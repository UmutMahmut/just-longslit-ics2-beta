from __future__ import annotations

from justls.ics.app.api.dependencies import (
    get_dispatcher,
    get_observation_preview_service,
    get_observation_service,
    get_setup_context_service,
)
from justls.ics.application.services.observation_sequence_service import (
    ObservationSequenceService,
)
from justls.ics.domain.observation.models import ExposureSpec
from justls.ics.domain.observation.sequence import (
    ObservationPlan,
    SequenceExecutionState,
    SequenceStepState,
)
from justls.ics.kernel.runtime import reset_runtime


def _service() -> ObservationSequenceService:
    runtime = reset_runtime()
    setup = get_setup_context_service()
    dispatcher = get_dispatcher(runtime)
    observation = get_observation_service(runtime, dispatcher, setup)
    preview = get_observation_preview_service(runtime, setup)
    return ObservationSequenceService(runtime, observation, preview, setup)


def _science_plan() -> ObservationPlan:
    return ObservationPlan(
        plan_id="plan-service",
        target_name="Vega",
        exposures=[
            ExposureSpec(frame_type="science", exp_time_s=1, label="one"),
            ExposureSpec(frame_type="science", exp_time_s=2, label="two"),
        ],
        operator_note="sequence test",
    )


def test_sequence_preview_is_side_effect_free_for_each_step() -> None:
    service = _service()

    preview = service.preview_plan(_science_plan())

    assert preview.executable is True
    assert preview.blocked is False
    assert len(preview.steps) == 2
    assert all(step.preview.side_effect_free for step in preview.steps)
    assert service.status() is None


def test_sequence_runs_two_steps_and_retains_exposure_records() -> None:
    service = _service()

    loaded = service.load(_science_plan())
    assert loaded.ok is True
    assert loaded.sequence.state == SequenceExecutionState.LOADED

    assert service.start().sequence.active_exposure is True
    first = service.finish_step().sequence
    assert first.current_index == 1
    assert first.state == SequenceExecutionState.RUNNING
    assert first.step_results[0].state == SequenceStepState.COMPLETED
    assert first.step_results[0].exposure_record["data_product_state"] == "available"
    assert first.step_results[0].exposure_record["fits_header"]["setup_file_stem"].endswith("_0001")

    assert service.start().sequence.active_exposure is True
    completed = service.finish_step().sequence
    assert completed.state == SequenceExecutionState.COMPLETED
    assert completed.completed_steps == 2
    assert len(completed.step_results) == 2
    assert completed.step_results[1].exposure_record["fits_header"]["setup_file_stem"].endswith("_0002")


def test_sequence_pause_requested_takes_effect_after_active_step() -> None:
    service = _service()
    service.load(_science_plan())
    service.start()

    pause_requested = service.pause().sequence
    assert pause_requested.state == SequenceExecutionState.PAUSE_REQUESTED
    assert pause_requested.active_exposure is True

    paused = service.finish_step().sequence
    assert paused.state == SequenceExecutionState.PAUSED
    assert paused.active_exposure is False

    resumed = service.resume().sequence
    assert resumed.state == SequenceExecutionState.RUNNING


def test_sequence_abort_discards_active_step() -> None:
    service = _service()
    service.load(_science_plan())
    service.start()

    aborted = service.abort().sequence

    assert aborted.state == SequenceExecutionState.ABORTED
    assert aborted.active_exposure is False
    assert aborted.step_results[0].state == SequenceStepState.DISCARDED
    assert aborted.step_results[0].exposure_record["data_product_state"] == "not_created"
