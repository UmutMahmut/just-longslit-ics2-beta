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


def test_management_service_detector_config_roundtrip():
    runtime = RuntimeAssembler().build()
    service = ManagementService(runtime)

    default_cfg = service.get_detector_config_dict()
    assert default_cfg["profile_name"] == "campus-beta-shared-camera"
    assert default_cfg["shared_physical_camera"] is True

    updated = service.set_detector_config(
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

    assert updated["profile_name"] == "rgb-safe-default"
    assert updated["channels"]["B"]["enabled"] is True
    assert service.get_detector_config_dict()["channels"]["R"]["enabled"] is True

def test_management_service_apply_preset_plan_science():
    runtime = RuntimeAssembler().build()
    service = ManagementService(runtime)

    plan = build_preset_plan("science_default")
    result = service.apply_preset_plan(plan)

    assert result["applied_preset"] == "science_default"
    assert result["detector_config"]["profile_name"] == "science-default"
    assert result["calibration"]["mode"] == "science"
    assert result["calibration_applied"] is True
    assert result["slit_applied"] is False

def test_management_service_apply_preset_plan_calib_flat():
    runtime = RuntimeAssembler().build()
    service = ManagementService(runtime)

    plan = build_preset_plan("calib_flat_default")
    result = service.apply_preset_plan(plan)

    assert result["applied_preset"] == "calib_flat_default"
    assert result["detector_config"]["profile_name"] == "calib-flat-default"
    assert result["calibration"]["mode"] == "calibration"
    assert result["calibration"]["active_lamp"] == "flat"
    assert result["calibration"]["lamp_enabled"] is True
    assert result["calibration_applied"] is True
    assert result["slit_applied"] is False
