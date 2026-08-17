from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from justls.ics.app.api.dependencies import (
    ObservationPreviewServiceDep,
    ObservationSequenceServiceDep,
    ObservationServiceDep,
)
from justls.ics.app.api.schemas.observation import (
    ObservationArmReq,
    ObservationCommandFeedbackResponse,
)
from justls.ics.app.api.schemas.observation_preview import (
    ObservationPreviewReq,
    ObservationPreviewResponse,
)
from justls.ics.app.api.schemas.responses import ObservationStatusResponse
from justls.ics.app.api.schemas.observation_sequence import (
    ObservationPlanReq,
    SequenceCommandFeedbackResponse,
)
from justls.ics.application.dispatcher import DispatchResult
from justls.ics.domain.observation.models import (
    ObservationCommandFeedback,
    ObservationCommandName,
)
from justls.ics.domain.observation.sequence import (
    SequenceExecutionSnapshot,
    SequencePreview,
)
from justls.ics.application.services.observation_sequence_service import (
    SequenceCommandResult,
)
from justls.ics.kernel.errors import ErrorCode, ICSException

router = APIRouter(prefix="/api/v1", tags=["observation"])


def _request_id_from(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return str(value) if value else None


def _feedback_response(
    feedback: ObservationCommandFeedback,
) -> ObservationCommandFeedbackResponse:
    return ObservationCommandFeedbackResponse.from_domain(feedback)


def _feedback_error_response(
    feedback: ObservationCommandFeedback,
    *,
    status_code: int = 400,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=_feedback_response(feedback).model_dump(mode="json"),
    )


def _observation_command_response(
    *,
    command: ObservationCommandName,
    result: DispatchResult,
    observation_service: ObservationServiceDep,
    request_id: str | None,
) -> ObservationCommandFeedbackResponse | JSONResponse:
    feedback = observation_service.feedback_from_dispatch_result(
        command,
        result,
        request_id=request_id,
    )
    if feedback.ok:
        return _feedback_response(feedback)
    return _feedback_error_response(feedback, status_code=400)


def _observation_exception_response(
    *,
    command: ObservationCommandName,
    exc: ICSException,
    observation_service: ObservationServiceDep,
    request_id: str | None,
) -> JSONResponse:
    feedback = observation_service.feedback_from_exception(
        command,
        exc,
        request_id=request_id,
    )
    return _feedback_error_response(feedback, status_code=400)


def _sequence_feedback(
    result: SequenceCommandResult,
    *,
    request_id: str | None,
) -> SequenceCommandFeedbackResponse:
    error = result.error
    blocked = error is not None and error.code == ErrorCode.INTERLOCK_BLOCKED
    return SequenceCommandFeedbackResponse(
        command=result.command,
        ok=result.ok,
        status="succeeded" if result.ok else ("blocked" if blocked else "failed"),
        message=(
            result.sequence.message
            if result.ok and result.sequence is not None and result.sequence.message
            else (error.info.message if error is not None else "Sequence command completed.")
        ),
        request_id=request_id,
        latest_job=result.job.to_dict(),
        sequence=result.sequence,
        error=(
            {
                "code": error.code.value,
                "message": error.info.message,
                "details": error.info.details,
            }
            if error is not None
            else None
        ),
    )


def _sequence_response(
    result: SequenceCommandResult,
    *,
    request_id: str | None,
) -> SequenceCommandFeedbackResponse | JSONResponse:
    feedback = _sequence_feedback(result, request_id=request_id)
    if result.ok:
        return feedback
    return JSONResponse(status_code=400, content=feedback.model_dump(mode="json"))


@router.get("/observation/status", response_model=ObservationStatusResponse)
def get_observation_status(observation_service: ObservationServiceDep) -> ObservationStatusResponse:
    payload = observation_service.get_exposure_status()
    return ObservationStatusResponse.model_validate(payload)


@router.post(
    "/observation/preview",
    response_model=ObservationPreviewResponse,
)
def preview_observation(
    req: ObservationPreviewReq,
    observation_preview_service: ObservationPreviewServiceDep,
) -> ObservationPreviewResponse:
    preview = observation_preview_service.preview_request(req.to_domain())
    return ObservationPreviewResponse.model_validate(preview.model_dump(mode="json"))


@router.post("/observation/sequence/preview", response_model=SequencePreview)
def preview_observation_sequence(
    req: ObservationPlanReq,
    sequence_service: ObservationSequenceServiceDep,
) -> SequencePreview:
    return sequence_service.preview_plan(req.to_domain())


@router.get(
    "/observation/sequence/status",
    response_model=SequenceExecutionSnapshot | None,
)
def get_observation_sequence_status(
    sequence_service: ObservationSequenceServiceDep,
) -> SequenceExecutionSnapshot | None:
    return sequence_service.status()


@router.post(
    "/observation/sequence/load",
    response_model=SequenceCommandFeedbackResponse,
    responses={400: {"model": SequenceCommandFeedbackResponse}},
)
def load_observation_sequence(
    req: ObservationPlanReq,
    request: Request,
    sequence_service: ObservationSequenceServiceDep,
) -> SequenceCommandFeedbackResponse | JSONResponse:
    return _sequence_response(
        sequence_service.load(req.to_domain()),
        request_id=_request_id_from(request),
    )


def _sequence_command_route(
    command: str,
    request: Request,
    sequence_service: ObservationSequenceServiceDep,
) -> SequenceCommandFeedbackResponse | JSONResponse:
    action = getattr(sequence_service, command)
    return _sequence_response(action(), request_id=_request_id_from(request))


@router.post("/observation/sequence/start", response_model=SequenceCommandFeedbackResponse, responses={400: {"model": SequenceCommandFeedbackResponse}})
def start_observation_sequence(
    request: Request,
    sequence_service: ObservationSequenceServiceDep,
) -> SequenceCommandFeedbackResponse | JSONResponse:
    return _sequence_command_route("start", request, sequence_service)


@router.post("/observation/sequence/finish_step", response_model=SequenceCommandFeedbackResponse, responses={400: {"model": SequenceCommandFeedbackResponse}})
def finish_observation_sequence_step(
    request: Request,
    sequence_service: ObservationSequenceServiceDep,
) -> SequenceCommandFeedbackResponse | JSONResponse:
    return _sequence_command_route("finish_step", request, sequence_service)


@router.post("/observation/sequence/stop_readout_step", response_model=SequenceCommandFeedbackResponse, responses={400: {"model": SequenceCommandFeedbackResponse}})
def stop_observation_sequence_step(
    request: Request,
    sequence_service: ObservationSequenceServiceDep,
) -> SequenceCommandFeedbackResponse | JSONResponse:
    return _sequence_command_route("stop_readout_step", request, sequence_service)


@router.post("/observation/sequence/pause", response_model=SequenceCommandFeedbackResponse, responses={400: {"model": SequenceCommandFeedbackResponse}})
def pause_observation_sequence(
    request: Request,
    sequence_service: ObservationSequenceServiceDep,
) -> SequenceCommandFeedbackResponse | JSONResponse:
    return _sequence_command_route("pause", request, sequence_service)


@router.post("/observation/sequence/resume", response_model=SequenceCommandFeedbackResponse, responses={400: {"model": SequenceCommandFeedbackResponse}})
def resume_observation_sequence(
    request: Request,
    sequence_service: ObservationSequenceServiceDep,
) -> SequenceCommandFeedbackResponse | JSONResponse:
    return _sequence_command_route("resume", request, sequence_service)


@router.post("/observation/sequence/abort", response_model=SequenceCommandFeedbackResponse, responses={400: {"model": SequenceCommandFeedbackResponse}})
def abort_observation_sequence(
    request: Request,
    sequence_service: ObservationSequenceServiceDep,
) -> SequenceCommandFeedbackResponse | JSONResponse:
    return _sequence_command_route("abort", request, sequence_service)


@router.post("/observation/sequence/retry_current_step", response_model=SequenceCommandFeedbackResponse, responses={400: {"model": SequenceCommandFeedbackResponse}})
def retry_observation_sequence_step(
    request: Request,
    sequence_service: ObservationSequenceServiceDep,
) -> SequenceCommandFeedbackResponse | JSONResponse:
    return _sequence_command_route("retry_current_step", request, sequence_service)


@router.post("/observation/sequence/mark_failed", response_model=SequenceCommandFeedbackResponse, responses={400: {"model": SequenceCommandFeedbackResponse}})
def mark_observation_sequence_failed(
    request: Request,
    sequence_service: ObservationSequenceServiceDep,
) -> SequenceCommandFeedbackResponse | JSONResponse:
    return _sequence_command_route("mark_failed", request, sequence_service)


@router.post(
    "/observation/arm",
    response_model=ObservationCommandFeedbackResponse,
    responses={
        400: {
            "model": ObservationCommandFeedbackResponse,
            "description": "Observation command rejected",
        }
    },
)
def arm_observation(
    req: ObservationArmReq,
    request: Request,
    observation_service: ObservationServiceDep,
) -> ObservationCommandFeedbackResponse | JSONResponse:
    request_id = _request_id_from(request)
    try:
        result = observation_service.arm(
            exp_time_s=req.exp_time_s,
            frame_type=req.frame_type,
            operator_note=req.operator_note,
            save_requested=req.save_requested,
        )
    except ICSException as exc:
        return _observation_exception_response(
            command=ObservationCommandName.ARM,
            exc=exc,
            observation_service=observation_service,
            request_id=request_id,
        )

    return _observation_command_response(
        command=ObservationCommandName.ARM,
        result=result,
        observation_service=observation_service,
        request_id=request_id,
    )


@router.post(
    "/observation/start",
    response_model=ObservationCommandFeedbackResponse,
    responses={
        400: {
            "model": ObservationCommandFeedbackResponse,
            "description": "Observation command rejected",
        }
    },
)
def start_observation(
    request: Request,
    observation_service: ObservationServiceDep,
) -> ObservationCommandFeedbackResponse | JSONResponse:
    request_id = _request_id_from(request)
    try:
        result = observation_service.start()
    except ICSException as exc:
        return _observation_exception_response(
            command=ObservationCommandName.START,
            exc=exc,
            observation_service=observation_service,
            request_id=request_id,
        )

    return _observation_command_response(
        command=ObservationCommandName.START,
        result=result,
        observation_service=observation_service,
        request_id=request_id,
    )


@router.post(
    "/observation/finish",
    response_model=ObservationCommandFeedbackResponse,
    responses={
        400: {
            "model": ObservationCommandFeedbackResponse,
            "description": "Observation command rejected",
        }
    },
)
def finish_observation(
    request: Request,
    observation_service: ObservationServiceDep,
) -> ObservationCommandFeedbackResponse | JSONResponse:
    request_id = _request_id_from(request)
    try:
        result = observation_service.finish()
    except ICSException as exc:
        return _observation_exception_response(
            command=ObservationCommandName.FINISH,
            exc=exc,
            observation_service=observation_service,
            request_id=request_id,
        )

    return _observation_command_response(
        command=ObservationCommandName.FINISH,
        result=result,
        observation_service=observation_service,
        request_id=request_id,
    )


@router.post(
    "/observation/stop_readout",
    response_model=ObservationCommandFeedbackResponse,
    responses={
        400: {
            "model": ObservationCommandFeedbackResponse,
            "description": "Observation command rejected",
        }
    },
)
def stop_readout_observation(
    request: Request,
    observation_service: ObservationServiceDep,
) -> ObservationCommandFeedbackResponse | JSONResponse:
    request_id = _request_id_from(request)
    try:
        result = observation_service.stop_readout()
    except ICSException as exc:
        return _observation_exception_response(
            command=ObservationCommandName.STOP_READOUT,
            exc=exc,
            observation_service=observation_service,
            request_id=request_id,
        )

    return _observation_command_response(
        command=ObservationCommandName.STOP_READOUT,
        result=result,
        observation_service=observation_service,
        request_id=request_id,
    )


@router.post(
    "/observation/abort_discard",
    response_model=ObservationCommandFeedbackResponse,
    responses={
        400: {
            "model": ObservationCommandFeedbackResponse,
            "description": "Observation command rejected",
        }
    },
)
def abort_discard_observation(
    request: Request,
    observation_service: ObservationServiceDep,
) -> ObservationCommandFeedbackResponse | JSONResponse:
    request_id = _request_id_from(request)
    try:
        result = observation_service.abort_discard()
    except ICSException as exc:
        return _observation_exception_response(
            command=ObservationCommandName.ABORT_DISCARD,
            exc=exc,
            observation_service=observation_service,
            request_id=request_id,
        )

    return _observation_command_response(
        command=ObservationCommandName.ABORT_DISCARD,
        result=result,
        observation_service=observation_service,
        request_id=request_id,
    )
