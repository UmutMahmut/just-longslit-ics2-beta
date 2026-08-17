from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from justls.ics.domain.observation.models import ObservationCommandFeedback

from .observation_preview import ObservationPreviewResponse, ValidationIssueResponse


class ObservationArmReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exp_time_s: float = Field(..., gt=0)
    frame_type: Literal["science", "flat", "arc", "test"] = "science"
    operator_note: str | None = None
    save_requested: bool = False


ObservationCommandLiteral = Literal[
    "status",
    "preview",
    "arm",
    "start",
    "finish",
    "stop_readout",
    "abort_discard",
]
ObservationCommandStatusLiteral = Literal["succeeded", "blocked", "failed"]
ObservationCommandBlockedReasonLiteral = Literal[
    "readiness_gate",
    "interlock",
    "validation",
    "api_error",
    "unknown",
]


class ObservationCommandErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any] | None = None


class ObservationCommandFeedbackResponse(BaseModel):
    """API response schema for normalized observation command feedback.

    The Preview action is advisory and independent from Arm. Arm responses may
    include the backend gate's preview snapshot when the arm command is blocked,
    but the UI Preview result is not a prerequisite for Arm.
    """

    model_config = ConfigDict(extra="forbid")

    command: ObservationCommandLiteral
    ok: bool
    status: ObservationCommandStatusLiteral
    message: str | None = None
    request_id: str | None = None
    observation_state: str | None = None
    latest_job: dict[str, Any] | None = None
    error: ObservationCommandErrorResponse | None = None
    blocked: bool = False
    blocked_reason: ObservationCommandBlockedReasonLiteral | None = None
    blocked_components: list[str] = Field(default_factory=list)
    preview: ObservationPreviewResponse | None = None
    validation_issues: list[ValidationIssueResponse] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(
        cls,
        feedback: ObservationCommandFeedback,
    ) -> "ObservationCommandFeedbackResponse":
        return cls.model_validate(feedback.model_dump(mode="json"))
