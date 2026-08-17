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


def _feedback_payload(data: dict, *, command: str) -> dict:
    assert data["command"] == command
    assert data["ok"] is True
    assert data["status"] == "succeeded"
    return data["details"]["payload"]


def test_api_observation_invalid_start_does_not_fault_runtime_state():
    client = TestClient(app)

    response = client.post("/api/v1/observation/start")
    assert response.status_code == 400
    data = response.json()
    assert data["command"] == "start"
    assert data["ok"] is False
    assert data["status"] == "failed"

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    data = health.json()

    runtime_state = data["runtime"]["state"]
    assert runtime_state["overall_state"] != "fault"
    assert runtime_state["subsystems"]["detector"]["state"] == "idle"
    assert runtime_state["exposure_state"] == "ready_to_arm"


def test_api_health_runtime_exposure_state_matches_observation_status_across_flow():
    client = TestClient(app)

    initial_health = client.get("/api/v1/health")
    initial_obs = client.get("/api/v1/observation/status")
    assert initial_health.status_code == 200
    assert initial_obs.status_code == 200
    assert initial_health.json()["runtime"]["state"]["exposure_state"] == initial_obs.json()["state"] == "ready_to_arm"

    arm = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 5.0, "frame_type": "science", "operator_note": "api-sync-check"},
    )
    assert arm.status_code == 200
    assert _feedback_payload(arm.json(), command="arm")["state"] == "armed"

    armed_health = client.get("/api/v1/health")
    armed_obs = client.get("/api/v1/observation/status")
    assert armed_health.status_code == 200
    assert armed_obs.status_code == 200
    assert armed_health.json()["runtime"]["state"]["exposure_state"] == armed_obs.json()["state"] == "armed"

    start = client.post("/api/v1/observation/start")
    assert start.status_code == 200
    assert _feedback_payload(start.json(), command="start")["state"] == "exposing"

    exposing_health = client.get("/api/v1/health")
    exposing_obs = client.get("/api/v1/observation/status")
    assert exposing_health.status_code == 200
    assert exposing_obs.status_code == 200
    assert exposing_health.json()["runtime"]["state"]["exposure_state"] == exposing_obs.json()["state"] == "exposing"

    finish = client.post("/api/v1/observation/finish")
    assert finish.status_code == 200
    assert _feedback_payload(finish.json(), command="finish")["state"] == "completed"

    completed_health = client.get("/api/v1/health")
    completed_obs = client.get("/api/v1/observation/status")
    assert completed_health.status_code == 200
    assert completed_obs.status_code == 200
    assert completed_health.json()["runtime"]["state"]["exposure_state"] == completed_obs.json()["state"] == "completed"


def test_armed_blocks_detector_config_mutation():
    client = TestClient(app)

    arm = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 5.0, "frame_type": "science", "operator_note": "lock-detector"},
    )
    assert arm.status_code == 200
    assert _feedback_payload(arm.json(), command="arm")["state"] == "armed"

    response = client.post(
        "/api/v1/detector/config",
        json={
            "profile_name": "locked-armed",
            "trigger_mode": "internal",
            "readout_mode": "normal",
            "channels": {
                "B": {"enabled": True, "camera_role": "science_b"},
                "G": {"enabled": True, "camera_role": "science_g"},
                "R": {"enabled": True, "camera_role": "science_r"},
            },
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_state"


def test_armed_blocks_preset_apply():
    client = TestClient(app)

    arm = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 5.0, "frame_type": "science", "operator_note": "lock-preset"},
    )
    assert arm.status_code == 200
    assert _feedback_payload(arm.json(), command="arm")["state"] == "armed"

    response = client.post("/api/v1/presets/apply", json={"name": "science_default"})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_state"


def test_armed_blocks_slit_and_calibration_mutation():
    client = TestClient(app)

    arm = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 5.0, "frame_type": "science", "operator_note": "lock-slit-cal"},
    )
    assert arm.status_code == 200
    assert _feedback_payload(arm.json(), command="arm")["state"] == "armed"

    slit = client.post("/api/v1/slit", json={"width_um": 140.0})
    assert slit.status_code == 400
    assert slit.json()["detail"]["code"] == "invalid_state"

    calibration = client.post("/api/v1/calibration/mode", json={"mode": "calibration"})
    assert calibration.status_code == 400
    assert calibration.json()["detail"]["code"] == "invalid_state"


def test_armed_still_allows_observation_start():
    client = TestClient(app)

    arm = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 5.0, "frame_type": "science", "operator_note": "start-still-allowed"},
    )
    assert arm.status_code == 200

    start = client.post("/api/v1/observation/start")
    assert start.status_code == 200
    assert _feedback_payload(start.json(), command="start")["state"] == "exposing"


def test_exposing_blocks_detector_preset_and_slit_mutation():
    client = TestClient(app)

    arm = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 5.0, "frame_type": "science", "operator_note": "lock-exposing"},
    )
    assert arm.status_code == 200

    start = client.post("/api/v1/observation/start")
    assert start.status_code == 200
    assert _feedback_payload(start.json(), command="start")["state"] == "exposing"

    detector = client.post(
        "/api/v1/detector/config",
        json={
            "profile_name": "locked-exposing",
            "trigger_mode": "internal",
            "readout_mode": "normal",
            "channels": {
                "B": {"enabled": True, "camera_role": "science_b"},
                "G": {"enabled": True, "camera_role": "science_g"},
                "R": {"enabled": True, "camera_role": "science_r"},
            },
        },
    )
    assert detector.status_code == 400
    assert detector.json()["detail"]["code"] == "invalid_state"

    preset = client.post("/api/v1/presets/apply", json={"name": "science_default"})
    assert preset.status_code == 400
    assert preset.json()["detail"]["code"] == "invalid_state"

    slit = client.post("/api/v1/slit", json={"width_um": 150.0})
    assert slit.status_code == 400
    assert slit.json()["detail"]["code"] == "invalid_state"


def test_exposing_still_allows_observation_finish():
    client = TestClient(app)

    arm = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 5.0, "frame_type": "science", "operator_note": "finish-still-allowed"},
    )
    assert arm.status_code == 200

    start = client.post("/api/v1/observation/start")
    assert start.status_code == 200
    assert _feedback_payload(start.json(), command="start")["state"] == "exposing"

    finish = client.post("/api/v1/observation/finish")
    assert finish.status_code == 200
    assert _feedback_payload(finish.json(), command="finish")["state"] == "completed"
