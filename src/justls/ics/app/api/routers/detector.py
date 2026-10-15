from __future__ import annotations

from fastapi import APIRouter

from justls.ics.app.api.dependencies import ManagementServiceDep
from justls.ics.app.api.errors import raise_api_error
from justls.ics.domain.detector.config import DetectorConfig
from justls.ics.kernel.errors import InvalidStateError

router = APIRouter(prefix="/api/v1", tags=["detector"])


@router.get("/detector/config", response_model=DetectorConfig)
def get_detector_config(management_service: ManagementServiceDep) -> DetectorConfig:
    return DetectorConfig.model_validate(management_service.get_detector_config_dict())


@router.post("/detector/config", response_model=DetectorConfig)
def set_detector_config(
    req: DetectorConfig,
    management_service: ManagementServiceDep,
) -> DetectorConfig:
    try:
        payload = management_service.set_detector_config(req)
    except InvalidStateError as exc:
        raise_api_error(
            status_code=400,
            code=exc.code.value,
            message=exc.info.message,
        )
    return DetectorConfig.model_validate(payload)
