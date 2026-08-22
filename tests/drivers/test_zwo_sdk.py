from __future__ import annotations

from pathlib import Path

import pytest

from justls.ics.drivers.zwo.probe import SDK_LIBRARY_ENV, resolve_sdk_library
from justls.ics.drivers.zwo.sdk import AsiCameraInfo, ZwoSdk


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
