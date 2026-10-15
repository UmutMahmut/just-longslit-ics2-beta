from __future__ import annotations

from fastapi import APIRouter

from justls.ics.app.api.dependencies import DispatcherDep, HealthServiceDep
from justls.ics.app.api.errors import raise_api_error, raise_dispatch_failure
from justls.ics.app.api.schemas.control import (
    CalibrationLampReq,
    CalibrationModeReq,
    LampReq,
)
from justls.ics.app.api.schemas.responses import (
    ApiErrorResponse,
    CalibrationStatusResponse,
    StateDtoResponse,
)
from justls.ics.application.dispatcher import DispatchResult
from justls.ics.kernel.jobs import CommandRequest
from justls.ics.kernel.states import CommandSource

router = APIRouter(prefix="/api/v1", tags=["control"])


def _unwrap_state_result(
    result: DispatchResult,
    health_service: HealthServiceDep,
) -> StateDtoResponse:
    if result.job.status.value == "failed":
        raise_dispatch_failure(result, default_code="command_failed")
    return StateDtoResponse.model_validate(health_service.get_state_dto())


def _unwrap_calibration_result(result: DispatchResult) -> CalibrationStatusResponse:
    if result.job.status.value == "failed":
        raise_dispatch_failure(result, default_code="command_failed")
    return CalibrationStatusResponse.model_validate(result.payload)


@router.post(
    "/lamp",
    response_model=StateDtoResponse,
    responses={400: {"model": ApiErrorResponse, "description": "Lamp command failed"}},
)
def set_lamp_legacy(
    req: LampReq,
    dispatcher: DispatcherDep,
    health_service: HealthServiceDep,
) -> StateDtoResponse:
    request = CommandRequest.create(
        subsystem="lamps",
        action="set_legacy_on",
        params={"on": req.on},
        source=CommandSource.API,
    )
    result = dispatcher.dispatch(request)
    return _unwrap_state_result(result, health_service)


@router.get(
    "/calibration/status",
    response_model=CalibrationStatusResponse,
    responses={404: {"model": ApiErrorResponse, "description": "Calibration subsystem unavailable"}},
)
def get_calibration_status(health_service: HealthServiceDep) -> CalibrationStatusResponse:
    calibration = health_service.get_calibration_status()
    if calibration is None:
        raise_api_error(
            status_code=404,
            code="subsystem_unavailable",
            message="Calibration subsystem unavailable.",
        )
    return CalibrationStatusResponse.model_validate(calibration)


@router.post(
    "/calibration/mode",
    response_model=CalibrationStatusResponse,
    responses={400: {"model": ApiErrorResponse, "description": "Calibration mode command failed"}},
)
def set_calibration_mode(
    req: CalibrationModeReq,
    dispatcher: DispatcherDep,
) -> CalibrationStatusResponse:
    request = CommandRequest.create(
        subsystem="lamps",
        action="set_mode",
        params={"mode": req.mode},
        source=CommandSource.API,
    )
    result = dispatcher.dispatch(request)
    return _unwrap_calibration_result(result)


@router.post(
    "/calibration/lamp",
    response_model=CalibrationStatusResponse,
    responses={400: {"model": ApiErrorResponse, "description": "Calibration lamp command failed"}},
)
def set_calibration_lamp(
    req: CalibrationLampReq,
    dispatcher: DispatcherDep,
) -> CalibrationStatusResponse:
    request = CommandRequest.create(
        subsystem="lamps",
        action="select_lamp",
        params={"lamp": req.lamp, "enabled": req.enabled},
        source=CommandSource.API,
    )
    result = dispatcher.dispatch(request)
    return _unwrap_calibration_result(result)