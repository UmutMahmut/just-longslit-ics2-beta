from __future__ import annotations

import ctypes
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from justls.ics.drivers.zwo.native_calls import GuardedLibrary, NativeCallGate, shared_gate


ASI_SUCCESS = 0
ASI_IMG_END = -1
ASI_IMG_RAW16 = 2
ASI_GAIN = 0
ASI_EXPOSURE = 1
ASI_OFFSET = 5
ASI_TEMPERATURE = 8
ASI_COOLER_POWER_PERCENT = 15
ASI_TARGET_TEMPERATURE = 16
ASI_COOLER_ON = 17

ASI_ERROR_NAMES = {
    0: "ASI_SUCCESS",
    1: "ASI_ERROR_INVALID_INDEX",
    2: "ASI_ERROR_INVALID_ID",
    3: "ASI_ERROR_INVALID_CONTROL_TYPE",
    4: "ASI_ERROR_CAMERA_CLOSED",
    5: "ASI_ERROR_CAMERA_REMOVED",
    6: "ASI_ERROR_INVALID_PATH",
    7: "ASI_ERROR_INVALID_FILEFORMAT",
    8: "ASI_ERROR_INVALID_SIZE",
    9: "ASI_ERROR_INVALID_IMGTYPE",
    10: "ASI_ERROR_OUTOF_BOUNDARY",
    11: "ASI_ERROR_TIMEOUT",
    12: "ASI_ERROR_INVALID_SEQUENCE",
    13: "ASI_ERROR_BUFFER_TOO_SMALL",
    14: "ASI_ERROR_VIDEO_MODE_ACTIVE",
    15: "ASI_ERROR_EXPOSURE_IN_PROGRESS",
    16: "ASI_ERROR_GENERAL_ERROR",
    17: "ASI_ERROR_INVALID_MODE",
}

BAYER_PATTERNS = {
    0: "RGGB",
    1: "BGGR",
    2: "GRBG",
    3: "GBRG",
}

IMAGE_TYPES = {
    0: "RAW8",
    1: "RGB24",
    2: "RAW16",
    3: "Y8",
}

CONTROL_TYPES = {
    0: "GAIN",
    1: "EXPOSURE",
    2: "GAMMA",
    3: "WB_R",
    4: "WB_B",
    5: "OFFSET",
    6: "BANDWIDTH_OVERLOAD",
    7: "OVERCLOCK",
    8: "TEMPERATURE",
    9: "FLIP",
    10: "AUTO_MAX_GAIN",
    11: "AUTO_MAX_EXPOSURE",
    12: "AUTO_TARGET_BRIGHTNESS",
    13: "HARDWARE_BIN",
    14: "HIGH_SPEED_MODE",
    15: "COOLER_POWER_PERCENT",
    16: "TARGET_TEMPERATURE",
    17: "COOLER_ON",
    18: "MONO_BIN",
    19: "FAN_ON",
    20: "PATTERN_ADJUST",
    21: "ANTI_DEW_HEATER",
}

EXPOSURE_STATUS = {
    0: "idle",
    1: "working",
    2: "success",
    3: "failed",
}


class AsiCameraInfo(ctypes.Structure):
    """Binary layout of ASI_CAMERA_INFO from the vendor ASICamera2.h."""

    _fields_ = [
        ("Name", ctypes.c_char * 64),
        ("CameraID", ctypes.c_int),
        ("MaxHeight", ctypes.c_long),
        ("MaxWidth", ctypes.c_long),
        ("IsColorCam", ctypes.c_int),
        ("BayerPattern", ctypes.c_int),
        ("SupportedBins", ctypes.c_int * 16),
        ("SupportedVideoFormat", ctypes.c_int * 8),
        ("PixelSize", ctypes.c_double),
        ("MechanicalShutter", ctypes.c_int),
        ("ST4Port", ctypes.c_int),
        ("IsCoolerCam", ctypes.c_int),
        ("IsUSB3Host", ctypes.c_int),
        ("IsUSB3Camera", ctypes.c_int),
        ("ElecPerADU", ctypes.c_float),
        ("BitDepth", ctypes.c_int),
        ("IsTriggerCam", ctypes.c_int),
        ("Unused", ctypes.c_char * 16),
    ]


class AsiControlCaps(ctypes.Structure):
    """Binary layout of ASI_CONTROL_CAPS from the vendor ASICamera2.h."""

    _fields_ = [
        ("Name", ctypes.c_char * 64),
        ("Description", ctypes.c_char * 128),
        ("MaxValue", ctypes.c_long),
        ("MinValue", ctypes.c_long),
        ("DefaultValue", ctypes.c_long),
        ("IsAutoSupported", ctypes.c_int),
        ("IsWritable", ctypes.c_int),
        ("ControlType", ctypes.c_int),
        ("Unused", ctypes.c_char * 32),
    ]


class AsiSerialNumber(ctypes.Structure):
    _fields_ = [("id", ctypes.c_ubyte * 8)]


@dataclass(frozen=True, slots=True)
class ZwoCameraDescriptor:
    index: int
    camera_id: int
    name: str
    max_width: int
    max_height: int
    is_color: bool
    bayer_pattern: str | None
    supported_bins: tuple[int, ...]
    supported_image_types: tuple[str, ...]
    pixel_size_um: float
    mechanical_shutter: bool
    st4_port: bool
    cooler: bool
    usb3_host: bool
    usb3_camera: bool
    electrons_per_adu: float
    bit_depth: int
    trigger_camera: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ZwoControlDescriptor:
    index: int
    control_type: int
    control_name: str
    sdk_name: str
    description: str
    minimum: int
    maximum: int
    default: int
    auto_supported: bool
    writable: bool
    current_value: int
    auto_enabled: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.control_name == "TEMPERATURE":
            data["current_value_c"] = self.current_value / 10.0
        return data


class ZwoSdkError(RuntimeError):
    def __init__(self, operation: str, code: int) -> None:
        self.operation = operation
        self.code = int(code)
        self.error_name = ASI_ERROR_NAMES.get(self.code, "ASI_ERROR_UNKNOWN")
        super().__init__(
            f"{operation} failed with {self.error_name} ({self.code})"
        )


class ZwoSdkLibraryLoadError(RuntimeError):
    """The vendor library itself (or one of its dependencies) failed to load."""


class ZwoCameraTopologyChangedError(ZwoSdkError):
    """A camera was connected/removed while enumeration was in progress.

    The ZWO SDK indexes cameras by hotplug order; calling it with a stale
    index after a topology change can crash the process outright, so the
    binding re-checks the camera count and raises this structured error
    instead. Callers should re-run discovery before retrying.
    """

    def __init__(
        self,
        operation: str,
        *,
        expected_count: int,
        actual_count: int,
    ) -> None:
        self.expected_count = int(expected_count)
        self.actual_count = int(actual_count)
        super().__init__(operation, 1)  # ASI_ERROR_INVALID_INDEX
        self.args = (
            f"{operation} aborted: camera topology changed during discovery "
            f"(expected {self.expected_count}, now {self.actual_count}). "
            "Re-run discovery before retrying.",
        )


# Enumeration calls share one lock process-wide: the vendor library crashes
# (access violation, not a catchable error) if topology queries race each
# other or run against a stale device list. Per-camera session calls use
# distinct camera IDs and are left unlocked so two cameras can expose in
# parallel.
_ENUMERATION_LOCK = threading.RLock()


def _load_library(dll_path: Path) -> Any:
    """Load ASICamera2 with its dependency directory registered.

    On Windows the vendor DLL depends on sibling DLLs that are only found if
    the containing directory is on the DLL search path. ``ctypes.WinDLL``
    alone fails (or worse, loads but crashes later) when ASI Studio is not on
    PATH, so we register the directory explicitly.
    """
    if not dll_path.is_file():
        raise ZwoSdkLibraryLoadError(
            "ZWO SDK library not found: "
            f"{dll_path}\n"
            "Install ZWO ASI Studio (or the ASI Camera SDK) and point "
            "ICS_ZWO_SDK_LIBRARY at ASICamera2.dll, e.g. "
            r"C:\Program Files\ASIStudio\ASICamera2.dll"
        )
    dll_dir_handle: Any | None = None
    if os.name == "nt" and hasattr(os, "add_dll_directory"):
        try:
            dll_dir_handle = os.add_dll_directory(str(dll_path.parent))
        except OSError:
            dll_dir_handle = None
    loader = ctypes.WinDLL if os.name == "nt" else ctypes.CDLL
    try:
        library = loader(str(dll_path))
    except OSError as exc:
        raise ZwoSdkLibraryLoadError(
            f"ZWO SDK library failed to load: {dll_path}\n"
            f"OS error: {exc}\n"
            "On Windows this is almost always a missing dependency of "
            "ASICamera2.dll. Install/repair ZWO ASI Studio and the ZWO USB "
            "camera driver, and make sure the DLL directory is reachable "
            "(it was registered via os.add_dll_directory before loading)."
        ) from exc
    return library, dll_dir_handle


class ZwoSdk:
    """Minimal read-only discovery binding for ASICamera2.dll."""

    def __init__(self, dll_path: str | Path, *, library: Any | None = None) -> None:
        self.dll_path = Path(dll_path).expanduser().resolve()
        real_library = library is None
        self._dll_dir_handle: Any | None = None
        if library is None:
            library, self._dll_dir_handle = _load_library(self.dll_path)
        self._library = library
        self._configure_signatures()
        gate = shared_gate(os.path.normcase(str(self.dll_path))) if real_library else NativeCallGate()
        self._library = GuardedLibrary(self._library, gate)
        self._native_gate = gate
        self.serial_by_camera_id: dict[int, str] = {}

    @property
    def health_error(self) -> str | None:
        return self._native_gate._quarantined

    def _configure_signatures(self) -> None:
        self._library.ASIGetSDKVersion.argtypes = []
        self._library.ASIGetSDKVersion.restype = ctypes.c_char_p
        self._library.ASIGetNumOfConnectedCameras.argtypes = []
        self._library.ASIGetNumOfConnectedCameras.restype = ctypes.c_int
        self._library.ASIGetCameraProperty.argtypes = [
            ctypes.POINTER(AsiCameraInfo),
            ctypes.c_int,
        ]
        self._library.ASIGetCameraProperty.restype = ctypes.c_int
        self._library.ASIOpenCamera.argtypes = [ctypes.c_int]
        self._library.ASIOpenCamera.restype = ctypes.c_int
        self._library.ASIInitCamera.argtypes = [ctypes.c_int]
        self._library.ASIInitCamera.restype = ctypes.c_int
        self._library.ASICloseCamera.argtypes = [ctypes.c_int]
        self._library.ASICloseCamera.restype = ctypes.c_int
        self._library.ASIGetNumOfControls.argtypes = [
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
        ]
        self._library.ASIGetNumOfControls.restype = ctypes.c_int
        self._library.ASIGetControlCaps.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(AsiControlCaps),
        ]
        self._library.ASIGetControlCaps.restype = ctypes.c_int
        self._library.ASIGetControlValue.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_long),
            ctypes.POINTER(ctypes.c_int),
        ]
        self._library.ASIGetControlValue.restype = ctypes.c_int
        self._library.ASISetControlValue.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_long,
            ctypes.c_int,
        ]
        self._library.ASISetControlValue.restype = ctypes.c_int
        self._library.ASISetROIFormat.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._library.ASISetROIFormat.restype = ctypes.c_int
        self._library.ASIStartExposure.argtypes = [ctypes.c_int, ctypes.c_int]
        self._library.ASIStartExposure.restype = ctypes.c_int
        self._library.ASIGetExpStatus.argtypes = [
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
        ]
        self._library.ASIGetExpStatus.restype = ctypes.c_int
        self._library.ASIGetDataAfterExp.argtypes = [
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_long,
        ]
        self._library.ASIGetDataAfterExp.restype = ctypes.c_int
        self._library.ASIStopExposure.argtypes = [ctypes.c_int]
        self._library.ASIStopExposure.restype = ctypes.c_int
        self._library.ASIGetSerialNumber.argtypes = [
            ctypes.c_int,
            ctypes.POINTER(AsiSerialNumber),
        ]
        self._library.ASIGetSerialNumber.restype = ctypes.c_int

    def sdk_version(self) -> str:
        raw = self._library.ASIGetSDKVersion()
        if raw is None:
            return "unknown"
        return bytes(raw).decode("ascii", errors="replace").strip()

    def connected_camera_count(self) -> int:
        with _ENUMERATION_LOCK:
            return int(self._library.ASIGetNumOfConnectedCameras())

    def discover(self) -> tuple[ZwoCameraDescriptor, ...]:
        with _ENUMERATION_LOCK:
            count = self.connected_camera_count()
            descriptors: list[ZwoCameraDescriptor] = []
            for index in range(count):
                # A hotplug between the count query and this property query
                # would hand the vendor library a stale index and can crash
                # the process; re-check before every call instead.
                current = self.connected_camera_count()
                if current != count:
                    raise ZwoCameraTopologyChangedError(
                        f"discover(index={index})",
                        expected_count=count,
                        actual_count=current,
                    )
                info = AsiCameraInfo()
                code = int(
                    self._library.ASIGetCameraProperty(ctypes.byref(info), index)
                )
                if code != ASI_SUCCESS:
                    recheck = self.connected_camera_count()
                    if recheck != count:
                        raise ZwoCameraTopologyChangedError(
                            f"ASIGetCameraProperty(index={index})",
                            expected_count=count,
                            actual_count=recheck,
                        )
                    raise ZwoSdkError(
                        f"ASIGetCameraProperty(index={index})", code
                    )
                descriptors.append(self._descriptor_from_info(index, info))
            return tuple(descriptors)

    def open_camera(self, camera_id: int) -> "ZwoCameraSession":
        """Open and initialize a camera; callers must use the returned context."""
        return ZwoCameraSession(self._library, camera_id)

    @staticmethod
    def _descriptor_from_info(
        index: int,
        info: AsiCameraInfo,
    ) -> ZwoCameraDescriptor:
        name = bytes(info.Name).split(b"\0", 1)[0].decode(
            "ascii", errors="replace"
        )
        bins = tuple(value for value in info.SupportedBins if value > 0)
        image_type_values: list[int] = []
        for value in info.SupportedVideoFormat:
            if value == ASI_IMG_END:
                break
            image_type_values.append(value)
        image_types = tuple(
            IMAGE_TYPES.get(value, f"UNKNOWN_{value}")
            for value in image_type_values
        )
        return ZwoCameraDescriptor(
            index=index,
            camera_id=int(info.CameraID),
            name=name,
            max_width=int(info.MaxWidth),
            max_height=int(info.MaxHeight),
            is_color=bool(info.IsColorCam),
            bayer_pattern=(
                BAYER_PATTERNS.get(int(info.BayerPattern))
                if info.IsColorCam
                else None
            ),
            supported_bins=bins,
            supported_image_types=image_types,
            pixel_size_um=float(info.PixelSize),
            mechanical_shutter=bool(info.MechanicalShutter),
            st4_port=bool(info.ST4Port),
            cooler=bool(info.IsCoolerCam),
            usb3_host=bool(info.IsUSB3Host),
            usb3_camera=bool(info.IsUSB3Camera),
            electrons_per_adu=float(info.ElecPerADU),
            bit_depth=int(info.BitDepth),
            trigger_camera=bool(info.IsTriggerCam),
        )


class ZwoCameraSession:
    """Scoped open/initialize/close lifecycle for one physical ASI camera."""

    def __init__(self, library: Any, camera_id: int) -> None:
        self._library = library
        self.camera_id = int(camera_id)
        self._opened = False

    def __enter__(self) -> "ZwoCameraSession":
        code = int(self._library.ASIOpenCamera(self.camera_id))
        if code != ASI_SUCCESS:
            raise ZwoSdkError("ASIOpenCamera", code)
        self._opened = True
        code = int(self._library.ASIInitCamera(self.camera_id))
        if code != ASI_SUCCESS:
            self.close()
            raise ZwoSdkError("ASIInitCamera", code)
        return self

    def __exit__(self, *_exc_info: Any) -> None:
        self.close()

    def close(self) -> None:
        if not self._opened:
            return
        code = int(self._library.ASICloseCamera(self.camera_id))
        self._opened = False
        if code != ASI_SUCCESS:
            raise ZwoSdkError("ASICloseCamera", code)

    def controls(self) -> tuple[ZwoControlDescriptor, ...]:
        if not self._opened:
            raise RuntimeError("camera session is not open")
        count = ctypes.c_int()
        code = int(
            self._library.ASIGetNumOfControls(self.camera_id, ctypes.byref(count))
        )
        if code != ASI_SUCCESS:
            raise ZwoSdkError("ASIGetNumOfControls", code)

        controls: list[ZwoControlDescriptor] = []
        for index in range(count.value):
            caps = AsiControlCaps()
            code = int(
                self._library.ASIGetControlCaps(
                    self.camera_id,
                    index,
                    ctypes.byref(caps),
                )
            )
            if code != ASI_SUCCESS:
                raise ZwoSdkError(f"ASIGetControlCaps(index={index})", code)

            value = ctypes.c_long()
            auto_enabled = ctypes.c_int()
            code = int(
                self._library.ASIGetControlValue(
                    self.camera_id,
                    int(caps.ControlType),
                    ctypes.byref(value),
                    ctypes.byref(auto_enabled),
                )
            )
            if code != ASI_SUCCESS:
                raise ZwoSdkError(
                    f"ASIGetControlValue(type={caps.ControlType})",
                    code,
                )

            controls.append(
                ZwoControlDescriptor(
                    index=index,
                    control_type=int(caps.ControlType),
                    control_name=CONTROL_TYPES.get(
                        int(caps.ControlType),
                        f"UNKNOWN_{caps.ControlType}",
                    ),
                    sdk_name=bytes(caps.Name).split(b"\0", 1)[0].decode(
                        "ascii", errors="replace"
                    ),
                    description=bytes(caps.Description)
                    .split(b"\0", 1)[0]
                    .decode("ascii", errors="replace"),
                    minimum=int(caps.MinValue),
                    maximum=int(caps.MaxValue),
                    default=int(caps.DefaultValue),
                    auto_supported=bool(caps.IsAutoSupported),
                    writable=bool(caps.IsWritable),
                    current_value=int(value.value),
                    auto_enabled=bool(auto_enabled.value),
                )
            )
        return tuple(controls)

    def serial_number(self) -> str:
        self._require_open()
        serial = AsiSerialNumber()
        code = int(
            self._library.ASIGetSerialNumber(
                self.camera_id,
                ctypes.byref(serial),
            )
        )
        if code != ASI_SUCCESS:
            raise ZwoSdkError("ASIGetSerialNumber", code)
        return bytes(serial.id).hex().upper()

    def control_value(self, control_type: int) -> tuple[int, bool]:
        self._require_open()
        value = ctypes.c_long()
        auto_enabled = ctypes.c_int()
        code = int(
            self._library.ASIGetControlValue(
                self.camera_id,
                int(control_type),
                ctypes.byref(value),
                ctypes.byref(auto_enabled),
            )
        )
        if code != ASI_SUCCESS:
            raise ZwoSdkError(f"ASIGetControlValue(type={control_type})", code)
        return int(value.value), bool(auto_enabled.value)

    def set_control_value(
        self,
        control_type: int,
        value: int,
        *,
        auto: bool = False,
    ) -> tuple[int, bool]:
        self._require_open()
        code = int(
            self._library.ASISetControlValue(
                self.camera_id,
                int(control_type),
                int(value),
                int(auto),
            )
        )
        if code != ASI_SUCCESS:
            raise ZwoSdkError(f"ASISetControlValue(type={control_type})", code)
        return self.control_value(control_type)

    def set_roi_format(
        self,
        *,
        width: int,
        height: int,
        binning: int,
        image_type: int,
    ) -> None:
        self._require_open()
        code = int(
            self._library.ASISetROIFormat(
                self.camera_id,
                int(width),
                int(height),
                int(binning),
                int(image_type),
            )
        )
        if code != ASI_SUCCESS:
            raise ZwoSdkError("ASISetROIFormat", code)

    def start_exposure(self, *, dark: bool = False) -> None:
        self._require_open()
        code = int(self._library.ASIStartExposure(self.camera_id, int(dark)))
        if code != ASI_SUCCESS:
            raise ZwoSdkError("ASIStartExposure", code)

    def exposure_status(self) -> str:
        self._require_open()
        status = ctypes.c_int()
        code = int(
            self._library.ASIGetExpStatus(self.camera_id, ctypes.byref(status))
        )
        if code != ASI_SUCCESS:
            raise ZwoSdkError("ASIGetExpStatus", code)
        return EXPOSURE_STATUS.get(status.value, f"unknown_{status.value}")

    def wait_for_exposure(
        self,
        *,
        timeout_s: float,
        poll_interval_s: float = 0.01,
    ) -> str:
        deadline = time.monotonic() + timeout_s
        while True:
            status = self.exposure_status()
            if status != "working":
                return status
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"ZWO exposure did not finish within {timeout_s:.3f} seconds"
                )
            time.sleep(poll_interval_s)

    def read_exposure_data(self, *, buffer_size: int) -> bytes:
        self._require_open()
        if buffer_size <= 0:
            raise ValueError("buffer_size must be positive")
        buffer = (ctypes.c_ubyte * buffer_size)()
        code = int(
            self._library.ASIGetDataAfterExp(
                self.camera_id,
                buffer,
                buffer_size,
            )
        )
        if code != ASI_SUCCESS:
            raise ZwoSdkError("ASIGetDataAfterExp", code)
        return bytes(buffer)

    def stop_exposure(self) -> None:
        self._require_open()
        code = int(self._library.ASIStopExposure(self.camera_id))
        if code != ASI_SUCCESS:
            raise ZwoSdkError("ASIStopExposure", code)

    def _require_open(self) -> None:
        if not self._opened:
            raise RuntimeError("camera session is not open")
