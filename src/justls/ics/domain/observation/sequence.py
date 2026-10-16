from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

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
    RECOVERY_REQUIRED = "recovery_required"


class SequenceStepState(str, Enum):
    PENDING = "pending"
    EXPOSING = "exposing"
    COMPLETED = "completed"
    DISCARDED = "discarded"
    FAILED = "failed"


class SequenceRecoveryAction(str, Enum):
    RETRY_CURRENT_STEP = "retry_current_step"
    ABORT = "abort"
    MARK_FAILED = "mark_failed"


class SequenceActiveStep(BaseModel):
    """Durable identity for a step that may have touched the detector."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    setup_file_stem: str | None = None
    phase: Literal["reserved", "armed", "exposing"] = "reserved"
    obs_id: str | None = None
    exp_id: str | None = None
    reserved_at_utc: str = Field(default_factory=utc_now_iso)
    started_at_utc: str | None = None


class SequenceFrameReservation(BaseModel):
    """Frame indices consumed when a plan is loaded.

    Pending or aborted steps deliberately keep their reservation. Reusing those
    indices would make restart and operator recovery ambiguous.
    """

    model_config = ConfigDict(extra="forbid")

    start_index: int = Field(ge=1)
    count: int = Field(ge=1)
    end_index_exclusive: int = Field(ge=2)
    step_data_previews: list[dict[str, str]] = Field(min_length=1)
    reserved_at_utc: str = Field(default_factory=utc_now_iso)


class SequenceRecoveryInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Literal[
        "interrupted_active_step",
        "completed_data_product_mismatch",
        "persistence_failure",
        "acquisition_failure",
    ]
    interrupted_state: str
    interrupted_index: int = Field(ge=0)
    required_at_utc: str = Field(default_factory=utc_now_iso)
    detected_files: list[str] = Field(default_factory=list)
    file_issues: list[str] = Field(default_factory=list)
    retry_allowed: bool = False
    allowed_actions: list[SequenceRecoveryAction] = Field(default_factory=list)


class ObservationPlan(BaseModel):
    """Multi-exposure observing intent without execution side effects."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(default_factory=new_plan_id, min_length=1)
    target_name: str | None = None
    exposures: list[ExposureSpec] = Field(..., min_length=1, max_length=100)
    operator_note: str | None = None
    # Legacy persisted plans remain operator-stepped. New UI plans opt in.
    auto_advance: bool = False
    save_requested: bool = False
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

    schema_version: Literal[1] = 1
    plan: ObservationPlan
    state: SequenceExecutionState = SequenceExecutionState.LOADED
    current_index: int = Field(default=0, ge=0)
    active_exposure: bool = False
    active_step: SequenceActiveStep | None = None
    frame_reservation: SequenceFrameReservation | None = None
    recovery: SequenceRecoveryInfo | None = None
    step_results: list[SequenceStepResult] = Field(default_factory=list)
    created_at_utc: str = Field(default_factory=utc_now_iso)
    updated_at_utc: str = Field(default_factory=utc_now_iso)
    last_persisted_at_utc: str | None = None
    restored_at_utc: str | None = None
    message: str | None = None

    @model_validator(mode="after")
    def validate_durable_invariants(self) -> "SequenceExecutionSnapshot":
        total = len(self.plan.exposures)
        if self.current_index > total:
            raise ValueError("current_index must not exceed the number of plan steps")

        result_indices = [result.index for result in self.step_results]
        if len(result_indices) != len(set(result_indices)):
            raise ValueError("sequence step result indices must be unique")
        if any(index >= total for index in result_indices):
            raise ValueError("sequence step result index is outside the plan")

        if self.active_exposure and self.active_step is None:
            raise ValueError("active_exposure requires durable active_step identity")
        if self.active_step is not None:
            if self.current_index >= total or self.active_step.index != self.current_index:
                raise ValueError("active_step must identify the current plan step")

        if self.frame_reservation is not None:
            reservation = self.frame_reservation
            if reservation.count != total:
                raise ValueError("frame reservation count must match the plan")
            if len(reservation.step_data_previews) != reservation.count:
                raise ValueError("frame reservation must include one preview per step")
            if reservation.end_index_exclusive != reservation.start_index + reservation.count:
                raise ValueError("frame reservation index range is inconsistent")

        if (
            self.state == SequenceExecutionState.RECOVERY_REQUIRED
            and self.recovery is None
        ):
            raise ValueError("recovery_required state requires recovery details")
        return self

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
