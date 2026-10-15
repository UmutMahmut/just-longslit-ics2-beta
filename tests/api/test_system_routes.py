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


def test_api_root():
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "ICS Beta is running."
    assert data["docs"] == "/docs"
    assert data["openapi"] == "/openapi.json"

def test_api_health():
    client = TestClient(app)
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["service"] == "just-longslit-ics-2.0"
    assert "runtime" in data

def test_api_status():
    client = TestClient(app)
    response = client.get("/api/v1/status")

    assert response.status_code == 200
    data = response.json()
    assert data["slit_width_um"] == 120.0
    assert data["slit_angle_deg"] == 0.0
    assert data["lamp_on"] is False
    assert data["temperature_c"] is None

def test_api_status_full():
    client = TestClient(app)
    response = client.get("/api/v1/status/full")

    assert response.status_code == 200
    data = response.json()

    assert "state" in data
    assert "capabilities" in data
    assert "calibration" in data
    assert "observation" in data
    assert "detector_config" in data
    assert "hal" in data
    assert "run_mode" in data
    assert "timestamp_utc" in data
    assert data["state"]["slit_width_um"] == 120.0
    assert data["state"]["slit_angle_deg"] == 0.0
    assert data["state"]["lamp_on"] is False
    assert data["capabilities"]["slit"] is True
    assert data["capabilities"]["slit_angle"] is True
    assert data["capabilities"]["calib_lamps"] is True
    assert data["calibration"]["mode"] == "science"
    assert data["observation"]["state"] == "ready_to_arm"
    assert data["observation"]["observation_meta"] is None
    assert (
        data["detector_config"]["profile_name"]
        == "campus-beta-shared-camera"
    )

def test_api_capabilities():
    client = TestClient(app)
    response = client.get("/api/v1/capabilities")

    assert response.status_code == 200
    data = response.json()

    assert data["slit"] is True
    assert data["slit_angle"] is True
    assert data["calib_lamps"] is True
    assert data["rotator"] is False
    assert data["slit_monitor_camera"] is True
    assert data["science_channels_bgr"] is True
    assert data["guider"] is False
    assert data["fast_photometry"] is False
