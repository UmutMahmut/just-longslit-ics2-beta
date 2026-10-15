from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from justls.ics.drivers.zwo.assembly import (
    select_camera_descriptor,
)
from justls.ics.infra.camera_config import (
    CameraDeviceConfig,
    CameraRoleBinding,
    CameraSystemConfig,
)
from justls.ics.kernel.runtime import RuntimeAssembler, RuntimeConfig


def _descriptor(camera_id: int, name: str) -> SimpleNamespace:
    return SimpleNamespace(camera_id=camera_id, name=name)


class _FakeSession:
    def __init__(self, serial: str) -> None:
        self._serial = serial

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *_exc) -> None:
        return None

    def serial_number(self) -> str:
        return self._serial


class _FakeSdk:
    def __init__(self, serials: dict[int, str]) -> None:
        self._serials = serials

    def discover(self):
        return [_descriptor(camera_id, f"ZWO cam {camera_id}") for camera_id in self._serials]

    def open_camera(self, camera_id: int) -> _FakeSession:
        return _FakeSession(self._serials[camera_id])


def _device(**overrides) -> CameraDeviceConfig:
    payload = {
        "device_id": "asi294mc-pro-01",
        "driver": "zwo",
        "model": "ASI294MC Pro",
        "serial": "28344F041D010900",
        "width": 4144,
        "height": 2822,
        "bit_depth": 14,
        "gain": 0,
        "offset": 30,
        "binning": 1,
    }
    payload.update(overrides)
    return CameraDeviceConfig(**payload)


def test_select_by_serial_ignores_enumeration_order() -> None:
    sdk = _FakeSdk({5: "OTHER_SERIAL", 9: "28344F041D010900"})

    descriptor = select_camera_descriptor(sdk, _device())

    assert descriptor.camera_id == 9


def test_select_by_serial_fails_loudly_on_mismatch() -> None:
    sdk = _FakeSdk({1: "SOME_OTHER_SERIAL"})

    with pytest.raises(RuntimeError, match="28344F041D010900"):
        select_camera_descriptor(sdk, _device())


def test_placeholder_serial_is_not_treated_as_a_real_binding() -> None:
    sdk = _FakeSdk({3: "REAL_SERIAL_A"})
    config = _device(serial="REPLACE_WITH_DETECTED_SERIAL")

    descriptor = select_camera_descriptor(sdk, config)

    assert descriptor.camera_id == 3


def test_multiple_cameras_without_serial_is_rejected() -> None:
    sdk = _FakeSdk({1: "SERIAL_A", 2: "SERIAL_B"})
    config = _device(serial=None, model="not-present")

    with pytest.raises(RuntimeError, match="no serial configured"):
        select_camera_descriptor(sdk, config)


def test_no_cameras_is_an_actionable_error() -> None:
    sdk = _FakeSdk({})

    with pytest.raises(RuntimeError, match="no ZWO cameras detected"):
        select_camera_descriptor(sdk, _device())


class _FakeZwoDriver:
    def __init__(self) -> None:
        self.disconnected = False

    def abort_exposure(self):
        return {"result": "aborted", "had_active_exposure": False}

    def get_status(self):
        return {"driver": "zwo", "connected": True}

    def disconnect(self) -> None:
        self.disconnected = True


def _zwo_camera_config() -> CameraSystemConfig:
    return CameraSystemConfig(
        profile_name="test-zwo-mixed",
        devices=[
            _device(),
            CameraDeviceConfig(device_id="slit-camera-01", driver="simulated"),
        ],
        role_bindings=[
            CameraRoleBinding(
                role="science",
                device_id="asi294mc-pro-01",
                logical_channels=["SCI"],
                shared_capture=False,
            ),
            CameraRoleBinding(role="slit", device_id="slit-camera-01"),
        ],
    )


def test_runtime_assembles_zwo_detector_from_driver_config(monkeypatch, tmp_path) -> None:
    fake_driver = _FakeZwoDriver()
    config = _zwo_camera_config()

    def _build(device, return_sdk: bool = False):
        if return_sdk:
            return fake_driver, None
        return fake_driver

    monkeypatch.setattr(
        "justls.ics.drivers.zwo.assembly.build_zwo_detector_driver",
        _build,
    )
    monkeypatch.setattr(
        "justls.ics.kernel.runtime.load_camera_system_config",
        lambda path=None: (config, tmp_path / "cameras.json"),
    )

    runtime = RuntimeAssembler(RuntimeConfig()).build()

    assert runtime.detector is not None
    assert runtime.detector.adapter.simulated is False
    assert runtime.detector.adapter.logical_channels == ("SCI",)
    status = runtime.get_camera_status_dict()
    assert status["science_camera"]["driver"] == "zwo"

    runtime.shutdown()
    assert fake_driver.disconnected is True
