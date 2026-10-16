from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from justls.ics.domain.observation.models import ExposureSpec, ObservationRequest, validate_exposure_time


FrameTypeLiteral = Literal["science", "bias", "dark", "flat", "arc", "test"]
ReadinessStateLiteral = Literal["ready", "blocked", "unknown", "unavailable"]
ValidationSeverityLiteral = Literal["info", "warning", "error"]


class ExposureSpecReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame_type: FrameTypeLiteral = "science"
    exp_time_s: float = Field(..., ge=0, allow_inf_nan=False)
    label: str | None = None

    @model_validator(mode="after")
    def validate_time(self):
        validate_exposure_time(self.exp_time_s, self.frame_type)
        return self

    def to_domain(self) -> ExposureSpec:
        return ExposureSpec(
            frame_type=self.frame_type,
            exp_time_s=self.exp_time_s,
            label=self.label,
        )


class ObservationPreviewReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str | None = None
    target_name: str | None = None
    exposures: list[ExposureSpecReq] = Field(..., min_length=1)
    operator_note: str | None = None
    setup_context: dict[str, Any] | None = None

    def to_domain(self) -> ObservationRequest:
        return ObservationRequest(
            request_id=self.request_id,
            target_name=self.target_name,
            exposures=[spec.to_domain() for spec in self.exposures],
            operator_note=self.operator_note,
            setup_context=self.setup_context,
        )


class ExposureSpecResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame_type: FrameTypeLiteral
    exp_time_s: float
    label: str | None = None


class ObservationRequestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str | None = None
    target_name: str | None = None
    exposures: list[ExposureSpecResponse]
    operator_note: str | None = None
    setup_context: dict[str, Any] | None = None


class ValidationIssueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: ValidationSeverityLiteral
    message: str
    field: str | None = None


class ReadinessItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: ReadinessStateLiteral
    message: str | None = None
    updated_at_utc: str | None = None


class ReadinessSnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detector: ReadinessItemResponse
    calibration: ReadinessItemResponse
    slit: ReadinessItemResponse
    tcs: ReadinessItemResponse


class ObservationPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: ObservationRequestResponse
    readiness: ReadinessSnapshotResponse
    validation_issues: list[ValidationIssueResponse]
    side_effect_free: bool
    single_exposure_compatible: bool
    blocked: bool
