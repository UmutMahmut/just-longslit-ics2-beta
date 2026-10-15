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


def test_dispatcher_success_flow():
    runtime = RuntimeAssembler().build()
    runtime.set_subsystem_connected("slit", True)
    runtime.set_subsystem_state("slit", ControlState.IDLE)

    dispatcher = CommandDispatcher(runtime)

    def handler(rt, request):
        return {"width_um": request.params["width_um"]}

    dispatcher.register_handler("slit", "set_width", handler)

    req = CommandRequest.create(
        subsystem="slit",
        action="set_width",
        params={"width_um": 100.0},
        source=CommandSource.UI,
    )

    result = dispatcher.dispatch(req)
    data = result.to_dict()

    assert data["job"]["status"] == "succeeded"
    assert data["payload"]["width_um"] == 100.0
    assert runtime.get_subsystem_state("slit").state == ControlState.IDLE

def test_dispatcher_unsupported_action():
    runtime = RuntimeAssembler().build()
    dispatcher = CommandDispatcher(runtime)

    req = CommandRequest.create(
        subsystem="slit",
        action="not_registered",
        params={},
        source=CommandSource.UI,
    )

    try:
        dispatcher.dispatch(req)
        assert False, "Expected UnsupportedError"
    except UnsupportedError as exc:
        assert exc.code == ErrorCode.UNSUPPORTED

def test_validate_required_params():
    req = CommandRequest.create(
        subsystem="slit",
        action="set_width",
        params={},
        source=CommandSource.UI,
    )

    try:
        validate_required_params(req, {"width_um"})
        assert False, "Expected InvalidParamError"
    except InvalidParamError as exc:
        assert exc.code == ErrorCode.INVALID_PARAM

def test_dispatcher_invalid_state_does_not_fault_detector_subsystem():
    runtime = RuntimeAssembler().build()
    dispatcher = CommandDispatcher(runtime)

    def handler(rt, request):
        raise InvalidStateError(
            "detector is not ready for this transition",
            subsystem="detector",
            details={"state": "ready_to_arm"},
        )

    dispatcher.register_handler("detector", "bad_transition", handler)

    req = CommandRequest.create(
        subsystem="detector",
        action="bad_transition",
        params={},
        source=CommandSource.API,
    )

    result = dispatcher.dispatch(req)
    data = result.to_dict()

    assert data["job"]["status"] == "failed"
    assert data["payload"]["error"]["code"] == "invalid_state"
    assert runtime.get_subsystem_state("detector").state == ControlState.IDLE
    assert runtime.get_snapshot().overall_state == ControlState.IDLE

def test_dispatcher_invalid_param_does_not_fault_slit_subsystem():
    runtime = RuntimeAssembler().build()
    dispatcher = CommandDispatcher(runtime)

    def handler(rt, request):
        raise InvalidParamError(
            "width_um must be > 0",
            subsystem="slit",
            details={"width_um": 0},
        )

    dispatcher.register_handler("slit", "bad_width", handler)

    req = CommandRequest.create(
        subsystem="slit",
        action="bad_width",
        params={"width_um": 0},
        source=CommandSource.API,
    )

    result = dispatcher.dispatch(req)
    data = result.to_dict()

    assert data["job"]["status"] == "failed"
    assert data["payload"]["error"]["code"] == "invalid_param"
    assert runtime.get_subsystem_state("slit").state == ControlState.IDLE
    assert runtime.get_snapshot().overall_state == ControlState.IDLE
