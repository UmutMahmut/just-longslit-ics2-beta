from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from justls.ics.adapters.detector.adapter import DetectorAdapter
from justls.ics.drivers.zwo.detector_driver import ZwoDetectorDriver
from justls.ics.drivers.zwo.sdk import ZwoCameraDescriptor
from justls.ics.infra.camera_config import CameraDeviceConfig
from justls.ics.infra.data_products import LocalDataProductWriter


class FakeZwoSession:
    def __init__(self, *, serial: str = "SERIAL01") -> None:
        self.serial = serial
        self.closed = False
        self.roi: tuple[int, int, int, int] | None = None
        self.controls = {8: 123, 15: 50, 16: -10, 17: 1}

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
        return np.arange(pixel_count, dtype="<u2").tobytes()

    def stop_exposure(self) -> None:
        pass

    def exposure_status(self) -> str:
        return "success"


class FakeZwoSdk:
    def __init__(self, session: FakeZwoSession) -> None:
        self.session = session

    def open_camera(self, camera_id: int) -> FakeZwoSession:
        self.camera_id = camera_id
        return self.session


def descriptor() -> ZwoCameraDescriptor:
    return ZwoCameraDescriptor(
        index=0,
        camera_id=7,
        name="ZWO test camera",
        max_width=32,
        max_height=16,
        is_color=True,
        bayer_pattern="RGGB",
        supported_bins=(1,),
        supported_image_types=("RAW8", "RAW16"),
        pixel_size_um=4.63,
        mechanical_shutter=False,
        st4_port=False,
        cooler=True,
        usb3_host=True,
        usb3_camera=True,
        electrons_per_adu=0.4,
        bit_depth=14,
        trigger_camera=False,
    )


def camera_config(*, serial: str = "SERIAL01") -> CameraDeviceConfig:
    return CameraDeviceConfig(
        device_id="zwo-test-01",
        driver="zwo",
        manufacturer="ZWO",
        model="ZWO test camera",
        serial=serial,
        width=32,
        height=16,
        bit_depth=14,
        gain=0,
    )


def test_hardware_driver_writes_real_raw16_fits_contract(tmp_path: Path) -> None:
    session = FakeZwoSession()
    driver = ZwoDetectorDriver(
        FakeZwoSdk(session),  # type: ignore[arg-type]
        descriptor(),
        camera_config(),
        gain=0,
        offset=30,
    )
    adapter = DetectorAdapter(
        driver,
        writer=LocalDataProductWriter(tmp_path),
        logical_channels=("SCI",),
        simulated=False,
    )

    with driver:
        result = adapter.acquire_exposure(
            obs_id="obs-zwo-contract",
            exp_time_s=0.01,
            frame_type="test",
            save_requested=True,
        )

    assert session.roi == (32, 16, 1, 2)
    assert session.closed is True
    assert result["simulated"] is False
    assert result["detector_metadata"]["serial"] == "SERIAL01"
    assert result["detector_metadata"]["cooler_enabled"] is True
    assert result["detector_metadata"]["detector_temperature_c"] == 12.3

    with fits.open(result["file_path"], uint=True) as hdus:
        hdus.verify("exception")
        assert hdus[0].data.dtype == np.dtype("uint16")
        assert hdus[0].data.shape == (16, 32)
        assert hdus[0].header["SIMULATE"] is False
        assert hdus[0].header["DETSER"] == "SERIAL01"
        assert hdus[0].header["BAYERPAT"] == "RGGB"


def test_connect_refuses_serial_mismatch() -> None:
    session = FakeZwoSession(serial="ACTUAL02")
    driver = ZwoDetectorDriver(
        FakeZwoSdk(session),  # type: ignore[arg-type]
        descriptor(),
        camera_config(serial="EXPECTED01"),
    )

    with pytest.raises(RuntimeError, match="serial number does not match"):
        driver.connect()

    assert session.closed is True


def _connected_driver(session: FakeZwoSession) -> ZwoDetectorDriver:
    driver = ZwoDetectorDriver(
        FakeZwoSdk(session),  # type: ignore[arg-type]
        descriptor(),
        camera_config(),
        gain=0,
        offset=30,
    )
    driver.connect()
    return driver


def test_zero_temperature_reading_is_invalid_not_a_measurement() -> None:
    # Bench reality 2026-10-08: ASI294MC Pro with its 12 V cooler supply
    # unplugged reports TEMPERATURE raw=0 (0.0 C).
    session = FakeZwoSession()
    session.controls[8] = 0
    driver = _connected_driver(session)
    try:
        status = driver.cooling_status()
        assert status["temperature_state"] == "invalid"
        assert status["detector_temperature_c"] is None

        metadata = driver._frame_metadata()
        assert metadata.temperature_state == "invalid"
        assert metadata.detector_temperature_c is None
        cards = {k: v for k, v in metadata.to_fits_cards().items() if v is not None}
        assert "CCD-TEMP" not in cards
        assert cards["TEMPSTAT"] == "invalid"
    finally:
        driver.disconnect()


def test_temperature_reading_recovers_to_stale_after_valid_read() -> None:
    session = FakeZwoSession()
    session.controls[8] = 123  # 12.3 C
    driver = _connected_driver(session)
    try:
        assert driver.cooling_status()["temperature_state"] == "stable"

        session.controls[8] = 0  # sensor supply lost mid-session
        status = driver.cooling_status()
        assert status["temperature_state"] == "stale"
        assert status["detector_temperature_c"] == 12.3
        assert status["temperature_age_s"] is not None
    finally:
        driver.disconnect()


def test_temperature_read_failure_uses_cache_then_invalid() -> None:
    session = FakeZwoSession()
    session.controls[8] = 123
    driver = _connected_driver(session)
    try:
        assert driver.cooling_status()["temperature_state"] == "stable"

        original = session.control_value

        def failing(control_type):
            if control_type == 8:
                raise RuntimeError("USB hiccup")
            return original(control_type)

        session.control_value = failing  # type: ignore[method-assign]
        status = driver.cooling_status()
        assert status["temperature_state"] == "stale"
        assert status["detector_temperature_c"] == 12.3
    finally:
        driver.disconnect()

def test_bias_zero_uses_sdk_minimum_and_records_both_times():
    from types import SimpleNamespace
    driver = _connected_driver(FakeZwoSession())
    driver.control_limits[1] = SimpleNamespace(minimum=32, maximum=2000000000)
    try:
        started = driver.start_exposure(obs_id='bias-min', exp_id='bias-0', exp_time_s=0, frame_type='bias', save_requested=False)
        assert started['requested_exp_time_s'] == 0
        assert started['actual_exp_time_s'] == .000032
        assert driver._session.dark
        assert driver.finish_exposure()['requested_exp_time_s'] == 0
    finally:
        driver.disconnect()


def test_status_is_nonblocking_and_performs_no_sdk_io():
    session = FakeZwoSession()
    driver = _connected_driver(session)
    try:
        session.control_value = lambda *_: pytest.fail('status polled USB controls')
        session.exposure_status = lambda: pytest.fail('status polled exposure hardware')
        assert driver.get_status()['connected']
    finally:
        driver.disconnect()


def test_disconnect_closes_session_even_when_abort_fails():
    session = FakeZwoSession()
    driver = ZwoDetectorDriver(FakeZwoSdk(session), descriptor(), camera_config())
    driver.connect()
    driver.start_exposure(obs_id="obs", exp_id="exp", exp_time_s=1,
                          frame_type="test", save_requested=False)
    def broken_stop():
        raise RuntimeError("USB stop failed")
    session.stop_exposure = broken_stop
    with pytest.raises(RuntimeError, match="USB stop failed"):
        driver.disconnect()
    assert session.closed
    assert driver._session is None
    assert driver._active is None
    driver.disconnect()  # repeated shutdown is harmless
