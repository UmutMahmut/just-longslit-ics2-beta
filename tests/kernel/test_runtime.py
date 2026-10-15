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


def test_runtime_status_dict():
    runtime = RuntimeAssembler(RuntimeConfig(run_mode=RunMode.SIM)).build()
    status = runtime.status_dict()

    assert status["app_name"] == "ICS Beta"
    assert status["version"] == "0.1.0"
    assert status["run_mode"] == "sim"
    assert status["latest_job"] is None

def test_runtime_has_slit_lamps_detector_and_capabilities():
    runtime = RuntimeAssembler().build()
    caps = runtime.get_capabilities_dict()

    assert runtime.slit is not None
    assert runtime.lamps is not None
    assert runtime.detector is not None
    assert caps["slit"] is True
    assert caps["slit_angle"] is True
    assert caps["calib_lamps"] is True
    assert caps["slit_monitor_camera"] is True
    assert caps["science_channels_bgr"] is True

def test_runtime_default_detector_config_exists():
    runtime = RuntimeAssembler().build()
    cfg = runtime.get_detector_config_dict()

    assert cfg["profile_name"] == "campus-beta-shared-camera"
    assert "save_enabled" not in cfg
    assert cfg["trigger_mode"] == "simulated"
    assert cfg["readout_mode"] == "normal"
    assert cfg["shared_physical_camera"] is True
    assert "channels" in cfg
    assert set(cfg["channels"].keys()) == {"B", "G", "R"}
    assert all(channel["enabled"] for channel in cfg["channels"].values())
    assert {
        channel["source_camera_id"] for channel in cfg["channels"].values()
    } == {"science-camera-01"}

def test_runtime_can_update_detector_config():
    runtime = RuntimeAssembler().build()

    updated = runtime.set_detector_config(
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

    assert updated.profile_name == "rgb-safe-default"
    cfg = runtime.get_detector_config_dict()
    assert cfg["channels"]["B"]["enabled"] is True
    assert cfg["channels"]["G"]["enabled"] is False
    assert cfg["channels"]["R"]["enabled"] is True

def test_runtime_can_update_subsystem_state():
    runtime = RuntimeAssembler().build()

    runtime.set_subsystem_connected("slit", True, message="connected")
    runtime.set_subsystem_state("slit", ControlState.IDLE, message="ready")

    slit = runtime.get_subsystem_state("slit")
    assert slit.connected is True
    assert slit.state == ControlState.IDLE
    assert slit.message == "ready"

def test_runtime_snapshot_exposure_state_is_derived_from_detector():
    runtime = RuntimeAssembler().build()

    runtime.detector.arm(
        exp_time_s=5.0,
        frame_type="science",
        operator_note="derive-check",
        instrument_snapshot=None,
        calibration_snapshot=None,
        detector_config=runtime.get_detector_config_dict(),
    )

    runtime_snapshot = runtime.get_snapshot()
    detector_snapshot = runtime.detector.get_snapshot()

    assert runtime_snapshot.exposure_state == detector_snapshot.state
    assert runtime_snapshot.exposure_state.value == "armed"

def test_runtime_snapshot_exposure_state_tracks_detector_after_start_and_finish():
    runtime = RuntimeAssembler().build()

    runtime.detector.arm(
        exp_time_s=5.0,
        frame_type="science",
        operator_note="derive-check",
        instrument_snapshot=None,
        calibration_snapshot=None,
        detector_config=runtime.get_detector_config_dict(),
    )
    runtime.detector.start()

    runtime_snapshot = runtime.get_snapshot()
    detector_snapshot = runtime.detector.get_snapshot()
    assert runtime_snapshot.exposure_state == detector_snapshot.state
    assert runtime_snapshot.exposure_state.value == "exposing"

    runtime.detector.finish_normal()

    runtime_snapshot = runtime.get_snapshot()
    detector_snapshot = runtime.detector.get_snapshot()
    assert runtime_snapshot.exposure_state == detector_snapshot.state
    assert runtime_snapshot.exposure_state.value == "completed"
