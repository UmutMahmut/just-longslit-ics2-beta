from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from justls.ics.app.api.schemas.observation import ObservationCommandErrorResponse
from justls.ics.app.api.schemas.observation_preview import ExposureSpecReq
from justls.ics.domain.observation.sequence import (
    ObservationPlan,
    SequenceExecutionSnapshot,
)


class ObservationPlanReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str | None = None
    target_name: str | None = None
    exposures: list[ExposureSpecReq] = Field(..., min_length=1, max_length=100)
    operator_note: str | None = None
    auto_advance: bool = False
    save_requested: bool = False
    setup_context: dict[str, Any] | None = None

    def to_domain(self) -> ObservationPlan:
        payload: dict[str, Any] = {
            "target_name": self.target_name,
            "exposures": [spec.to_domain() for spec in self.exposures],
            "operator_note": self.operator_note,
            "auto_advance": self.auto_advance,
            "save_requested": self.save_requested,
            "setup_context": self.setup_context,
        }
        if self.plan_id is not None:
            payload["plan_id"] = self.plan_id
        return ObservationPlan.model_validate(payload)


SequenceCommandLiteral = Literal[
    "load",
    "start",
    "finish_step",
    "stop_readout_step",
    "pause",
    "resume",
    "abort",
    "retry_current_step",
    "mark_failed",
]


class SequenceCommandFeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: SequenceCommandLiteral
    ok: bool
    status: Literal["succeeded", "blocked", "failed"]
    message: str
    request_id: str | None = None
    latest_job: dict[str, Any]
    sequence: SequenceExecutionSnapshot | None = None
    error: ObservationCommandErrorResponse | None = None
