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


def _assert_command_succeeded(data: dict, command: str) -> dict:
    assert data["command"] == command
    assert data["ok"] is True
    assert data["status"] == "succeeded"
    assert data["blocked"] is False
    assert data["error"] is None
    return data["details"]["payload"]


def _assert_command_failed(data: dict, command: str) -> None:
    assert data["command"] == command
    assert data["ok"] is False
    assert data["status"] == "failed"
    assert data["blocked"] is False
    assert data["error"]["code"] == "invalid_state"
    assert data["error"]["message"] != "Observation command dispatch failed."
    assert data["error"]["details"]["payload"]["error"]["code"] == "invalid_state"


def test_api_observation_initial_status():
    client = TestClient(app)

    response = client.get("/api/v1/observation/status")
    assert response.status_code == 200
    data = response.json()

    assert data["state"] == "ready_to_arm"
    assert data["armed_exposure"] is None
    assert data["last_exposure"] is None
    assert data["observation_meta"] is None


def test_api_observation_arm_includes_detector_config():
    client = TestClient(app)

    client.post(
        "/api/v1/detector/config",
        json={
            "profile_name": "rgb-safe-default",
            "trigger_mode": "internal",
            "readout_mode": "normal",
            "channels": {
                "B": {"enabled": True, "camera_role": "science_b"},
                "G": {"enabled": False, "camera_role": "science_g"},
                "R": {"enabled": True, "camera_role": "science_r"},
            },
        },
    )

    response = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 15.0, "frame_type": "science", "operator_note": "detector-config-link"},
    )
    assert response.status_code == 200
    data = response.json()
    payload = _assert_command_succeeded(data, "arm")

    assert data["observation_state"] == "armed"
    assert payload["state"] == "armed"
    assert payload["armed_exposure"] is not None
    assert payload["armed_exposure"]["operator_note"] == "detector-config-link"
    assert payload["observation_meta"] is not None
    assert payload["observation_meta"]["detector_config"]["profile_name"] == "rgb-safe-default"
    assert payload["observation_meta"]["detector_config"]["channels"]["B"]["enabled"] is True
    assert payload["observation_meta"]["detector_config"]["channels"]["G"]["enabled"] is False
    assert payload["observation_meta"]["detector_config"]["channels"]["R"]["enabled"] is True


def test_api_observation_start_returns_exposing():
    client = TestClient(app)

    arm = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 20.0, "frame_type": "science", "operator_note": "api-meta-check"},
    )
    assert arm.status_code == 200

    response = client.post("/api/v1/observation/start")
    assert response.status_code == 200
    data = response.json()
    payload = _assert_command_succeeded(data, "start")

    assert data["observation_state"] == "exposing"
    assert payload["state"] == "exposing"
    assert payload["armed_exposure"] is not None
    assert payload["armed_exposure"]["frame_type"] == "science"
    assert payload["last_exposure"] is None
    assert payload["observation_meta"] is not None
    assert payload["observation_meta"]["state"] == "exposing"
    assert payload["observation_meta"]["started_at_utc"] is not None


def test_api_observation_finish():
    client = TestClient(app)

    arm = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 20.0, "frame_type": "science", "operator_note": "api-meta-check"},
    )
    assert arm.status_code == 200

    start = client.post("/api/v1/observation/start")
    assert start.status_code == 200

    response = client.post("/api/v1/observation/finish")
    assert response.status_code == 200
    data = response.json()
    payload = _assert_command_succeeded(data, "finish")

    assert data["observation_state"] == "completed"
    assert payload["state"] == "completed"
    assert payload["armed_exposure"] is None
    assert payload["last_exposure"] is not None
    assert payload["last_exposure"]["frame_type"] == "science"
    assert payload["last_exposure"]["kept"] is True
    assert payload["last_exposure"]["early_stop"] is False
    assert payload["last_exposure"]["discarded"] is False
    assert payload["observation_meta"] is not None
    assert payload["observation_meta"]["state"] == "completed"
    assert len(payload["observation_meta"]["frame_results"]) == 1
    assert payload["observation_meta"]["frame_results"][0]["kept"] is True
    assert payload["observation_meta"]["frame_results"][0]["early_stop"] is False
    assert payload["latest_exposure_record"]["save_requested"] is False
    assert payload["latest_exposure_record"]["data_product_state"] == "not_requested"


def test_api_saved_single_exposure_consumes_one_frame_index() -> None:
    client = TestClient(app)
    setup = client.put(
        "/api/v1/setup/context",
        json={"root_name": "science", "date_prefix": "20260817", "next_frame_index": 10},
    )
    assert setup.status_code == 200

    unsaved_arm = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 0.1, "frame_type": "test"},
    )
    assert unsaved_arm.status_code == 200
    assert client.get("/api/v1/setup/context").json()["next_frame_index"] == 10
    assert client.post("/api/v1/observation/start").status_code == 200
    assert client.post("/api/v1/observation/finish").status_code == 200

    saved_arm = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 0.1, "frame_type": "science", "save_requested": True},
    )
    assert saved_arm.status_code == 200
    saved_payload = saved_arm.json()["details"]["payload"]
    assert saved_payload["armed_exposure"]["save_requested"] is True
    assert saved_payload["observation_meta"]["data_preview"]["file_stem"] == "science_20260817_0010"
    assert client.get("/api/v1/setup/context").json()["next_frame_index"] == 11
    assert client.post("/api/v1/observation/start").status_code == 200
    finished = client.post("/api/v1/observation/finish").json()["details"]["payload"]
    assert finished["latest_exposure_record"]["data_product_state"] == "available"


def test_api_observation_stop_readout():
    client = TestClient(app)

    arm = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 8.0, "frame_type": "science", "operator_note": "early-stop-case"},
    )
    assert arm.status_code == 200

    start = client.post("/api/v1/observation/start")
    assert start.status_code == 200

    response = client.post("/api/v1/observation/stop_readout")
    assert response.status_code == 200
    data = response.json()
    payload = _assert_command_succeeded(data, "stop_readout")

    assert data["observation_state"] == "completed"
    assert payload["state"] == "completed"
    assert payload["armed_exposure"] is None
    assert payload["last_exposure"] is not None
    assert payload["last_exposure"]["frame_type"] == "science"
    assert payload["last_exposure"]["kept"] is True
    assert payload["last_exposure"]["early_stop"] is True
    assert payload["last_exposure"]["discarded"] is False
    assert payload["observation_meta"] is not None
    assert payload["observation_meta"]["state"] == "completed"
    assert len(payload["observation_meta"]["frame_results"]) == 1
    assert payload["observation_meta"]["frame_results"][0]["kept"] is True
    assert payload["observation_meta"]["frame_results"][0]["early_stop"] is True


def test_api_observation_abort_discard():
    client = TestClient(app)

    arm = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 10.0, "frame_type": "science", "operator_note": "discard-case"},
    )
    assert arm.status_code == 200

    response = client.post("/api/v1/observation/abort_discard")
    assert response.status_code == 200
    data = response.json()
    payload = _assert_command_succeeded(data, "abort_discard")

    assert data["observation_state"] == "discarded"
    assert payload["state"] == "discarded"
    assert payload["armed_exposure"] is None
    assert payload["last_exposure"] is not None
    assert payload["last_exposure"]["frame_type"] == "science"
    assert payload["last_exposure"]["kept"] is False
    assert payload["last_exposure"]["early_stop"] is False
    assert payload["last_exposure"]["discarded"] is True
    assert payload["observation_meta"] is not None
    assert payload["observation_meta"]["state"] == "discarded"
    assert len(payload["observation_meta"]["frame_results"]) == 1
    assert payload["observation_meta"]["frame_results"][0]["discarded"] is True


def test_api_observation_invalid_start_before_arm():
    client = TestClient(app)

    response = client.post("/api/v1/observation/start")
    assert response.status_code == 400
    _assert_command_failed(response.json(), "start")


def test_api_observation_invalid_finish_before_start():
    client = TestClient(app)

    arm = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 5.0, "frame_type": "science", "operator_note": "bad-finish"},
    )
    assert arm.status_code == 200

    response = client.post("/api/v1/observation/finish")
    assert response.status_code == 400
    _assert_command_failed(response.json(), "finish")


def test_api_observation_invalid_stop_before_start():
    client = TestClient(app)

    response = client.post("/api/v1/observation/stop_readout")
    assert response.status_code == 400
    _assert_command_failed(response.json(), "stop_readout")


def test_api_observation_invalid_abort_before_arm():
    client = TestClient(app)

    response = client.post("/api/v1/observation/abort_discard")
    assert response.status_code == 400
    _assert_command_failed(response.json(), "abort_discard")
