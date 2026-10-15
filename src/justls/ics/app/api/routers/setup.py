from __future__ import annotations

from fastapi import APIRouter

from justls.ics.app.api.dependencies import SetupContextServiceDep
from justls.ics.app.api.errors import raise_api_error
from justls.ics.app.api.schemas.responses import SetupContextResponse
from justls.ics.app.api.schemas.setup import SetupContextUpdateReq

router = APIRouter(prefix="/api/v1", tags=["setup"])


@router.get("/setup/context", response_model=SetupContextResponse)
def get_setup_context(
    setup_context_service: SetupContextServiceDep,
) -> SetupContextResponse:
    payload = setup_context_service.get_context_payload()
    return SetupContextResponse.model_validate(payload)


@router.put("/setup/context", response_model=SetupContextResponse)
def put_setup_context(
    req: SetupContextUpdateReq,
    setup_context_service: SetupContextServiceDep,
) -> SetupContextResponse:
    try:
        context = setup_context_service.save_context_payload(req.model_dump())
    except ValueError as exc:
        raise_api_error(
            status_code=422,
            code="setup_context_validation_error",
            message=str(exc),
        )
    return SetupContextResponse.model_validate(context.to_dict())


@router.post("/setup/context/reload", response_model=SetupContextResponse)
def reload_setup_context(
    setup_context_service: SetupContextServiceDep,
) -> SetupContextResponse:
    try:
        context = setup_context_service.reload_context()
    except ValueError as exc:
        raise_api_error(
            status_code=422,
            code="setup_context_validation_error",
            message=str(exc),
        )
    return SetupContextResponse.model_validate(context.to_dict())