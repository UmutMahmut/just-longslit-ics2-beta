from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from justls.ics.app.main import app
from justls.ics.kernel.runtime import reset_runtime


@pytest.fixture(autouse=True)
def _reset_runtime_singleton():
    reset_runtime()
    yield
    reset_runtime()


def _plan_payload() -> dict:
    return {
        "plan_id": "plan-api",
        "target_name": "Vega",
        "operator_note": "api sequence",
        "exposures": [
            {"frame_type": "science", "exp_time_s": 1, "label": "one"},
            {"frame_type": "science", "exp_time_s": 2, "label": "two"},
        ],
    }


def test_sequence_preview_does_not_load_or_arm() -> None:
    client = TestClient(app)

    response = client.post("/api/v1/observation/sequence/preview", json=_plan_payload())
    assert response.status_code == 200
    data = response.json()
    assert data["side_effect_free"] is True
    assert data["executable"] is True
    assert len(data["steps"]) == 2

    assert client.get("/api/v1/observation/sequence/status").json() is None
    assert client.get("/api/v1/observation/status").json()["state"] == "ready_to_arm"


def test_sequence_api_runs_multiple_exposures_with_request_ids() -> None:
    client = TestClient(app)
    headers = {"X-Request-ID": "sequence-api-request"}

    loaded = client.post(
        "/api/v1/observation/sequence/load",
        json=_plan_payload(),
        headers=headers,
    )
    assert loaded.status_code == 200
    assert loaded.headers["X-Request-ID"] == "sequence-api-request"
    assert loaded.json()["request_id"] == "sequence-api-request"
    assert loaded.json()["sequence"]["state"] == "loaded"

    for index in range(2):
        started = client.post("/api/v1/observation/sequence/start")
        assert started.status_code == 200
        assert started.json()["sequence"]["active_exposure"] is True

        finished = client.post("/api/v1/observation/sequence/finish_step")
        assert finished.status_code == 200
        assert len(finished.json()["sequence"]["step_results"]) == index + 1

    status = client.get("/api/v1/observation/sequence/status")
    assert status.status_code == 200
    assert status.json()["state"] == "completed"
    assert status.json()["current_index"] == 2
    assert status.json()["total_steps"] == 2
    assert status.json()["completed_steps"] == 2


def test_sequence_api_reports_invalid_transition_as_structured_feedback() -> None:
    client = TestClient(app)

    response = client.post("/api/v1/observation/sequence/start")

    assert response.status_code == 400
    data = response.json()
    assert data["command"] == "start"
    assert data["ok"] is False
    assert data["status"] == "failed"
    assert data["error"]["code"] == "invalid_state"
    assert data["latest_job"]["status"] == "failed"


def test_sequence_api_pause_resume_and_abort_are_audited() -> None:
    client = TestClient(app)
    assert client.post("/api/v1/observation/sequence/load", json=_plan_payload()).status_code == 200

    paused = client.post("/api/v1/observation/sequence/pause")
    assert paused.status_code == 200
    assert paused.json()["sequence"]["state"] == "paused"
    assert paused.json()["latest_job"]["request"]["action"] == "pause"

    resumed = client.post("/api/v1/observation/sequence/resume")
    assert resumed.status_code == 200
    assert resumed.json()["sequence"]["state"] == "running"

    aborted = client.post("/api/v1/observation/sequence/abort")
    assert aborted.status_code == 200
    assert aborted.json()["sequence"]["state"] == "aborted"
    assert aborted.json()["sequence"]["step_results"] == []


def test_sequence_load_reports_blocked_calibration_step() -> None:
    client = TestClient(app)
    payload = _plan_payload()
    payload["exposures"] = [{"frame_type": "flat", "exp_time_s": 2}]

    response = client.post("/api/v1/observation/sequence/load", json=payload)

    assert response.status_code == 400
    data = response.json()
    assert data["status"] == "blocked"
    assert data["error"]["code"] == "interlock_blocked"
    assert data["error"]["details"]["blocked_steps"] == [0]


def test_active_sequence_owns_detector_command_path() -> None:
    client = TestClient(app)
    assert client.post("/api/v1/observation/sequence/load", json=_plan_payload()).status_code == 200

    direct = client.post(
        "/api/v1/observation/arm",
        json={"frame_type": "science", "exp_time_s": 3},
    )

    assert direct.status_code == 400
    data = direct.json()
    assert data["status"] == "blocked"
    assert data["error"]["code"] == "interlock_blocked"
    assert data["error"]["details"]["use_sequence_commands"] is True
