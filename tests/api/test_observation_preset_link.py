import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath("src"))

from justls.ics.app.main import app
from justls.ics.kernel.runtime import reset_runtime


def setup_function():
    reset_runtime()


def teardown_function():
    reset_runtime()


def _feedback_payload(data: dict) -> dict:
    assert data["ok"] is True
    assert data["status"] == "succeeded"
    return data["details"]["payload"]


def test_observation_arm_records_latest_successful_preset_apply():
    client = TestClient(app)

    applied = client.post(
        "/api/v1/presets/apply",
        json={"name": "calib_flat_default", "confirmed": True},
    )
    assert applied.status_code == 200
    apply_data = applied.json()

    armed = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 5.0, "frame_type": "flat", "operator_note": "preset-link"},
    )
    assert armed.status_code == 200
    data = armed.json()
    assert data["command"] == "arm"
    meta = _feedback_payload(data)["observation_meta"]

    assert meta["preset_apply"]["job_id"] == apply_data["job_id"]
    assert meta["preset_apply"]["preset"] == "calib_flat_default"
    assert meta["preset_apply"]["category"] == "calibration"
    assert meta["preset_apply"]["risk_level"] == "high_impact"
    assert meta["preset_apply"]["requires_confirmation"] is True
    assert meta["preset_apply"]["changed_fields_count"] == len(apply_data["changed_fields"])
    assert meta["preset_apply"]["calibration_applied"] is True
    assert meta["preset_apply"]["slit_applied"] is False


def test_observation_arm_without_prior_preset_has_null_preset_reference():
    client = TestClient(app)

    armed = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 5.0, "frame_type": "science", "operator_note": "no-preset"},
    )
    assert armed.status_code == 200
    data = armed.json()
    assert data["command"] == "arm"
    meta = _feedback_payload(data)["observation_meta"]

    assert meta["preset_apply"] is None


def test_status_full_observation_meta_exposes_preset_reference():
    client = TestClient(app)

    applied = client.post(
        "/api/v1/presets/apply",
        json={"name": "calib_flat_default", "confirmed": True},
    )
    assert applied.status_code == 200
    apply_data = applied.json()

    armed = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 6.0, "frame_type": "flat", "operator_note": "status-preset-link"},
    )
    assert armed.status_code == 200
    data = armed.json()
    assert data["command"] == "arm"
    assert data["ok"] is True

    status = client.get("/api/v1/status/full")
    assert status.status_code == 200
    meta = status.json()["observation"]["observation_meta"]

    assert meta["preset_apply"]["job_id"] == apply_data["job_id"]
    assert meta["preset_apply"]["preset"] == "calib_flat_default"
    assert meta["preset_apply"]["category"] == "calibration"
    assert meta["preset_apply"]["risk_level"] == "high_impact"


def test_api_observation_arm_reflects_applied_calib_preset():
    client = TestClient(app)

    preset = client.post(
        "/api/v1/presets/apply",
        json={"name": "calib_flat_default", "confirmed": True},
    )
    assert preset.status_code == 200

    response = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 6.0, "frame_type": "flat", "operator_note": "preset-calib-link"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["command"] == "arm"
    payload = _feedback_payload(data)

    assert payload["observation_meta"]["detector_config"]["profile_name"] == "calib-flat-default"
    assert payload["observation_meta"]["calibration_snapshot"]["mode"] == "calibration"
    assert payload["observation_meta"]["calibration_snapshot"]["active_lamp"] == "flat"
    assert payload["observation_meta"]["calibration_snapshot"]["lamp_enabled"] is True


def test_api_status_full_reflects_observation_meta_and_detector_config():
    client = TestClient(app)

    client.post(
        "/api/v1/presets/apply",
        json={"name": "calib_flat_default", "confirmed": True},
    )

    arm = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 8.0, "frame_type": "flat", "operator_note": "full-status-check"},
    )
    assert arm.status_code == 200
    data = arm.json()
    assert data["command"] == "arm"
    assert data["ok"] is True

    response = client.get("/api/v1/status/full")
    assert response.status_code == 200
    data = response.json()

    assert data["observation"]["state"] == "armed"
    assert data["observation"]["armed_exposure"] is not None
    assert data["observation"]["last_exposure"] is None
    assert data["observation"]["observation_meta"] is not None
    assert data["observation"]["observation_meta"]["operator_note"] == "full-status-check"
    assert data["observation"]["observation_meta"]["detector_config"]["profile_name"] == "calib-flat-default"
    assert data["observation"]["observation_meta"]["calibration_snapshot"]["mode"] == "calibration"
    assert data["observation"]["observation_meta"]["calibration_snapshot"]["active_lamp"] == "flat"
    assert data["detector_config"]["profile_name"] == "calib-flat-default"
