from __future__ import annotations

from fastapi import APIRouter

from justls.ics.app.api.dependencies import HealthServiceDep
from justls.ics.app.api.schemas.responses import (
    CapabilitiesResponse,
    HealthResponse,
    StateDtoResponse,
    StatusFullResponse,
)

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/health", response_model=HealthResponse)
def read_health(health_service: HealthServiceDep) -> HealthResponse:
    return HealthResponse.model_validate(health_service.get_health())


@router.get("/status", response_model=StateDtoResponse)
def read_status(health_service: HealthServiceDep) -> StateDtoResponse:
    return StateDtoResponse.model_validate(health_service.get_state_dto())


@router.get("/status/full", response_model=StatusFullResponse)
def read_status_full(health_service: HealthServiceDep) -> StatusFullResponse:
    return StatusFullResponse.model_validate(health_service.get_status_full())


@router.get("/capabilities", response_model=CapabilitiesResponse)
def read_capabilities(health_service: HealthServiceDep) -> CapabilitiesResponse:
    return CapabilitiesResponse.model_validate(health_service.get_capabilities())