"""Assembly helpers that wire the ZWO driver into the managed runtime.

These functions are the single place where deployment configuration
(``CameraDeviceConfig``) is resolved against physically attached hardware:

- the vendor library path comes from explicit configuration, the
  ``ICS_ZWO_SDK_LIBRARY`` environment variable, or well-known install
  locations;
- cameras are bound **by serial number**, never by USB enumeration index
  (indices change with hotplug order; serials do not).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from justls.ics.drivers.zwo.native_calls import (
    SDK_HARDWARE_TIMEOUT_S, ZwoHardwareTimeoutError, _run_with_watchdog,
)

from justls.ics.drivers.zwo.sdk import (
    ZwoCameraDescriptor,
    ZwoSdk,
    ZwoSdkError,
    ZwoSdkLibraryLoadError,
)

logger = logging.getLogger(__name__)


from justls.ics.drivers.zwo.detector_driver import ZwoDetectorDriver
from justls.ics.drivers.zwo.preview_driver import ZwoPreviewCameraDriver
from justls.ics.infra.camera_config import CameraDeviceConfig

SDK_LIBRARY_ENV = "ICS_ZWO_SDK_LIBRARY"

# Vendor installers register ASICamera2.dll in these locations by default.
_DEFAULT_LIBRARY_CANDIDATES = (
    r"C:\Program Files\ASIStudio\ASICamera2.dll",
    r"C:\Program Files (x86)\ASIStudio\ASICamera2.dll",
)

# Placeholder values used in example configs; they must not be treated as
# real serial numbers.
_SERIAL_PLACEHOLDER_PREFIXES = ("REPLACE", "TODO", "CHANGEME")


def resolve_sdk_library_path(explicit: str | Path | None = None) -> Path:
    """Resolve the ASICamera2 library path without raising ``SystemExit``.

    Unlike the CLI resolver in ``probe.py`` this raises a structured error so
    the runtime can surface it through the API instead of terminating.
    """
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    configured = os.getenv(SDK_LIBRARY_ENV)
    if configured and configured.strip():
        return Path(configured.strip()).expanduser().resolve()
    if sys.platform.startswith("win"):
        for candidate in _DEFAULT_LIBRARY_CANDIDATES:
            path = Path(candidate)
            if path.is_file():
                return path
    raise ZwoSdkLibraryLoadError(
        "no ZWO SDK library configured: set "
        f"{SDK_LIBRARY_ENV} to the full path of ASICamera2.dll "
        "(it ships with ZWO ASI Studio / the ASI Camera SDK)"
    )


def _is_configured_serial(serial: str | None) -> bool:
    if not serial or not serial.strip():
        return False
    normalized = serial.strip().upper()
    return not normalized.startswith(_SERIAL_PLACEHOLDER_PREFIXES)


def _read_serial(sdk: ZwoSdk, descriptor: ZwoCameraDescriptor) -> str:
    cache = getattr(sdk, "serial_by_camera_id", {})
    if descriptor.camera_id in cache:
        return cache[descriptor.camera_id]
    with sdk.open_camera(descriptor.camera_id) as session:
        serial = session.serial_number()
    cache[descriptor.camera_id] = serial
    return serial


def select_camera_descriptor(
    sdk: ZwoSdk,
    config: CameraDeviceConfig,
) -> ZwoCameraDescriptor:
    """Pick the physical camera for a deployment profile.

    Serial binding is authoritative: when the profile carries a real serial
    number, every discovered camera is checked and a mismatch is a hard
    error (silently exposing the wrong camera is worse than failing fast).
    USB enumeration order is only ever a discovery detail.
    """
    # Enumerate once before opening either role. Enumeration is not a
    # connectivity heartbeat while the SDK owns live USB sessions.
    cameras = getattr(sdk, "binding_descriptors", None)
    if cameras is None:
        cameras = sdk.discover()
        sdk.binding_descriptors = cameras
    if not cameras:
        raise RuntimeError(
            f"no ZWO cameras detected for device {config.device_id!r}: "
            "check USB connections, close ASI Studio/ASICap (the SDK opens "
            "cameras exclusively), then retry"
        )

    wanted_serial = (config.serial or "").strip()
    if _is_configured_serial(wanted_serial):
        detected: dict[str, str] = {}
        for camera in cameras:
            try:
                detected[camera.name] = _read_serial(sdk, camera)
            except ZwoSdkError:
                detected[camera.name] = "<unreadable>"
            if detected[camera.name].upper() == wanted_serial.upper():
                return camera
        available = ", ".join(
            f"{name} serial={serial}" for name, serial in detected.items()
        )
        raise RuntimeError(
            f"no attached ZWO camera matches the configured serial "
            f"{wanted_serial!r} for device {config.device_id!r}. "
            f"Detected: {available}"
        )

    if len(cameras) == 1:
        return cameras[0]

    if config.model:
        matches = [
            camera
            for camera in cameras
            if config.model.strip().lower() in camera.name.lower()
        ]
        if len(matches) == 1:
            return matches[0]

    available = ", ".join(f"{camera.name} (id={camera.camera_id})" for camera in cameras)
    raise RuntimeError(
        f"{len(cameras)} ZWO cameras are attached but device "
        f"{config.device_id!r} has no serial configured; set 'serial' in the "
        f"camera profile so the binding is unambiguous. Detected: {available}"
    )


def build_zwo_detector_driver(
    config: CameraDeviceConfig,
    *,
    sdk: ZwoSdk | None = None,
    sdk_library: str | Path | None = None,
    return_sdk: bool = False,
):
    """Build a connected ZWO detector driver for the given device profile.

    Setting ``return_sdk=True`` returns ``(driver, sdk)`` so the caller can
    share the SDK instance with another component (e.g. the hot-plug
    monitor) without paying for a second ``ZwoSdk`` construction. The default
    return shape is preserved for back-compat with existing tests.
    """
    if sdk is None:
        sdk = ZwoSdk(resolve_sdk_library_path(sdk_library))
    descriptor = select_camera_descriptor(sdk, config)
    driver = ZwoDetectorDriver(
        sdk,
        descriptor,
        config,
        gain=int(config.gain),
        offset=int(config.offset),
        binning=int(config.binning),
    )
    try:
        driver.connect()
    except Exception:
        # Never leak an open camera if ROI/serial validation fails.
        try:
            driver.disconnect()
        except Exception:
            pass
        raise
    if return_sdk:
        return driver, sdk
    return driver


def build_zwo_preview_driver(
    config: CameraDeviceConfig,
    *,
    sdk: ZwoSdk | None = None,
    sdk_library: str | Path | None = None,
    role: str = "slit",
    return_sdk: bool = False,
):
    """Build a connected ZWO slit/guide preview driver for the given profile.

    Serial binding works exactly like the science camera: the two roles are
    told apart by their serial numbers, never by USB enumeration order.
    See :func:`build_zwo_detector_driver` for the meaning of ``return_sdk``.
    """
    if sdk is None:
        sdk = ZwoSdk(resolve_sdk_library_path(sdk_library))
    descriptor = select_camera_descriptor(sdk, config)
    driver = ZwoPreviewCameraDriver(sdk, descriptor, config, role=role)
    try:
        driver.connect()
    except Exception:
        try:
            driver.disconnect()
        except Exception:
            pass
        raise
    if return_sdk:
        return driver, sdk
    return driver
