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


def test_api_observation_arm_rejected_when_preview_blocks_calibration_mismatch() -> None:
    client = TestClient(app)

    lamp = client.post(
        "/api/v1/calibration/lamp",
        json={"lamp": "flat", "enabled": True},
    )
    assert lamp.status_code == 200

    response = client.post(
        "/api/v1/observation/arm",
        json={"frame_type": "science", "exp_time_s": 30.0},
    )

    assert response.status_code == 400
    data = response.json()

    assert data["command"] == "arm"
    assert data["ok"] is False
    assert data["status"] == "blocked"
    assert data["blocked"] is True
    assert data["blocked_reason"] == "readiness_gate"
    assert data["error"]["code"] == "interlock_blocked"
    assert data["error"]["details"]["preview"]["blocked"] is True
    assert data["error"]["details"]["preview"]["single_exposure_compatible"] is False
    assert data["blocked_components"] == ["calibration"]
    assert data["details"]["blocked_components"] == ["calibration"]
    assert data["details"]["validation_issue_codes"] == [
        "science_calibration_not_ready"
    ]
    assert data["preview"]["blocked"] is True
    assert data["preview"]["single_exposure_compatible"] is False
    assert [issue["code"] for issue in data["validation_issues"]] == [
        "science_calibration_not_ready"
    ]

    status = client.get("/api/v1/observation/status").json()
    assert status["state"] == "ready_to_arm"
    assert status["armed_exposure"] is None


def test_api_observation_arm_rejected_when_detector_is_already_armed() -> None:
    client = TestClient(app)

    first = client.post(
        "/api/v1/observation/arm",
        json={"frame_type": "science", "exp_time_s": 5.0},
    )
    assert first.status_code == 200
    first_data = first.json()
    assert first_data["command"] == "arm"
    assert first_data["ok"] is True
    assert first_data["status"] == "succeeded"

    second = client.post(
        "/api/v1/observation/arm",
        json={"frame_type": "science", "exp_time_s": 30.0},
    )

    assert second.status_code == 400
    data = second.json()

    assert data["command"] == "arm"
    assert data["ok"] is False
    assert data["status"] == "blocked"
    assert data["blocked"] is True
    assert data["blocked_reason"] == "readiness_gate"
    assert data["error"]["code"] == "interlock_blocked"
    assert data["preview"]["readiness"]["detector"]["state"] == "blocked"
    assert data["blocked_components"] == ["detector"]
    assert data["details"]["blocked_components"] == ["detector"]
    assert data["details"]["validation_issue_codes"] == []
    assert data["validation_issues"] == []

    status = client.get("/api/v1/observation/status").json()
    assert status["state"] == "armed"
    assert status["armed_exposure"]["exp_time_s"] == 5.0
