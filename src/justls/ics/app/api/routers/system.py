from __future__ import annotations

from fastapi import APIRouter

from justls.ics.app.api.dependencies import OutputLocationServiceDep
from justls.ics.app.api.errors import raise_api_error
from justls.ics.app.api.schemas.system import (
    OutputLocationResponse,
    OutputLocationUpdateReq,
)
from justls.ics.application.services.output_location_service import OutputLocationError

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/system/output-location", response_model=OutputLocationResponse)
def get_output_location(
    service: OutputLocationServiceDep,
) -> OutputLocationResponse:
    return OutputLocationResponse.model_validate(service.get_payload())


@router.put("/system/output-location", response_model=OutputLocationResponse)
def put_output_location(
    req: OutputLocationUpdateReq,
    service: OutputLocationServiceDep,
) -> OutputLocationResponse:
    try:
        payload = service.set_data_root(req.data_root)
    except OutputLocationError as exc:
        raise_api_error(
            status_code=422,
            code="output_location_invalid",
            message=str(exc),
        )
    return OutputLocationResponse.model_validate(payload)
