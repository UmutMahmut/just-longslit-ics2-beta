from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from urllib.parse import urlparse
from urllib.request import url2pathname

from justls.ics.app.api.dependencies import (
    get_dispatcher,
    get_observation_preview_service,
    get_observation_service,
    get_setup_context_service,
)
from justls.ics.application.services.observation_sequence_service import (
    ObservationSequenceService,
)
from justls.ics.application.services.observation_sequence_store import (
    InMemoryObservationSequenceStore,
)
from justls.ics.application.services.setup_context_service import SetupContextService
from justls.ics.application.services.setup_context_store import InMemorySetupContextStore
from justls.ics.domain.observation.models import ExposureSpec
from justls.ics.domain.observation.sequence import (
    ObservationPlan,
    SequenceExecutionState,
    SequenceStepState,
)
from justls.ics.domain.setup import SessionDataContext
from justls.ics.kernel.runtime import reset_runtime


def _service() -> ObservationSequenceService:
    runtime = reset_runtime()
    setup = get_setup_context_service()
    return _service_for(runtime, setup=setup)


def _service_for(
    runtime,
    *,
    setup: SetupContextService,
    store: InMemoryObservationSequenceStore | None = None,
) -> ObservationSequenceService:
    dispatcher = get_dispatcher(runtime)
    observation = get_observation_service(runtime, dispatcher, setup)
    preview = get_observation_preview_service(runtime, setup)
    return ObservationSequenceService(
        runtime,
        observation,
        preview,
        setup,
        store,
    )


def _file_path(uri: str) -> Path:
    return Path(url2pathname(urlparse(uri).path))


def _science_plan(*, save_requested: bool = False) -> ObservationPlan:
    return ObservationPlan(
        plan_id="plan-service",
        target_name="Vega",
        exposures=[
            ExposureSpec(frame_type="science", exp_time_s=1, label="one"),
            ExposureSpec(frame_type="science", exp_time_s=2, label="two"),
        ],
        operator_note="sequence test",
        save_requested=save_requested,
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

    loaded = service.load(_science_plan(save_requested=True))
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


def test_sequence_load_reserves_frame_indices_once() -> None:
    runtime = reset_runtime()
    setup = SetupContextService(
        store=InMemorySetupContextStore(
            SessionDataContext(
                root_name="science",
                date_prefix="20260817",
                next_frame_index=7,
            )
        )
    )
    service = _service_for(runtime, setup=setup)

    loaded = service.load(_science_plan(save_requested=True)).sequence

    assert loaded.frame_reservation.start_index == 7
    assert loaded.frame_reservation.end_index_exclusive == 9
    assert [
        item["file_stem"] for item in loaded.frame_reservation.step_data_previews
    ] == ["science_20260817_0007", "science_20260817_0008"]
    assert setup.get_context().next_frame_index == 9

    service.abort()
    next_plan = _science_plan(save_requested=True).model_copy(update={"plan_id": "plan-next"})
    next_loaded = service.load(next_plan).sequence
    assert next_loaded.frame_reservation.start_index == 9
    assert setup.get_context().next_frame_index == 11


def test_unsaved_sequence_does_not_consume_frame_indices() -> None:
    runtime = reset_runtime()
    setup = SetupContextService(
        store=InMemorySetupContextStore(
            SessionDataContext(
                root_name="science",
                date_prefix="20260817",
                next_frame_index=7,
            )
        )
    )
    service = _service_for(runtime, setup=setup)

    loaded = service.load(_science_plan()).sequence
    assert loaded.frame_reservation is None
    assert setup.get_context().next_frame_index == 7

    service.start()
    completed = service.finish_step().sequence.step_results[0].exposure_record
    assert completed["save_requested"] is False
    assert completed["data_product_state"] == "not_requested"
    assert completed["primary_data_product"]["uri"] is None


def test_restart_during_active_step_requires_explicit_retry() -> None:
    store = InMemoryObservationSequenceStore()
    setup = SetupContextService(store=InMemorySetupContextStore())
    first = _service_for(reset_runtime(), setup=setup, store=store)
    first.load(_science_plan())
    first.start()

    restored = _service_for(reset_runtime(), setup=setup, store=store)
    snapshot = restored.status()

    assert snapshot.state == SequenceExecutionState.RECOVERY_REQUIRED
    assert snapshot.active_exposure is False
    assert snapshot.active_step.phase == "exposing"
    assert snapshot.recovery.reason == "interrupted_active_step"
    assert snapshot.recovery.retry_allowed is True
    assert "retry_current_step" in snapshot.recovery.allowed_actions

    retried = restored.retry_current_step()
    assert retried.ok is True
    assert retried.sequence.state == SequenceExecutionState.LOADED
    assert retried.sequence.active_step is None
    assert retried.sequence.recovery is None


def test_restart_restores_loaded_plan_without_false_recovery() -> None:
    store = InMemoryObservationSequenceStore()
    setup = SetupContextService(store=InMemorySetupContextStore())
    first = _service_for(reset_runtime(), setup=setup, store=store)
    loaded = first.load(_science_plan(save_requested=True)).sequence

    restored = _service_for(reset_runtime(), setup=setup, store=store).status()

    assert restored.state == SequenceExecutionState.LOADED
    assert restored.recovery is None
    assert restored.restored_at_utc is not None
    assert restored.frame_reservation == loaded.frame_reservation


def test_restart_blocks_retry_when_interrupted_step_may_have_written_fits() -> None:
    store = InMemoryObservationSequenceStore()
    setup = SetupContextService(store=InMemorySetupContextStore())
    first_runtime = reset_runtime()
    first = _service_for(first_runtime, setup=setup, store=store)
    first.load(_science_plan(save_requested=True))
    active = first.start().sequence.active_step
    output = Path(first_runtime.data_root) / "recovery-test" / "obs"
    output.mkdir(parents=True, exist_ok=True)
    (output / f"{active.exp_id}-possible.fits").write_bytes(b"possible fits")

    restored = _service_for(reset_runtime(), setup=setup, store=store)
    snapshot = restored.status()

    assert snapshot.state == SequenceExecutionState.RECOVERY_REQUIRED
    assert snapshot.recovery.retry_allowed is False
    assert snapshot.recovery.detected_files
    rejected = restored.retry_current_step()
    assert rejected.ok is False
    assert rejected.error.info.details["detected_files"]

    failed = restored.mark_failed()
    assert failed.ok is True
    assert failed.sequence.state == SequenceExecutionState.FAILED
    terminal = _service_for(reset_runtime(), setup=setup, store=store)
    assert terminal.status().state == SequenceExecutionState.FAILED


def test_restart_reconciles_completed_data_product_files() -> None:
    store = InMemoryObservationSequenceStore()
    setup = SetupContextService(store=InMemorySetupContextStore())
    first = _service_for(reset_runtime(), setup=setup, store=store)
    first.load(_science_plan(save_requested=True))
    first.start()
    completed_step = first.finish_step().sequence.step_results[0]

    safely_restored = _service_for(reset_runtime(), setup=setup, store=store)
    assert safely_restored.status().state == SequenceExecutionState.RUNNING
    assert safely_restored.status().current_index == 1

    fits_uri = completed_step.exposure_record["primary_data_product"]["uri"]
    _file_path(fits_uri).unlink()
    mismatched = _service_for(reset_runtime(), setup=setup, store=store)

    assert mismatched.status().state == SequenceExecutionState.RECOVERY_REQUIRED
    assert mismatched.status().recovery.reason == "completed_data_product_mismatch"
    assert mismatched.status().recovery.retry_allowed is False
    assert "missing primary_data_product" in mismatched.status().recovery.file_issues[0]


def test_restart_detects_completed_fits_checksum_mismatch() -> None:
    store = InMemoryObservationSequenceStore()
    setup = SetupContextService(store=InMemorySetupContextStore())
    first = _service_for(reset_runtime(), setup=setup, store=store)
    first.load(_science_plan(save_requested=True))
    first.start()
    completed = first.finish_step().sequence.step_results[0]
    fits_uri = completed.exposure_record["primary_data_product"]["uri"]
    _file_path(fits_uri).write_bytes(b"corrupted after durable record")

    restored = _service_for(reset_runtime(), setup=setup, store=store)

    assert restored.status().state == SequenceExecutionState.RECOVERY_REQUIRED
    assert any(
        "FITS checksum mismatch" in issue
        for issue in restored.status().recovery.file_issues
    )


def test_concurrent_sequence_starts_cannot_start_the_same_step_twice() -> None:
    service = _service()
    service.load(_science_plan())
    barrier = Barrier(2)

    def start_after_barrier():
        barrier.wait()
        return service.start()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: start_after_barrier(), range(2)))

    assert sorted(result.ok for result in results) == [False, True]
    assert service.status().active_exposure is True
    assert service.status().active_step.phase == "exposing"


def test_auto_advance_commits_frame_before_starting_next(monkeypatch) -> None:
    service = _service()
    plan = _science_plan().model_copy(update={"auto_advance": True})
    service.load(plan)
    assert service.start().ok
    persisted = []
    original = service._persist
    def remember(snapshot):
        original(snapshot)
        persisted.append((snapshot.current_index, snapshot.active_exposure))
    monkeypatch.setattr(service, "_persist", remember)
    result = service.finish_step()
    assert result.ok
    assert (1, False) in persisted
    assert persisted.index((1, False)) < persisted.index((1, True))
    assert result.sequence.current_index == 1
    assert result.sequence.active_exposure
    assert service.finish_step().sequence.state == SequenceExecutionState.COMPLETED


def test_auto_advance_pause_resume_and_abort() -> None:
    service = _service()
    service.load(_science_plan().model_copy(update={"auto_advance": True}))
    service.start()
    service.pause()
    paused = service.finish_step().sequence
    assert paused.state == SequenceExecutionState.PAUSED
    assert not paused.active_exposure
    assert service.resume().sequence.active_exposure
    aborted = service.abort().sequence
    assert aborted.state == SequenceExecutionState.ABORTED
    assert not aborted.active_exposure


def test_auto_advance_runs_on_backend_without_browser(monkeypatch) -> None:
    import time
    monkeypatch.setenv("JUSTLS_AUTO_READOUT_ENABLED", "1")
    service = _service()
    service.load(ObservationPlan(auto_advance=True, exposures=[
        ExposureSpec(frame_type="bias", exp_time_s=0),
        ExposureSpec(frame_type="test", exp_time_s=0.02),
        ExposureSpec(frame_type="test", exp_time_s=0.02),
    ]))
    assert service.start().ok
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with service.runtime.sequence_lock:
            if service.status().state == SequenceExecutionState.COMPLETED:
                break
        time.sleep(0.01)
    snapshot = service.status()
    assert snapshot.state == SequenceExecutionState.COMPLETED
    assert len(snapshot.step_results) == 3
    assert service.runtime.readout_scheduler.last_error is None
    service.runtime.shutdown()


def test_auto_advance_stops_after_next_start_rejection(monkeypatch) -> None:
    from justls.ics.kernel.errors import InvalidStateError
    service = _service()
    service.load(_science_plan().model_copy(update={"auto_advance": True}))
    service.start()
    calls = []
    def blocked():
        calls.append(True)
        raise InvalidStateError("test readiness changed", subsystem="observation_sequence")
    monkeypatch.setattr(service, "_start", blocked)
    result = service.finish_step()
    assert not result.ok
    assert len(calls) == 1
    assert result.sequence.current_index == 1
    assert not result.sequence.active_exposure
    assert len(result.sequence.step_results) == 1


def test_auto_advance_persistence_failure_does_not_start_next(monkeypatch) -> None:
    from justls.ics.kernel.errors import InvalidStateError
    service = _service()
    service.load(_science_plan().model_copy(update={"auto_advance": True}))
    service.start()
    def unavailable(snapshot):
        raise InvalidStateError("test persistence failure", subsystem="observation_sequence")
    monkeypatch.setattr(service, "_persist", unavailable)
    result = service.finish_step()
    assert not result.ok
    assert result.sequence.current_index == 1
    assert not result.sequence.active_exposure


def test_restored_auto_plan_waits_for_operator_start() -> None:
    runtime = reset_runtime()
    setup = get_setup_context_service()
    store = InMemoryObservationSequenceStore()
    service = _service_for(runtime, setup=setup, store=store)
    service.load(_science_plan().model_copy(update={"auto_advance": True}))
    restored = _service_for(reset_runtime(), setup=setup, store=store).status()
    assert restored.plan.auto_advance is True
    assert restored.state == SequenceExecutionState.LOADED
    assert not restored.active_exposure
