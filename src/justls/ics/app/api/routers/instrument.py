from __future__ import annotations

from fastapi import APIRouter

from justls.ics.app.api.dependencies import InstrumentContextServiceDep
from justls.ics.app.api.errors import raise_api_error
from justls.ics.app.api.schemas.instrument import (
    InstrumentContextResponse,
    InstrumentContextUpdateReq,
)

router = APIRouter(prefix="/api/v1", tags=["instrument"])


@router.get("/instrument/context", response_model=InstrumentContextResponse)
def get_instrument_context(
    instrument_context_service: InstrumentContextServiceDep,
) -> InstrumentContextResponse:
    try:
        payload = instrument_context_service.get_context_payload()
    except ValueError as exc:
        raise_api_error(
            status_code=422,
            code="instrument_context_validation_error",
            message=str(exc),
        )
    return InstrumentContextResponse.model_validate(payload)


@router.put("/instrument/context", response_model=InstrumentContextResponse)
def put_instrument_context(
    req: InstrumentContextUpdateReq,
    instrument_context_service: InstrumentContextServiceDep,
) -> InstrumentContextResponse:
    try:
        context = instrument_context_service.save_context_payload(
            req.model_dump(exclude_unset=False)
        )
    except ValueError as exc:
        raise_api_error(
            status_code=422,
            code="instrument_context_validation_error",
            message=str(exc),
        )
    return InstrumentContextResponse.model_validate(context.to_dict())


@router.post("/instrument/context/reload", response_model=InstrumentContextResponse)
def reload_instrument_context(
    instrument_context_service: InstrumentContextServiceDep,
) -> InstrumentContextResponse:
    try:
        context = instrument_context_service.reload_context()
    except ValueError as exc:
        raise_api_error(
            status_code=422,
            code="instrument_context_validation_error",
            message=str(exc),
        )
    return InstrumentContextResponse.model_validate(context.to_dict())
