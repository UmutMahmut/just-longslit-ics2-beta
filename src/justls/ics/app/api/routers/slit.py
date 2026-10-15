from __future__ import annotations

from fastapi import APIRouter

from justls.ics.app.api.dependencies import DispatcherDep, HealthServiceDep
from justls.ics.app.api.errors import raise_dispatch_failure
from justls.ics.app.api.schemas.control import SlitAngleReq, SlitReq
from justls.ics.app.api.schemas.responses import ApiErrorResponse, StateDtoResponse
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


@router.post(
    "/slit",
    response_model=StateDtoResponse,
    responses={400: {"model": ApiErrorResponse, "description": "Slit command failed"}},
)
def set_slit_width(
    req: SlitReq,
    dispatcher: DispatcherDep,
    health_service: HealthServiceDep,
) -> StateDtoResponse:
    request = CommandRequest.create(
        subsystem="slit",
        action="set_width",
        params={"width_um": req.width_um},
        source=CommandSource.API,
    )
    result = dispatcher.dispatch(request)
    return _unwrap_state_result(result, health_service)


@router.post(
    "/slit_angle",
    response_model=StateDtoResponse,
    responses={400: {"model": ApiErrorResponse, "description": "Slit angle command failed"}},
)
def set_slit_angle(
    req: SlitAngleReq,
    dispatcher: DispatcherDep,
    health_service: HealthServiceDep,
) -> StateDtoResponse:
    request = CommandRequest.create(
        subsystem="slit",
        action="set_angle",
        params={"angle_deg": req.angle_deg},
        source=CommandSource.API,
    )
    result = dispatcher.dispatch(request)
    return _unwrap_state_result(result, health_service)