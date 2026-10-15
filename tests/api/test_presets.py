# Consolidated preset API contract tests.

# Source: test_presets_metadata.py
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath("src"))

from justls.ics.application.usecases.presets import build_preset_plan, list_presets
from justls.ics.app.main import app
from justls.ics.kernel.runtime import reset_runtime


def setup_function():
    reset_runtime()


def teardown_function():
    reset_runtime()


def test_builtin_preset_plans_include_operational_metadata():
    science = build_preset_plan("science_default")
    rgb_safe = build_preset_plan("rgb_safe_default")
    engineering = build_preset_plan("engineering_all_channels_off")
    flat = build_preset_plan("calib_flat_default")

    assert science.category == "science"
    assert science.risk_level == "normal"
    assert science.requires_confirmation is False

    assert rgb_safe.category == "science"
    assert rgb_safe.risk_level == "normal"
    assert rgb_safe.requires_confirmation is False

    assert engineering.category == "engineering"
    assert engineering.risk_level == "engineering"
    assert engineering.requires_confirmation is True

    assert flat.category == "calibration"
    assert flat.risk_level == "high_impact"
    assert flat.requires_confirmation is True


def test_list_presets_exposes_metadata_without_full_payloads():
    items = list_presets()
    by_name = {item["name"]: item for item in items}

    assert by_name["science_default"]["category"] == "science"
    assert by_name["science_default"]["risk_level"] == "normal"
    assert by_name["science_default"]["requires_confirmation"] is False

    assert by_name["calib_flat_default"]["category"] == "calibration"
    assert by_name["calib_flat_default"]["risk_level"] == "high_impact"
    assert by_name["calib_flat_default"]["requires_confirmation"] is True

    assert by_name["engineering_all_channels_off"]["category"] == "engineering"
    assert by_name["engineering_all_channels_off"]["risk_level"] == "engineering"
    assert by_name["engineering_all_channels_off"]["requires_confirmation"] is True

    assert "detector_config" not in by_name["science_default"]
    assert "calibration" not in by_name["science_default"]


def test_presets_api_exposes_operational_metadata():
    client = TestClient(app)

    response = client.get("/api/v1/presets")

    assert response.status_code == 200
    data = response.json()
    by_name = {item["name"]: item for item in data["items"]}

    assert by_name["science_default"]["category"] == "science"
    assert by_name["science_default"]["risk_level"] == "normal"
    assert by_name["science_default"]["requires_confirmation"] is False

    assert by_name["calib_flat_default"]["category"] == "calibration"
    assert by_name["calib_flat_default"]["risk_level"] == "high_impact"
    assert by_name["calib_flat_default"]["requires_confirmation"] is True

    assert by_name["engineering_all_channels_off"]["category"] == "engineering"
    assert by_name["engineering_all_channels_off"]["risk_level"] == "engineering"
    assert by_name["engineering_all_channels_off"]["requires_confirmation"] is True


def test_apply_preset_returns_structured_metadata_and_diff():
    client = TestClient(app)

    response = client.post("/api/v1/presets/apply", json={"name": "science_default"})

    assert response.status_code == 200
    data = response.json()
    assert data["applied_preset"] == "science_default"
    assert data["category"] == "science"
    assert data["risk_level"] == "normal"
    assert data["requires_confirmation"] is False
    assert data["detector_config"]["profile_name"] == "science-default"
    assert data["detector_config_changes"]
    assert data["changed_fields"]
    assert data["skipped_fields"] == []
    assert data["blocked_fields"] == []

# Source: test_presets_preview.py
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath("src"))

from justls.ics.application.services.management_service import ManagementService
from justls.ics.application.usecases.presets import build_preset_plan
from justls.ics.app.main import app
from justls.ics.kernel.runtime import RuntimeAssembler, reset_runtime


def setup_function():
    reset_runtime()


def teardown_function():
    reset_runtime()


def test_preview_preset_plan_has_no_side_effects():
    runtime = RuntimeAssembler().build()
    service = ManagementService(runtime)
    before_detector = runtime.get_detector_config_dict()
    before_calibration = runtime.lamps.get_snapshot().to_dict()

    preview = service.preview_preset_plan(build_preset_plan("calib_flat_default"))

    assert preview["preset"] == "calib_flat_default"
    assert preview["category"] == "calibration"
    assert preview["risk_level"] == "high_impact"
    assert preview["requires_confirmation"] is True
    assert preview["blocked"] is False
    assert preview["blocked_reason"] is None
    assert preview["detector_config_changes"]
    assert preview["calibration_changes"]
    assert preview["changes"]

    assert runtime.get_detector_config_dict() == before_detector
    assert runtime.lamps.get_snapshot().to_dict() == before_calibration


def test_preview_api_returns_backend_generated_diff():
    client = TestClient(app)

    response = client.post("/api/v1/presets/preview", json={"name": "calib_flat_default"})

    assert response.status_code == 200
    data = response.json()

    assert data["preset"] == "calib_flat_default"
    assert data["summary"]
    assert data["category"] == "calibration"
    assert data["risk_level"] == "high_impact"
    assert data["requires_confirmation"] is True
    assert data["blocked"] is False
    assert data["blocked_reason"] is None

    paths = {change["path"] for change in data["changes"]}
    assert "detector_config.profile_name" in paths
    assert "calibration.mode" in paths
    assert "calibration.active_lamp" in paths
    assert "calibration.lamp_enabled" in paths
    assert "calibration.mirror_inserted" in paths


def test_preview_api_is_side_effect_free():
    client = TestClient(app)

    before_status = client.get("/api/v1/status/full").json()
    response = client.post("/api/v1/presets/preview", json={"name": "calib_flat_default"})
    after_status = client.get("/api/v1/status/full").json()

    assert response.status_code == 200
    assert before_status["detector_config"] == after_status["detector_config"]
    assert before_status["calibration"] == after_status["calibration"]


def test_preview_api_unknown_preset_returns_404():
    client = TestClient(app)

    response = client.post("/api/v1/presets/preview", json={"name": "not_exists"})

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "preset_not_found"


def test_preview_reports_blocked_when_observation_is_armed():
    client = TestClient(app)

    arm = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 10.0, "frame_type": "science", "operator_note": "preview-block"},
    )
    assert arm.status_code == 200

    response = client.post("/api/v1/presets/preview", json={"name": "science_default"})

    assert response.status_code == 200
    data = response.json()
    assert data["blocked"] is True
    assert "armed" in data["blocked_reason"]


def test_preview_does_not_enforce_confirmation_yet():
    client = TestClient(app)

    response = client.post("/api/v1/presets/preview", json={"name": "engineering_all_channels_off"})

    assert response.status_code == 200
    data = response.json()
    assert data["requires_confirmation"] is True
    assert data["risk_level"] == "engineering"
    assert data["blocked"] is False

# Source: test_presets_confirmation.py
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


def test_normal_preset_apply_remains_backward_compatible():
    client = TestClient(app)

    response = client.post("/api/v1/presets/apply", json={"name": "science_default"})

    assert response.status_code == 200
    data = response.json()
    assert data["applied_preset"] == "science_default"
    assert data["detector_config"]["profile_name"] == "science-default"


def test_high_impact_preset_requires_confirmation():
    client = TestClient(app)

    response = client.post("/api/v1/presets/apply", json={"name": "calib_flat_default"})

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "confirmation_required"
    assert detail["message"] == "Preset calib_flat_default requires explicit confirmation before apply."
    assert detail["preset"] == "calib_flat_default"
    assert detail["category"] == "calibration"
    assert detail["risk_level"] == "high_impact"
    assert detail["requires_confirmation"] is True


def test_high_impact_preset_apply_succeeds_when_confirmed():
    client = TestClient(app)

    response = client.post(
        "/api/v1/presets/apply",
        json={"name": "calib_flat_default", "confirmed": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["applied_preset"] == "calib_flat_default"
    assert data["detector_config"]["profile_name"] == "calib-flat-default"
    assert data["calibration"]["mode"] == "calibration"
    assert data["calibration"]["active_lamp"] == "flat"
    assert data["calibration"]["lamp_enabled"] is True
    assert data["job_id"]


def test_apply_preset_records_latest_job():
    client = TestClient(app)

    response = client.post(
        "/api/v1/presets/apply",
        json={"name": "calib_flat_default", "confirmed": True},
    )
    assert response.status_code == 200
    applied = response.json()

    status = client.get("/api/v1/status/full")
    assert status.status_code == 200
    latest_job = status.json()["operational_status"]["latest_job"]

    assert latest_job["job_id"] == applied["job_id"]
    assert latest_job["status"] == "succeeded"
    assert latest_job["request"]["subsystem"] == "presets"
    assert latest_job["request"]["action"] == "apply_preset"
    assert latest_job["request"]["params"]["name"] == "calib_flat_default"
    assert latest_job["request"]["params"]["confirmed"] is True
    assert latest_job["result"]["kind"] == "preset_apply"
    assert latest_job["result"]["preset"] == "calib_flat_default"
    assert latest_job["result"]["category"] == "calibration"
    assert latest_job["result"]["risk_level"] == "high_impact"
    assert latest_job["result"]["changed_fields_count"] == len(applied["changed_fields"])
    assert latest_job["result"]["calibration_applied"] is True
    assert latest_job["result"]["slit_applied"] is False


def test_engineering_preset_requires_confirmation():
    client = TestClient(app)

    response = client.post(
        "/api/v1/presets/apply",
        json={"name": "engineering_all_channels_off"},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "confirmation_required"
    assert detail["preset"] == "engineering_all_channels_off"
    assert detail["category"] == "engineering"
    assert detail["risk_level"] == "engineering"
    assert detail["requires_confirmation"] is True


def test_preview_still_does_not_require_confirmation():
    client = TestClient(app)

    response = client.post("/api/v1/presets/preview", json={"name": "calib_flat_default"})

    assert response.status_code == 200
    data = response.json()
    assert data["preset"] == "calib_flat_default"
    assert data["requires_confirmation"] is True
    assert data["blocked"] is False
