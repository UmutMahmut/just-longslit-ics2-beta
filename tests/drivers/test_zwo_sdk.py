from __future__ import annotations

import ctypes
from pathlib import Path
from types import SimpleNamespace

import pytest

from justls.ics.drivers.zwo.probe import SDK_LIBRARY_ENV, resolve_sdk_library
from justls.ics.drivers.zwo.sdk import (
    AsiCameraInfo,
    ZwoCameraTopologyChangedError,
    ZwoSdk,
    ZwoSdkLibraryLoadError,
)


def test_camera_info_converts_to_generic_descriptor() -> None:
    info = AsiCameraInfo()
    info.Name = b"ZWO ASI294MC Pro"
    info.CameraID = 3
    info.MaxWidth = 4144
    info.MaxHeight = 2822
    info.IsColorCam = 1
    info.BayerPattern = 0
    info.SupportedBins[0] = 1
    info.SupportedBins[1] = 2
    info.SupportedBins[2] = 4
    info.SupportedVideoFormat[0] = 0
    info.SupportedVideoFormat[1] = 2
    info.SupportedVideoFormat[2] = -1
    info.PixelSize = 4.63
    info.IsCoolerCam = 1
    info.IsUSB3Host = 1
    info.IsUSB3Camera = 1
    info.ElecPerADU = 0.26
    info.BitDepth = 14

    descriptor = ZwoSdk._descriptor_from_info(0, info)

    assert descriptor.name == "ZWO ASI294MC Pro"
    assert descriptor.camera_id == 3
    assert (descriptor.max_width, descriptor.max_height) == (4144, 2822)
    assert descriptor.is_color is True
    assert descriptor.bayer_pattern == "RGGB"
    assert descriptor.supported_bins == (1, 2, 4)
    assert descriptor.supported_image_types == ("RAW8", "RAW16")
    assert descriptor.cooler is True
    assert descriptor.bit_depth == 14


def test_mono_camera_does_not_publish_a_bayer_pattern() -> None:
    info = AsiCameraInfo()
    info.Name = b"Mono test camera"
    info.IsColorCam = 0
    info.BayerPattern = 2
    info.SupportedVideoFormat[0] = -1

    descriptor = ZwoSdk._descriptor_from_info(0, info)

    assert descriptor.is_color is False
    assert descriptor.bayer_pattern is None


def test_sdk_library_path_is_deployment_configuration(monkeypatch) -> None:
    monkeypatch.setenv(SDK_LIBRARY_ENV, r"D:\vendor\ASICamera2.dll")

    assert resolve_sdk_library(None) == Path(r"D:\vendor\ASICamera2.dll")
    assert resolve_sdk_library(Path("explicit.dll")) == Path("explicit.dll")


def test_sdk_library_path_is_required(monkeypatch) -> None:
    monkeypatch.delenv(SDK_LIBRARY_ENV, raising=False)

    with pytest.raises(SystemExit, match="provide --dll"):
        resolve_sdk_library(None)


def _fake_library(connected_count: int) -> SimpleNamespace:
    def get_property(info_ptr, index):
        info = ctypes.cast(info_ptr, ctypes.POINTER(AsiCameraInfo)).contents
        info.Name = b"Fake ZWO camera"
        info.CameraID = index + 10
        info.SupportedVideoFormat[0] = -1
        return 0

    return SimpleNamespace(
        ASIGetSDKVersion=lambda: b"1.0.0.0",
        ASIGetNumOfConnectedCameras=lambda: connected_count,
        ASIGetCameraProperty=get_property,
        ASIOpenCamera=lambda camera_id: 0,
        ASIInitCamera=lambda camera_id: 0,
        ASICloseCamera=lambda camera_id: 0,
        ASIGetNumOfControls=lambda camera_id, count_ptr: 0,
        ASIGetControlCaps=lambda camera_id, index, caps_ptr: 0,
        ASIGetControlValue=lambda camera_id, control_type, value_ptr, auto_ptr: 0,
        ASISetControlValue=lambda camera_id, control_type, value, auto: 0,
        ASISetROIFormat=lambda camera_id, width, height, binning, image_type: 0,
        ASIStartExposure=lambda camera_id, dark: 0,
        ASIGetExpStatus=lambda camera_id, status_ptr: 0,
        ASIGetDataAfterExp=lambda camera_id, buffer, size: 0,
        ASIStopExposure=lambda camera_id: 0,
        ASIGetSerialNumber=lambda camera_id, serial_ptr: 0,
    )


def test_discover_succeeds_with_stable_topology(tmp_path) -> None:
    sdk = ZwoSdk(tmp_path / "unused.dll", library=_fake_library(2))

    descriptors = sdk.discover()

    assert [d.camera_id for d in descriptors] == [10, 11]


def test_discover_reports_topology_change_instead_of_stale_index(tmp_path) -> None:
    library = _fake_library(2)
    state = {"count": 2, "property_calls": 0}

    def shrinking_count() -> int:
        return state["count"]

    def get_property(info_ptr, index):
        state["property_calls"] += 1
        # Simulate a camera being unplugged after the first property query.
        state["count"] = 1
        return 1  # ASI_ERROR_INVALID_INDEX, as the vendor SDK would return

    library.ASIGetNumOfConnectedCameras = shrinking_count
    library.ASIGetCameraProperty = get_property
    sdk = ZwoSdk(tmp_path / "unused.dll", library=library)

    with pytest.raises(ZwoCameraTopologyChangedError) as exc_info:
        sdk.discover()

    assert exc_info.value.expected_count == 2
    assert exc_info.value.actual_count == 1
    assert "topology changed" in str(exc_info.value)
    # The stale index 1 must never reach the vendor library.
    assert state["property_calls"] == 1


def test_missing_library_raises_actionable_error(tmp_path) -> None:
    with pytest.raises(ZwoSdkLibraryLoadError, match="ICS_ZWO_SDK_LIBRARY"):
        ZwoSdk(tmp_path / "ASICamera2.dll")
