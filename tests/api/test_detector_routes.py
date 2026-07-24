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


def test_api_get_detector_config():
    client = TestClient(app)

    response = client.get("/api/v1/detector/config")
    assert response.status_code == 200
    data = response.json()

    assert data["profile_name"] == "campus-beta-shared-camera"
    assert data["shared_physical_camera"] is True
    assert {
        channel["source_camera_id"] for channel in data["channels"].values()
    } == {"science-camera-01"}
    assert data["channels"]["B"]["camera_role"] == "science_b"
    assert data["channels"]["G"]["camera_role"] == "science_g"
    assert data["channels"]["R"]["camera_role"] == "science_r"

def test_api_set_detector_config():
    client = TestClient(app)

    response = client.post(
        "/api/v1/detector/config",
        json={
            "profile_name": "rgb-safe-default",
            "save_enabled": True,
            "trigger_mode": "internal",
            "readout_mode": "normal",
            "channels": {
                "B": {"enabled": True, "camera_role": "science_b"},
                "G": {"enabled": False, "camera_role": "science_g"},
                "R": {"enabled": True, "camera_role": "science_r"},
            },
        },
    )
    assert response.status_code == 200
    data = response.json()

    assert data["profile_name"] == "rgb-safe-default"
    assert data["channels"]["B"]["enabled"] is True
    assert data["channels"]["G"]["enabled"] is False
    assert data["channels"]["R"]["enabled"] is True

    readback = client.get("/api/v1/detector/config")
    assert readback.status_code == 200
    read_data = readback.json()
    assert read_data["profile_name"] == "rgb-safe-default"
    assert read_data["channels"]["R"]["enabled"] is True

def test_api_detector_config_invalid_payload_returns_422():
    client = TestClient(app)

    response = client.post(
        "/api/v1/detector/config",
        json={
            "profile_name": "bad",
            "save_enabled": True,
            "trigger_mode": "invalid",
            "readout_mode": "normal",
            "channels": {
                "B": {"enabled": True, "camera_role": "science_b"},
                "G": {"enabled": False, "camera_role": "science_g"},
                "R": {"enabled": True, "camera_role": "science_r"},
            },
        },
    )
    assert response.status_code == 422
