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


def test_openapi_presets_responses_are_typed():
    client = TestClient(app)
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    data = openapi.json()

    list_schema = data["paths"]["/api/v1/presets"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    apply_schema = data["paths"]["/api/v1/presets/apply"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]

    assert "$ref" in list_schema
    assert list_schema["$ref"].endswith("/PresetListResponse")
    assert "$ref" in apply_schema
    assert apply_schema["$ref"].endswith("/PresetApplyResponse")


def test_openapi_observation_responses_are_typed():
    client = TestClient(app)
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    data = openapi.json()

    status_schema = data["paths"]["/api/v1/observation/status"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    arm_schema = data["paths"]["/api/v1/observation/arm"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    start_schema = data["paths"]["/api/v1/observation/start"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    sequence_preview_schema = data["paths"]["/api/v1/observation/sequence/preview"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    sequence_load_schema = data["paths"]["/api/v1/observation/sequence/load"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    sequence_retry_schema = data["paths"]["/api/v1/observation/sequence/retry_current_step"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]

    assert "$ref" in status_schema
    assert status_schema["$ref"].endswith("/ObservationStatusResponse")
    assert "$ref" in arm_schema
    assert arm_schema["$ref"].endswith("/ObservationCommandFeedbackResponse")
    assert "$ref" in start_schema
    assert start_schema["$ref"].endswith("/ObservationCommandFeedbackResponse")
    assert sequence_preview_schema["$ref"].endswith("/SequencePreview")
    assert sequence_load_schema["$ref"].endswith("/SequenceCommandFeedbackResponse")
    assert sequence_retry_schema["$ref"].endswith("/SequenceCommandFeedbackResponse")


def test_openapi_response_components_include_new_models():
    client = TestClient(app)
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    data = openapi.json()

    schemas = data["components"]["schemas"]

    assert "PresetListResponse" in schemas
    assert "PresetApplyResponse" in schemas
    assert "ObservationStatusResponse" in schemas
    assert "ObservationCommandFeedbackResponse" in schemas
    assert "ObservationCommandErrorResponse" in schemas
    assert "ObservationPlan" in schemas
    assert "SequencePreview" in schemas
    assert "SequenceExecutionSnapshot" in schemas
    assert "SequenceCommandFeedbackResponse" in schemas


def test_openapi_system_and_detector_responses_are_typed():
    client = TestClient(app)
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    data = openapi.json()

    health_schema = data["paths"]["/api/v1/health"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    status_schema = data["paths"]["/api/v1/status"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    status_full_schema = data["paths"]["/api/v1/status/full"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    capabilities_schema = data["paths"]["/api/v1/capabilities"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    observatory_schema = data["paths"]["/api/v1/observatory/context"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    detector_get_schema = data["paths"]["/api/v1/detector/config"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    detector_post_schema = data["paths"]["/api/v1/detector/config"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]

    assert "$ref" in health_schema
    assert health_schema["$ref"].endswith("/HealthResponse")

    assert "$ref" in status_schema
    assert status_schema["$ref"].endswith("/StateDtoResponse")

    assert "$ref" in status_full_schema
    assert status_full_schema["$ref"].endswith("/StatusFullResponse")

    assert "$ref" in capabilities_schema
    assert capabilities_schema["$ref"].endswith("/CapabilitiesResponse")

    assert "$ref" in observatory_schema
    assert observatory_schema["$ref"].endswith("/ObservatoryContext")

    assert "$ref" in detector_get_schema
    assert detector_get_schema["$ref"].endswith(("/DetectorConfig", "/DetectorConfig-Output"))

    assert "$ref" in detector_post_schema
    assert detector_post_schema["$ref"].endswith(("/DetectorConfig", "/DetectorConfig-Output"))


def test_openapi_response_components_include_system_models():
    client = TestClient(app)
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    data = openapi.json()

    schemas = data["components"]["schemas"]

    assert "HealthResponse" in schemas
    assert "StateDtoResponse" in schemas
    assert "StatusFullResponse" in schemas
    assert "CapabilitiesResponse" in schemas
    assert "RuntimeStatusResponse" in schemas
    assert "RuntimeStateResponse" in schemas
    assert "RuntimeSubsystemStateResponse" in schemas
    assert "ObservatoryContext" in schemas
    assert "ObservatoryComponentContext" in schemas


def test_openapi_control_responses_are_typed():
    client = TestClient(app)
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    data = openapi.json()

    lamp_schema = data["paths"]["/api/v1/lamp"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    calib_status_schema = data["paths"]["/api/v1/calibration/status"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    calib_mode_schema = data["paths"]["/api/v1/calibration/mode"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    calib_lamp_schema = data["paths"]["/api/v1/calibration/lamp"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    slit_schema = data["paths"]["/api/v1/slit"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    slit_angle_schema = data["paths"]["/api/v1/slit_angle"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]

    assert "$ref" in lamp_schema
    assert lamp_schema["$ref"].endswith("/StateDtoResponse")

    assert "$ref" in calib_status_schema
    assert calib_status_schema["$ref"].endswith("/CalibrationStatusResponse")

    assert "$ref" in calib_mode_schema
    assert calib_mode_schema["$ref"].endswith("/CalibrationStatusResponse")

    assert "$ref" in calib_lamp_schema
    assert calib_lamp_schema["$ref"].endswith("/CalibrationStatusResponse")

    assert "$ref" in slit_schema
    assert slit_schema["$ref"].endswith("/StateDtoResponse")

    assert "$ref" in slit_angle_schema
    assert slit_angle_schema["$ref"].endswith("/StateDtoResponse")


def test_openapi_control_response_components_exist():
    client = TestClient(app)
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    data = openapi.json()

    schemas = data["components"]["schemas"]

    assert "CalibrationStatusResponse" in schemas
    assert "StateDtoResponse" in schemas


def test_openapi_error_response_models_are_declared():
    client = TestClient(app)
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    data = openapi.json()

    obs_start_400 = data["paths"]["/api/v1/observation/start"]["post"]["responses"]["400"]["content"]["application/json"]["schema"]
    slit_400 = data["paths"]["/api/v1/slit"]["post"]["responses"]["400"]["content"]["application/json"]["schema"]
    calib_status_404 = data["paths"]["/api/v1/calibration/status"]["get"]["responses"]["404"]["content"]["application/json"]["schema"]
    preset_apply_404 = data["paths"]["/api/v1/presets/apply"]["post"]["responses"]["404"]["content"]["application/json"]["schema"]

    assert "$ref" in obs_start_400
    assert obs_start_400["$ref"].endswith("/ObservationCommandFeedbackResponse")

    assert "$ref" in slit_400
    assert slit_400["$ref"].endswith("/ApiErrorResponse")

    assert "$ref" in calib_status_404
    assert calib_status_404["$ref"].endswith("/ApiErrorResponse")

    assert "$ref" in preset_apply_404
    assert preset_apply_404["$ref"].endswith("/ApiErrorResponse")


def test_openapi_error_components_exist():
    client = TestClient(app)
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    data = openapi.json()

    schemas = data["components"]["schemas"]

    assert "ApiErrorResponse" in schemas
    assert "ApiErrorDetailResponse" in schemas
