from __future__ import annotations

from fastapi import APIRouter

from justls.ics.app.api.dependencies import ManagementServiceDep
from justls.ics.app.api.errors import raise_api_error
from justls.ics.app.api.schemas.presets import PresetApplyReq
from justls.ics.app.api.schemas.responses import (
    ApiErrorResponse,
    PresetApplyResponse,
    PresetListResponse,
    PresetPreviewResponse,
)
from justls.ics.application.services.management_service import PresetConfirmationRequiredError
from justls.ics.application.usecases.presets import build_preset_plan, list_presets
from justls.ics.kernel.errors import InvalidStateError

router = APIRouter(prefix="/api/v1", tags=["presets"])


def _build_plan_or_404(name: str):
    try:
        return build_preset_plan(name)
    except KeyError:
        raise_api_error(
            status_code=404,
            code="preset_not_found",
            message=f"Preset not found: {name}",
        )


@router.get("/presets", response_model=PresetListResponse)
def get_presets() -> PresetListResponse:
    return PresetListResponse(items=list_presets())


@router.post(
    "/presets/preview",
    response_model=PresetPreviewResponse,
    responses={404: {"model": ApiErrorResponse, "description": "Preset not found"}},
)
def preview_preset(
    req: PresetApplyReq,
    management_service: ManagementServiceDep,
) -> PresetPreviewResponse:
    plan = _build_plan_or_404(req.name)
    payload = management_service.preview_preset_plan(plan)
    return PresetPreviewResponse.model_validate(payload)


@router.post(
    "/presets/apply",
    response_model=PresetApplyResponse,
    responses={
        400: {"model": ApiErrorResponse, "description": "Preset blocked or confirmation required"},
        404: {"model": ApiErrorResponse, "description": "Preset not found"},
    },
)
def apply_preset(
    req: PresetApplyReq,
    management_service: ManagementServiceDep,
) -> PresetApplyResponse:
    plan = _build_plan_or_404(req.name)

    try:
        payload = management_service.apply_preset_plan(plan, confirmed=req.confirmed)
    except PresetConfirmationRequiredError as exc:
        raise_api_error(
            status_code=400,
            code=exc.code.value if hasattr(exc.code, "value") else str(exc.code),
            message=exc.info.message,
            **exc.info.details,
        )
    except InvalidStateError as exc:
        raise_api_error(
            status_code=400,
            code=exc.code.value,
            message=exc.info.message,
        )

    return PresetApplyResponse.model_validate(payload)
