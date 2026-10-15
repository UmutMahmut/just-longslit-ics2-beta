from __future__ import annotations

from fastapi import APIRouter

from justls.ics.app.api.dependencies import ObservatoryContextServiceDep
from justls.ics.domain.observatory.context import ObservatoryContext

router = APIRouter(prefix="/api/v1", tags=["observatory"])


@router.get("/observatory/context", response_model=ObservatoryContext)
def read_observatory_context(
    observatory_context_service: ObservatoryContextServiceDep,
) -> ObservatoryContext:
    return ObservatoryContext.model_validate(
        observatory_context_service.get_context()
    )
