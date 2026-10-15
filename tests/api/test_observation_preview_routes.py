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


def test_api_observation_preview_returns_side_effect_free_response() -> None:
    client = TestClient(app)

    before = client.get("/api/v1/observation/status").json()
    response = client.post(
        "/api/v1/observation/preview",
        json={
            "target_name": "Target A",
            "exposures": [
                {"frame_type": "science", "exp_time_s": 30.0},
            ],
            "operator_note": "preview only",
        },
    )
    after = client.get("/api/v1/observation/status").json()

    assert response.status_code == 200
    data = response.json()

    assert data["side_effect_free"] is True
    assert data["blocked"] is False
    assert data["single_exposure_compatible"] is True
    assert data["request"]["target_name"] == "Target A"
    assert data["request"]["operator_note"] == "preview only"
    assert data["request"]["exposures"] == [
        {"frame_type": "science", "exp_time_s": 30.0, "label": None}
    ]
    assert data["request"]["setup_context"] is not None
    assert data["readiness"]["detector"]["state"] == "ready"

    # Preview remains advisory and is not wrapped as command feedback.
    assert "command" not in data
    assert "ok" not in data
    assert "status" not in data

    assert before["state"] == "ready_to_arm"
    assert after["state"] == "ready_to_arm"
    assert after["armed_exposure"] is None


def test_api_observation_preview_preserves_explicit_setup_context() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/observation/preview",
        json={
            "exposures": [
                {"frame_type": "science", "exp_time_s": 30.0},
            ],
            "setup_context": {"root_name": "explicit"},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["request"]["setup_context"] == {"root_name": "explicit"}


def test_api_observation_preview_blocks_multiple_exposures_without_sequence_runner() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/observation/preview",
        json={
            "exposures": [
                {"frame_type": "science", "exp_time_s": 30.0},
                {"frame_type": "arc", "exp_time_s": 5.0},
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["side_effect_free"] is True
    assert data["blocked"] is True
    assert data["single_exposure_compatible"] is False
    assert [issue["code"] for issue in data["validation_issues"]] == [
        "multiple_exposures_not_supported"
    ]


def test_api_observation_preview_blocks_when_detector_is_already_armed() -> None:
    client = TestClient(app)

    arm = client.post(
        "/api/v1/observation/arm",
        json={"frame_type": "science", "exp_time_s": 5.0},
    )
    assert arm.status_code == 200
    arm_data = arm.json()
    assert arm_data["command"] == "arm"
    assert arm_data["ok"] is True

    response = client.post(
        "/api/v1/observation/preview",
        json={
            "exposures": [
                {"frame_type": "science", "exp_time_s": 30.0},
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["blocked"] is True
    assert data["single_exposure_compatible"] is False
    assert data["readiness"]["detector"]["state"] == "blocked"
    assert "command" not in data
    assert "ok" not in data

    status = client.get("/api/v1/observation/status").json()
    assert status["state"] == "armed"
    assert status["armed_exposure"] is not None


def test_api_observation_preview_openapi_response_is_typed() -> None:
    client = TestClient(app)

    data = client.get("/openapi.json").json()
    schema = data["paths"]["/api/v1/observation/preview"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]

    assert "$ref" in schema
    assert schema["$ref"].endswith("/ObservationPreviewResponse")
    assert "ObservationPreviewResponse" in data["components"]["schemas"]
