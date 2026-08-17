from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field

from justls.ics.domain.observation.models import (
    ExposureSpec,
    ObservationPreviewResult,
    utc_now_iso,
)


def new_plan_id() -> str:
    return f"plan-{uuid4().hex[:12]}"


class SequenceExecutionState(str, Enum):
    LOADED = "loaded"
    RUNNING = "running"
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


class SequenceStepState(str, Enum):
    PENDING = "pending"
    EXPOSING = "exposing"
    COMPLETED = "completed"
    DISCARDED = "discarded"
    FAILED = "failed"


class ObservationPlan(BaseModel):
    """Multi-exposure observing intent without execution side effects."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(default_factory=new_plan_id, min_length=1)
    target_name: str | None = None
    exposures: list[ExposureSpec] = Field(..., min_length=1, max_length=100)
    operator_note: str | None = None
    setup_context: dict[str, Any] | None = None


class SequenceStepPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    exposure: ExposureSpec
    preview: ObservationPreviewResult


class SequencePreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: ObservationPlan
    steps: list[SequenceStepPreview]
    side_effect_free: bool = True
    executable: bool
    blocked: bool


class SequenceStepResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    exposure: ExposureSpec
    state: SequenceStepState
    exposure_record: dict[str, Any] | None = None
    message: str | None = None


class SequenceExecutionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: ObservationPlan
    state: SequenceExecutionState = SequenceExecutionState.LOADED
    current_index: int = Field(default=0, ge=0)
    active_exposure: bool = False
    step_results: list[SequenceStepResult] = Field(default_factory=list)
    created_at_utc: str = Field(default_factory=utc_now_iso)
    updated_at_utc: str = Field(default_factory=utc_now_iso)
    message: str | None = None

    @computed_field
    @property
    def total_steps(self) -> int:
        return len(self.plan.exposures)

    @computed_field
    @property
    def completed_steps(self) -> int:
        return len(
            [
                result
                for result in self.step_results
                if result.state == SequenceStepState.COMPLETED
            ]
        )

    def current_exposure(self) -> ExposureSpec | None:
        if self.current_index >= self.total_steps:
            return None
        return self.plan.exposures[self.current_index]

    def to_status_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.update(
            {
                "current_exposure": (
                    self.current_exposure().model_dump(mode="json")
                    if self.current_exposure() is not None
                    else None
                ),
            }
        )
        return payload
