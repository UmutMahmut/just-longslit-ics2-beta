from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from justls.ics.application.dispatcher import CommandDispatcher, validate_required_params
from justls.ics.application.services.health_service import HealthService
from justls.ics.application.services.management_service import ManagementService
from justls.ics.application.services.observation_service import ObservationService
from justls.ics.app.main import app
from justls.ics.application.usecases.presets import (
    build_preset_config,
    build_preset_plan,
    list_presets,
)
from justls.ics.domain.detector.config import DetectorConfig
from justls.ics.kernel.errors import (
    ErrorCode,
    InvalidParamError,
    InvalidStateError,
    UnsupportedError,
)
from justls.ics.kernel.jobs import CommandRequest, JobTracker
from justls.ics.kernel.runtime import RuntimeAssembler, RuntimeConfig, reset_runtime
from justls.ics.kernel.states import (
    CommandSource,
    ControlState,
    ExposureState,
    RunMode,
    build_initial_state,
)


@pytest.fixture(autouse=True)
def _reset_runtime_singleton():
    reset_runtime()
    yield
    reset_runtime()


def test_services_read_runtime_state_calibration_observation_and_detector_config():
    runtime = RuntimeAssembler().build()

    runtime.set_detector_config(
        {
            "profile_name": "rgb-safe-default",
            "trigger_mode": "internal",
            "readout_mode": "normal",
            "channels": {
                "B": {"enabled": True, "camera_role": "science_b"},
                "G": {"enabled": False, "camera_role": "science_g"},
                "R": {"enabled": True, "camera_role": "science_r"},
            },
        }
    )

    health_service = HealthService(runtime)
    management_service = ManagementService(runtime)
    observation_service = ObservationService(runtime, CommandDispatcher(runtime))

    management_service.set_connected("slit", True, message="connected")
    management_service.set_state("slit", ControlState.IDLE, message="ready")
    runtime.slit.set_width_um(150.0)
    runtime.slit.set_angle_deg(10.0)

    runtime.lamps.set_mode("calibration")
    runtime.lamps.select_lamp("flat", enable=True)

    runtime.detector.arm(
        exp_time_s=5.0,
        frame_type="science",
        operator_note="service-check",
        instrument_snapshot={"slit_width_um": 150.0, "slit_angle_deg": 10.0},
        calibration_snapshot=runtime.lamps.get_snapshot().to_dict(),
        detector_config=runtime.get_detector_config_dict(),
    )
    runtime.set_exposure_state(ExposureState.ARMED)

    state_dto = health_service.get_state_dto()
    status_full = health_service.get_status_full()
    calibration = health_service.get_calibration_status()
    observation = health_service.get_observation_status()
    exposure = observation_service.get_exposure_status()

    assert state_dto["slit_width_um"] == 150.0
    assert state_dto["slit_angle_deg"] == 10.0
    assert state_dto["lamp_on"] is True

    assert status_full["capabilities"]["calib_lamps"] is True
    assert status_full["calibration"]["mode"] == "calibration"
    assert status_full["calibration"]["active_lamp"] == "flat"
    assert status_full["calibration"]["lamp_enabled"] is True
    assert status_full["calibration"]["mirror_inserted"] is True
    assert status_full["detector_config"]["profile_name"] == "rgb-safe-default"

    assert calibration["mode"] == "calibration"
    assert calibration["active_lamp"] == "flat"

    assert observation["state"] == "armed"
    assert observation["armed_exposure"]["frame_type"] == "science"
    assert observation["observation_meta"] is not None
    assert observation["observation_meta"]["operator_note"] == "service-check"
    assert observation["observation_meta"]["detector_config"]["profile_name"] == "rgb-safe-default"

    assert exposure["state"] == "armed"
