from __future__ import annotations

import io

import pytest
from PIL import Image

from justls.ics.drivers.zwo.preview_driver import ZwoPreviewCameraDriver
from justls.ics.drivers.zwo.sdk import ZwoCameraDescriptor
from justls.ics.infra.camera_config import CameraDeviceConfig

import numpy as np


class FakeZwoSession:
    def __init__(self, *, serial: str = "GUIDESERIAL") -> None:
        self.serial = serial
        self.closed = False
        self.roi: tuple[int, int, int, int] | None = None
        self.controls = {8: 255}  # ASI_TEMPERATURE -> 25.5 C

    def __enter__(self) -> "FakeZwoSession":
        return self

    def __exit__(self, *_exc_info) -> None:
        self.closed = True

    def set_roi_format(self, *, width, height, binning, image_type) -> None:
        self.roi = (width, height, binning, image_type)

    def serial_number(self) -> str:
        return self.serial

    def set_control_value(self, control_type, value, *, auto=False):
        self.controls[control_type] = value
        return value, auto

    def control_value(self, control_type):
        return self.controls[control_type], False

    def start_exposure(self, *, dark=False) -> None:
        self.dark = dark

    def wait_for_exposure(self, *, timeout_s):
        return "success"

    def read_exposure_data(self, *, buffer_size):
        pixel_count = buffer_size // 2
        return np.full(pixel_count, 3000, dtype="<u2").tobytes()

    def stop_exposure(self) -> None:
        pass

    def exposure_status(self) -> str:
        return "success"


class FakeZwoSdk:
    def __init__(self, session: FakeZwoSession) -> None:
        self.session = session

    def open_camera(self, camera_id: int) -> FakeZwoSession:
        return self.session


def descriptor() -> ZwoCameraDescriptor:
    return ZwoCameraDescriptor(
        index=0,
        camera_id=3,
        name="ZWO ASI678MC",
        max_width=3840,
        max_height=2160,
        is_color=True,
        bayer_pattern="RGGB",
        supported_bins=(1, 2),
        supported_image_types=("RAW8", "RAW16"),
        pixel_size_um=2.0,
        mechanical_shutter=False,
        st4_port=True,
        cooler=False,
        usb3_host=True,
        usb3_camera=True,
        electrons_per_adu=1.0,
        bit_depth=12,
        trigger_camera=False,
    )


def camera_config(*, serial: str = "GUIDESERIAL") -> CameraDeviceConfig:
    return CameraDeviceConfig(
        device_id="zwo-guide-01",
        driver="zwo",
        manufacturer="ZWO",
        model="ZWO ASI678MC",
        serial=serial,
        width=1920,
        height=1080,
        bit_depth=12,
        gain=150,
        preview_exposure_ms=50.0,
    )


def build_driver(**kwargs) -> ZwoPreviewCameraDriver:
    session = kwargs.pop("session", FakeZwoSession())
    driver = ZwoPreviewCameraDriver(
        FakeZwoSdk(session),  # type: ignore[arg-type]
        descriptor(),
        camera_config(),
        **kwargs,
    )
    driver._fake_session = session  # type: ignore[attr-defined]
    return driver


def test_capture_jpeg_returns_decodable_jpeg_and_metadata() -> None:
    driver = build_driver()
    driver.connect()

    payload, meta = driver.capture_jpeg()

    image = Image.open(io.BytesIO(payload))
    assert image.format == "JPEG"
    assert meta["media_type"] == "image/jpeg"
    assert meta["width"] == 1920
    assert meta["height"] == 1080
    assert meta["sequence"] == 1
    assert meta["serial"] == "GUIDESERIAL"
    assert meta["exposure_ms"] == pytest.approx(50.0)
    driver.disconnect()


def test_stopped_preview_refuses_capture_and_resumes() -> None:
    driver = build_driver()
    driver.connect()

    driver.stop_preview()
    with pytest.raises(RuntimeError, match="preview is stopped"):
        driver.capture_jpeg()

    driver.start_preview()
    payload, meta = driver.capture_jpeg()
    assert payload[:2] == b"\xff\xd8"  # JPEG SOI marker
    assert meta["sequence"] == 1
    driver.disconnect()


def test_roi_is_aligned_down_to_zwo_constraints() -> None:
    session = FakeZwoSession()
    config = camera_config()
    config = config.model_copy(update={"width": 1919, "height": 1079})
    driver = ZwoPreviewCameraDriver(
        FakeZwoSdk(session),  # type: ignore[arg-type]
        descriptor(),
        config,
    )
    driver.connect()

    assert session.roi is not None
    width, height, _binning, _image_type = session.roi
    assert width == 1912  # 1919 rounded down to a multiple of 8
    assert height == 1078  # 1079 rounded down to a multiple of 2
    driver.disconnect()


def test_serial_mismatch_refuses_connection_and_closes_session() -> None:
    session = FakeZwoSession(serial="OTHERCAM")
    driver = ZwoPreviewCameraDriver(
        FakeZwoSdk(session),  # type: ignore[arg-type]
        descriptor(),
        camera_config(serial="GUIDESERIAL"),
    )

    with pytest.raises(RuntimeError, match="serial number does not match"):
        driver.connect()

    assert session.closed is True


def test_status_reports_cached_temperature_without_usb_polling() -> None:
    driver = build_driver()
    driver.connect()

    status = driver.status()
    assert status["state"] == "previewing"
    assert status["connected"] is True
    assert status["temperature_c"] == pytest.approx(25.5)

    driver._fake_session.controls[8] = 0  # type: ignore[attr-defined]
    assert driver.status()["temperature_c"] == pytest.approx(25.5)
    driver._fake_session.control_value = lambda *_: pytest.fail("Status polled USB")
    assert driver.status()["connected"]
    driver.disconnect()


def test_disconnect_releases_session() -> None:
    driver = build_driver()
    driver.connect()
    driver.disconnect()

    assert driver._fake_session.closed is True  # type: ignore[attr-defined]
    status = driver.status()
    assert status["connected"] is False
    assert status["state"] == "stopped"

def test_failed_preview_discards_failed_snap_and_next_frame_recovers():
    driver = build_driver()
    driver.connect()
    session = driver._fake_session
    results = iter(['failed', 'success'])
    session.wait_for_exposure = lambda **_: next(results)
    stopped = []
    session.stop_exposure = lambda: stopped.append(True)
    try:
        with pytest.raises(RuntimeError, match='failed'):
            driver.capture_jpeg()
        assert stopped == [True]
        assert driver.status()['failed_frames'] == 1
        assert driver.status()['error']
        payload, meta = driver.capture_jpeg()
        assert payload[:2] == b'\xff\xd8'
        assert driver.status()['error'] is None
        assert meta['sequence'] == 1
    finally:
        driver.disconnect()

def test_quarantined_sdk_is_not_reported_as_live_preview():
    driver = build_driver()
    driver.connect()
    driver.sdk.health_error = 'SDK quarantined; restart the service'
    try:
        status = driver.status()
        assert not status['connected']
        assert not status['preview_enabled']
        assert status['state'] == 'unavailable'
        assert 'restart' in status['error']
    finally:
        driver.disconnect()
