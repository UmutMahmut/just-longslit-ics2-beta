import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath("src"))

from justls.ics.application.services.health_service import HealthService
from justls.ics.app.main import app
from justls.ics.kernel.runtime import RuntimeAssembler, reset_runtime


def setup_function():
    reset_runtime()


def teardown_function():
    reset_runtime()


def test_operational_status_ready():
    runtime = RuntimeAssembler().build()
    status = HealthService(runtime).get_operational_status()

    assert status["level"] == "ok"
    assert status["flags"]["busy"] is False
    assert status["flags"]["fault"] is False
    assert status["flags"]["interlock_blocked"] is False
    assert status["summary"] == "System is ready for observer operations."


def test_operational_status_exposing_is_busy():
    runtime = RuntimeAssembler().build()
    runtime.detector.arm(
        exp_time_s=5.0,
        frame_type="science",
        operator_note=None,
        instrument_snapshot=None,
        calibration_snapshot=None,
        detector_config=runtime.get_detector_config_dict(),
    )
    runtime.detector.start()

    status = HealthService(runtime).get_operational_status()

    assert status["level"] == "busy"
    assert status["flags"]["busy"] is True
    assert status["flags"]["exposing"] is True
    assert status["summary"] == "Exposure is in progress."


def test_status_full_includes_operational_status():
    client = TestClient(app)
    response = client.get("/api/v1/status/full")

    assert response.status_code == 200
    data = response.json()
    assert "operational_status" in data
    assert data["operational_status"]["level"] == "ok"
    assert data["operational_status"]["control_state"] == "idle"
    assert data["operational_status"]["exposure_state"] == "ready_to_arm"
    assert data["operational_status"]["ui_hints"]["show_request_id"] is True
