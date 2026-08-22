from __future__ import annotations

import pytest

from justls.ics.application.services.observation_preview_service import (
    ObservationPreviewService,
)
from justls.ics.application.services.setup_context_service import SetupContextService
from justls.ics.domain.observation.models import (
    ExposureSpec,
    ObservationRequest,
    ReadinessState,
)
from justls.ics.domain.setup import SessionDataContext
from justls.ics.kernel.runtime import RuntimeAssembler


def test_preview_request_attaches_setup_context_when_missing() -> None:
    runtime = RuntimeAssembler().build()
    setup_service = SetupContextService(
        SessionDataContext(
            observers="Observer",
            project_id="P-001",
            pi_name="PI",
            support_operator="Support",
            root_name="science",
            date_prefix="20260527",
            comment="night setup",
            next_frame_index=5,
            data_directory="/data/just",
        )
    )
    service = ObservationPreviewService(
        runtime=runtime,
        setup_context_service=setup_service,
    )

    preview = service.preview_request(
        ObservationRequest(
            target_name="Target A",
            exposures=[ExposureSpec(frame_type="science", exp_time_s=30.0)],
        )
    )

    assert preview.side_effect_free is True
    assert preview.blocked is False
    assert preview.single_exposure_compatible is True
    assert preview.request.setup_context == {
        "observers": "Observer",
        "project_id": "P-001",
        "pi_name": "PI",
        "support_operator": "Support",
        "root_name": "science",
        "date_prefix": "20260527",
        "comment": "night setup",
        "next_frame_index": 5,
        "data_directory": "/data/just",
    }


def test_preview_request_preserves_explicit_setup_context() -> None:
    runtime = RuntimeAssembler().build()
    setup_service = SetupContextService(
        SessionDataContext(root_name="service_default", date_prefix="20260527")
    )
    service = ObservationPreviewService(
        runtime=runtime,
        setup_context_service=setup_service,
    )

    preview = service.preview_request(
        ObservationRequest(
            exposures=[ExposureSpec(frame_type="science", exp_time_s=30.0)],
            setup_context={"root_name": "explicit"},
        )
    )

    assert preview.request.setup_context == {"root_name": "explicit"}


def test_preview_request_is_side_effect_free_and_does_not_create_jobs() -> None:
    runtime = RuntimeAssembler().build()
    service = ObservationPreviewService(runtime=runtime)

    before_state = runtime.detector.get_snapshot().state
    before_job = runtime.latest_job()

    preview = service.preview_request(
        ObservationRequest(
            exposures=[ExposureSpec(frame_type="science", exp_time_s=30.0)]
        )
    )

    after_state = runtime.detector.get_snapshot().state
    after_job = runtime.latest_job()

    assert preview.side_effect_free is True
    assert before_state == after_state
    assert before_job is None
    assert after_job is None


def test_preview_blocks_when_detector_is_already_armed() -> None:
    runtime = RuntimeAssembler().build()
    runtime.detector.arm(exp_time_s=5.0, frame_type="science")
    service = ObservationPreviewService(runtime=runtime)

    preview = service.preview_request(
        ObservationRequest(
            exposures=[ExposureSpec(frame_type="science", exp_time_s=30.0)]
        )
    )

    assert preview.blocked is True
    assert preview.single_exposure_compatible is False
    assert preview.readiness.detector.state == ReadinessState.BLOCKED


def test_preview_blocks_science_frame_when_calibration_lamp_is_inserted() -> None:
    runtime = RuntimeAssembler().build()
    runtime.lamps.select_lamp("flat", enable=True)
    service = ObservationPreviewService(runtime=runtime)

    preview = service.preview_request(
        ObservationRequest(
            exposures=[ExposureSpec(frame_type="science", exp_time_s=30.0)]
        )
    )

    assert preview.blocked is True
    assert preview.single_exposure_compatible is False
    assert preview.readiness.calibration.state == ReadinessState.BLOCKED
    assert [issue.code for issue in preview.validation_issues] == [
        "science_calibration_not_ready"
    ]


@pytest.mark.parametrize("frame_type", ["bias", "dark"])
def test_preview_allows_detector_calibration_frames_with_lamps_off(
    frame_type: str,
) -> None:
    runtime = RuntimeAssembler().build()
    service = ObservationPreviewService(runtime=runtime)

    preview = service.preview_request(
        ObservationRequest(
            exposures=[ExposureSpec(frame_type=frame_type, exp_time_s=0.01)]
        )
    )

    assert preview.blocked is False
    assert preview.readiness.calibration.state == ReadinessState.READY


@pytest.mark.parametrize("frame_type", ["bias", "dark"])
def test_preview_blocks_detector_calibration_frames_with_lamp_inserted(
    frame_type: str,
) -> None:
    runtime = RuntimeAssembler().build()
    runtime.lamps.select_lamp("flat", enable=True)
    service = ObservationPreviewService(runtime=runtime)

    preview = service.preview_request(
        ObservationRequest(
            exposures=[ExposureSpec(frame_type=frame_type, exp_time_s=0.01)]
        )
    )

    assert preview.blocked is True
    assert [issue.code for issue in preview.validation_issues] == [
        f"{frame_type}_calibration_not_ready"
    ]


def test_preview_allows_flat_frame_when_flat_lamp_is_enabled() -> None:
    runtime = RuntimeAssembler().build()
    runtime.lamps.select_lamp("flat", enable=True)
    service = ObservationPreviewService(runtime=runtime)

    preview = service.preview_request(
        ObservationRequest(
            exposures=[ExposureSpec(frame_type="flat", exp_time_s=2.0)]
        )
    )

    assert preview.blocked is False
    assert preview.single_exposure_compatible is True
    assert preview.readiness.calibration.state == ReadinessState.READY


def test_preview_blocks_arc_frame_when_flat_lamp_is_enabled() -> None:
    runtime = RuntimeAssembler().build()
    runtime.lamps.select_lamp("flat", enable=True)
    service = ObservationPreviewService(runtime=runtime)

    preview = service.preview_request(
        ObservationRequest(
            exposures=[ExposureSpec(frame_type="arc", exp_time_s=5.0)]
        )
    )

    assert preview.blocked is True
    assert preview.single_exposure_compatible is False
    assert preview.readiness.calibration.state == ReadinessState.BLOCKED
    assert [issue.code for issue in preview.validation_issues] == [
        "arc_calibration_not_ready"
    ]
