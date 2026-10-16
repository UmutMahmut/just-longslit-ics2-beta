from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from justls.ics.app.main import app
from justls.ics.kernel.runtime import reset_runtime


@pytest.fixture(autouse=True)
def _reset_runtime_singleton():
    reset_runtime()
    yield
    reset_runtime()


def _plan_payload(*, save_requested: bool = False) -> dict:
    return {
        "plan_id": "plan-api",
        "target_name": "Vega",
        "operator_note": "api sequence",
        "save_requested": save_requested,
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
    assert loaded.json()["sequence"]["frame_reservation"] is None

    for index in range(2):
        started = client.post("/api/v1/observation/sequence/start")
        assert started.status_code == 200
        assert started.json()["sequence"]["active_exposure"] is True

        finished = client.post("/api/v1/observation/sequence/finish_step")
        assert finished.status_code == 200
        assert len(finished.json()["sequence"]["step_results"]) == index + 1
        assert finished.json()["sequence"]["step_results"][-1]["exposure_record"]["data_product_state"] == "not_requested"

    status = client.get("/api/v1/observation/sequence/status")
    assert status.status_code == 200
    assert status.json()["state"] == "completed"
    assert status.json()["current_index"] == 2
    assert status.json()["total_steps"] == 2
    assert status.json()["completed_steps"] == 2


def test_saved_sequence_reserves_its_complete_file_range() -> None:
    client = TestClient(app)
    assert client.put(
        "/api/v1/setup/context",
        json={"root_name": "science", "date_prefix": "20260817", "next_frame_index": 4},
    ).status_code == 200

    loaded = client.post(
        "/api/v1/observation/sequence/load",
        json=_plan_payload(save_requested=True),
    )

    assert loaded.status_code == 200
    reservation = loaded.json()["sequence"]["frame_reservation"]
    assert reservation["start_index"] == 4
    assert reservation["end_index_exclusive"] == 6
    assert client.get("/api/v1/setup/context").json()["next_frame_index"] == 6


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


def test_sequence_api_restores_interrupted_step_and_requires_explicit_retry() -> None:
    client = TestClient(app)
    assert client.post(
        "/api/v1/observation/sequence/load", json=_plan_payload()
    ).status_code == 200
    started = client.post("/api/v1/observation/sequence/start")
    assert started.status_code == 200
    assert started.json()["sequence"]["active_step"]["phase"] == "exposing"

    reset_runtime()
    restored = client.get("/api/v1/observation/sequence/status")

    assert restored.status_code == 200
    assert restored.json()["state"] == "recovery_required"
    assert restored.json()["active_exposure"] is False
    assert restored.json()["recovery"]["retry_allowed"] is True

    retry = client.post("/api/v1/observation/sequence/retry_current_step")
    assert retry.status_code == 200
    assert retry.json()["sequence"]["state"] == "loaded"
    assert retry.json()["sequence"]["recovery"] is None
    assert retry.json()["latest_job"]["request"]["action"] == "retry_current_step"


def test_sequence_api_blocks_retry_when_recovery_finds_possible_fits() -> None:
    client = TestClient(app)
    assert client.post(
        "/api/v1/observation/sequence/load", json=_plan_payload()
    ).status_code == 200
    started = client.post("/api/v1/observation/sequence/start").json()["sequence"]
    exp_id = started["active_step"]["exp_id"]
    data_root = Path(os.environ["ICS_BETA_DATA_ROOT"])
    possible = data_root / "20260817" / "possible" / f"{exp_id}-possible.fits"
    possible.parent.mkdir(parents=True, exist_ok=True)
    possible.write_bytes(b"possible fits")

    reset_runtime()
    restored = client.get("/api/v1/observation/sequence/status").json()
    assert restored["state"] == "recovery_required"
    assert restored["recovery"]["retry_allowed"] is False

    retry = client.post("/api/v1/observation/sequence/retry_current_step")
    assert retry.status_code == 400
    assert retry.json()["error"]["code"] == "invalid_state"

    failed = client.post("/api/v1/observation/sequence/mark_failed")
    assert failed.status_code == 200
    assert failed.json()["sequence"]["state"] == "failed"


def test_corrupt_durable_sequence_state_blocks_direct_exposure_commands() -> None:
    state_path = Path(os.environ["JUSTLS_SEQUENCE_STATE_PATH"])
    state_path.write_text("{not valid json", encoding="utf-8")
    reset_runtime()
    client = TestClient(app)

    response = client.post(
        "/api/v1/observation/arm",
        json={"frame_type": "science", "exp_time_s": 1},
    )

    assert response.status_code == 400
    data = response.json()
    assert data["status"] == "blocked"
    assert data["error"]["code"] == "interlock_blocked"
    assert "sequence_persistence_error" in data["error"]["details"]


def test_sequence_api_preserves_auto_advance_option() -> None:
    client = TestClient(app)
    payload = _plan_payload()
    payload["auto_advance"] = True
    loaded = client.post("/api/v1/observation/sequence/load", json=payload)
    assert loaded.status_code == 200
    assert loaded.json()["sequence"]["plan"]["auto_advance"] is True
    assert client.post("/api/v1/observation/sequence/start").json()["ok"]
    completed = client.post("/api/v1/observation/sequence/finish_step").json()
    assert completed["ok"]
    assert completed["sequence"]["current_index"] == 1
    assert completed["sequence"]["active_exposure"]
    assert client.post("/api/v1/observation/sequence/abort").json()["ok"]
