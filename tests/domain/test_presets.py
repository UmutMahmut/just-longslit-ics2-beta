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


def test_presets_catalog():
    items = list_presets()
    names = {item["name"] for item in items}

    assert "science_default" in names
    assert "rgb_safe_default" in names
    assert "engineering_all_channels_off" in names
    assert "calib_flat_default" in names

def test_build_preset_plan_science_default():
    plan = build_preset_plan("science_default").to_dict()

    assert plan["name"] == "science_default"
    assert plan["detector_config"]["profile_name"] == "science-default"
    assert plan["calibration"]["mode"] == "science"
    assert plan["calibration"]["enabled"] is False
    assert plan["slit"] is None

def test_build_preset_plan_calib_flat_default():
    plan = build_preset_plan("calib_flat_default").to_dict()

    assert plan["name"] == "calib_flat_default"
    assert plan["detector_config"]["profile_name"] == "calib-flat-default"
    assert plan["calibration"]["mode"] == "calibration"
    assert plan["calibration"]["lamp"] == "flat"
    assert plan["calibration"]["enabled"] is True

def test_build_preset_config_science_default():
    cfg = build_preset_config("science_default").to_dict()

    assert cfg["profile_name"] == "science-default"
    assert cfg["channels"]["B"]["enabled"] is True
    assert cfg["channels"]["G"]["enabled"] is True
    assert cfg["channels"]["R"]["enabled"] is True

def test_build_unknown_preset_raises():
    with pytest.raises(KeyError):
        build_preset_plan("not_exists")
