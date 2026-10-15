import pytest
from pydantic import ValidationError

from justls.ics.domain.observation.models import (
    ExposureSpec,
    ObservationFrameType,
    ObservationPreviewResult,
    ObservationRequest,
    ReadinessItem,
    ReadinessSnapshot,
    ReadinessState,
    ValidationIssue,
    ValidationSeverity,
)


@pytest.mark.parametrize(
    "frame_type",
    ["science", "bias", "dark", "flat", "arc", "test"],
)
def test_exposure_spec_accepts_execution_compatible_frame_types(frame_type: str) -> None:
    spec = ExposureSpec(frame_type=frame_type, exp_time_s=30.0)

    assert spec.frame_type.value == frame_type
    assert spec.exp_time_s == 30.0


def test_exposure_spec_rejects_unknown_frame_type() -> None:
    with pytest.raises(ValidationError):
        ExposureSpec(frame_type="unknown", exp_time_s=30.0)


def test_observation_request_accepts_single_exposure_baseline() -> None:
    request = ObservationRequest(
        target_name="Target A",
        exposures=[
            ExposureSpec(
                frame_type=ObservationFrameType.SCIENCE,
                exp_time_s=30.0,
            )
        ],
        operator_note="single exposure preview",
        setup_context={"project_id": "P-001", "root_name": "science"},
    )

    assert request.single_exposure_spec() is not None
    assert request.single_exposure_spec().exp_time_s == 30.0
    assert request.compatibility_issues() == []


def test_observation_request_preserves_exposure_list_shape_but_flags_multiple_exposures() -> None:
    request = ObservationRequest(
        exposures=[
            ExposureSpec(frame_type="science", exp_time_s=30.0),
            ExposureSpec(frame_type="arc", exp_time_s=5.0),
        ]
    )

    issues = request.compatibility_issues()

    assert request.single_exposure_spec() is None
    assert len(issues) == 1
    assert issues[0].code == "multiple_exposures_not_supported"
    assert issues[0].severity == ValidationSeverity.ERROR
    assert issues[0].field == "exposures"


def test_observation_preview_result_is_side_effect_free_and_single_exposure_compatible() -> None:
    request = ObservationRequest(
        exposures=[ExposureSpec(frame_type="science", exp_time_s=30.0)]
    )

    preview = ObservationPreviewResult.from_request(request)

    assert preview.side_effect_free is True
    assert preview.blocked is False
    assert preview.single_exposure_compatible is True
    assert preview.validation_issues == []
    assert preview.readiness.tcs.state == ReadinessState.UNAVAILABLE


def test_observation_preview_blocks_multiple_exposures_without_sequence_runner() -> None:
    request = ObservationRequest(
        exposures=[
            ExposureSpec(frame_type="science", exp_time_s=30.0),
            ExposureSpec(frame_type="flat", exp_time_s=2.0),
        ]
    )

    preview = ObservationPreviewResult.from_request(request)

    assert preview.side_effect_free is True
    assert preview.blocked is True
    assert preview.single_exposure_compatible is False
    assert [issue.code for issue in preview.validation_issues] == [
        "multiple_exposures_not_supported"
    ]


def test_readiness_blocked_component_blocks_preview() -> None:
    request = ObservationRequest(
        exposures=[ExposureSpec(frame_type="flat", exp_time_s=2.0)]
    )
    readiness = ReadinessSnapshot(
        calibration=ReadinessItem(
            state=ReadinessState.BLOCKED,
            message="Lamp/mode is not compatible with requested frame type.",
        )
    )

    preview = ObservationPreviewResult.from_request(
        request,
        readiness=readiness,
    )

    assert preview.blocked is True
    assert preview.single_exposure_compatible is False
    assert preview.readiness.blocked_components() == ["calibration"]


def test_preview_can_carry_external_validation_issues() -> None:
    request = ObservationRequest(
        exposures=[ExposureSpec(frame_type="arc", exp_time_s=5.0)]
    )

    preview = ObservationPreviewResult.from_request(
        request,
        validation_issues=[
            ValidationIssue(
                code="calibration_source_unknown",
                severity=ValidationSeverity.WARNING,
                field="exposures.0.frame_type",
                message="Calibration source readiness is unknown.",
            )
        ],
    )

    assert preview.blocked is False
    assert preview.single_exposure_compatible is True
    assert preview.validation_issues[0].severity == ValidationSeverity.WARNING
