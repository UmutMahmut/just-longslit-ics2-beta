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


def test_api_set_slit_width():
    client = TestClient(app)

    response = client.post("/api/v1/slit", json={"width_um": 220.0})
    assert response.status_code == 200
    data = response.json()
    assert data["slit_width_um"] == 220.0
    assert data["slit_angle_deg"] == 0.0

    status = client.get("/api/v1/status")
    assert status.status_code == 200
    status_data = status.json()
    assert status_data["slit_width_um"] == 220.0
    assert status_data["slit_angle_deg"] == 0.0

def test_api_set_slit_angle():
    client = TestClient(app)

    response = client.post("/api/v1/slit_angle", json={"angle_deg": 12.5})
    assert response.status_code == 200
    data = response.json()
    assert data["slit_width_um"] == 120.0
    assert data["slit_angle_deg"] == 12.5

    status = client.get("/api/v1/status")
    assert status.status_code == 200
    status_data = status.json()
    assert status_data["slit_width_um"] == 120.0
    assert status_data["slit_angle_deg"] == 12.5

def test_api_invalid_slit_width_returns_422():
    client = TestClient(app)
    response = client.post("/api/v1/slit", json={"width_um": 0})

    assert response.status_code == 422

def test_api_invalid_slit_angle_returns_422():
    client = TestClient(app)
    response = client.post("/api/v1/slit_angle", json={"angle_deg": 120.0})

    assert response.status_code == 422

def test_api_lamp_legacy_on_and_off():
    client = TestClient(app)

    on_response = client.post("/api/v1/lamp", json={"on": True})
    assert on_response.status_code == 200
    assert on_response.json()["lamp_on"] is True

    off_response = client.post("/api/v1/lamp", json={"on": False})
    assert off_response.status_code == 200
    assert off_response.json()["lamp_on"] is False

def test_api_get_calibration_status():
    client = TestClient(app)

    response = client.get("/api/v1/calibration/status")
    assert response.status_code == 200
    data = response.json()

    assert data["mode"] == "science"
    assert data["active_lamp"] is None
    assert data["lamp_enabled"] is False
    assert data["mirror_inserted"] is False

def test_api_set_calibration_mode_and_lamp():
    client = TestClient(app)

    response1 = client.post("/api/v1/calibration/mode", json={"mode": "calibration"})
    assert response1.status_code == 200
    assert response1.json()["mode"] == "calibration"

    response2 = client.post("/api/v1/calibration/lamp", json={"lamp": "flat", "enabled": True})
    assert response2.status_code == 200
    data = response2.json()

    assert data["mode"] == "calibration"
    assert data["active_lamp"] == "flat"
    assert data["lamp_enabled"] is True
    assert data["mirror_inserted"] is True

    legacy = client.get("/api/v1/status")
    assert legacy.json()["lamp_on"] is True

def test_api_invalid_calibration_mode_returns_422():
    client = TestClient(app)
    response = client.post("/api/v1/calibration/mode", json={"mode": "invalid"})

    assert response.status_code == 422

def test_api_invalid_calibration_lamp_returns_422():
    client = TestClient(app)
    response = client.post("/api/v1/calibration/lamp", json={"lamp": "invalid", "enabled": True})

    assert response.status_code == 422
