from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from justls.ics.application.services.observation_preview_service import (
    ObservationPreviewService,
)
from justls.ics.application.services.observation_service import ObservationService
from justls.ics.application.services.observation_sequence_store import (
    InMemoryObservationSequenceStore,
    ObservationSequenceStore,
    initialize_runtime_sequence,
)
from justls.ics.application.services.setup_context_service import SetupContextService
from justls.ics.domain.observation.models import ObservationRequest, utc_now_iso
from justls.ics.domain.observation.sequence import (
    ObservationPlan,
    SequenceExecutionSnapshot,
    SequenceExecutionState,
    SequenceActiveStep,
    SequenceFrameReservation,
    SequencePreview,
    SequenceRecoveryAction,
    SequenceRecoveryInfo,
    SequenceStepPreview,
    SequenceStepResult,
    SequenceStepState,
)
from justls.ics.domain.setup.context import SessionDataContext
from justls.ics.kernel.errors import ICSException, InterlockBlockedError, InvalidStateError
from justls.ics.kernel.jobs import CommandRequest, JobRecord
from justls.ics.kernel.runtime import Runtime
from justls.ics.kernel.states import CommandSource


@dataclass(slots=True)
class SequenceCommandResult:
    command: str
    ok: bool
    sequence: SequenceExecutionSnapshot | None
    job: JobRecord
    error: ICSException | None = None


class ObservationSequenceService:
    """Audited, in-memory coordinator over the existing single-exposure path.

    Each sequence step is armed, started, and completed through
    ObservationService, so the existing readiness gate and ExposureRecord
    contract remain authoritative.

    A step is read out automatically once its requested integration time has
    elapsed (hardware exposures cannot wait for an operator to click
    "finish"); the operator still starts the next step explicitly.
    """

    def __init__(
        self,
        runtime: Runtime,
        observation_service: ObservationService,
        preview_service: ObservationPreviewService,
        setup_context_service: SetupContextService | None = None,
        state_store: ObservationSequenceStore | None = None,
    ) -> None:
        self.runtime = runtime
        self.observation_service = observation_service
        self.preview_service = preview_service
        self.setup_context_service = setup_context_service
        self.state_store = state_store or InMemoryObservationSequenceStore()
        initialize_runtime_sequence(runtime, self.state_store)

    def status(self) -> SequenceExecutionSnapshot | None:
        return self.runtime.sequence_execution

    def preview_plan(self, plan: ObservationPlan) -> SequencePreview:
        resolved_plan = self._attach_setup_context(plan)
        steps: list[SequenceStepPreview] = []
        for index, exposure in enumerate(resolved_plan.exposures):
            setup_context, _ = self._step_setup_payloads(resolved_plan, index)
            request = ObservationRequest(
                target_name=resolved_plan.target_name,
                exposures=[exposure],
                operator_note=self._step_note(resolved_plan, exposure.label),
                setup_context=setup_context,
            )
            preview = self.preview_service.preview_request(request)
            steps.append(
                SequenceStepPreview(
                    index=index,
                    exposure=exposure,
                    preview=preview,
                )
            )

        blocked = any(step.preview.blocked for step in steps)
        return SequencePreview(
            plan=resolved_plan,
            steps=steps,
            executable=not blocked,
            blocked=blocked,
        )

    def load(self, plan: ObservationPlan) -> SequenceCommandResult:
        return self._execute("load", lambda: self._load(plan), params=plan.model_dump(mode="json"))

    def start(self) -> SequenceCommandResult:
        return self._execute("start", self._start)

    def finish_step(self) -> SequenceCommandResult:
        return self._execute("finish_step", self._finish_step)

    def stop_readout_step(self) -> SequenceCommandResult:
        return self._execute("stop_readout_step", self._stop_readout_step)

    def pause(self) -> SequenceCommandResult:
        return self._execute("pause", self._pause)

    def resume(self) -> SequenceCommandResult:
        return self._execute("resume", self._resume)

    def abort(self) -> SequenceCommandResult:
        return self._execute("abort", self._abort)

    def retry_current_step(self) -> SequenceCommandResult:
        return self._execute("retry_current_step", self._retry_current_step)

    def mark_failed(self) -> SequenceCommandResult:
        return self._execute("mark_failed", self._mark_failed)

    def _persist(self, snapshot: SequenceExecutionSnapshot) -> None:
        snapshot.last_persisted_at_utc = utc_now_iso()
        try:
            self.state_store.save(snapshot)
        except (OSError, ValueError) as exc:
            previous_state = snapshot.state.value
            snapshot.state = SequenceExecutionState.RECOVERY_REQUIRED
            snapshot.active_exposure = False
            snapshot.recovery = SequenceRecoveryInfo(
                reason="persistence_failure",
                interrupted_state=previous_state,
                interrupted_index=snapshot.current_index,
                file_issues=[str(exc)],
                retry_allowed=False,
                allowed_actions=[
                    SequenceRecoveryAction.ABORT,
                    SequenceRecoveryAction.MARK_FAILED,
                ],
            )
            snapshot.message = (
                "Recovery required: sequence state could not be saved. "
                "Detector commands are blocked until persistence is repaired."
            )
            self.runtime.sequence_persistence_error = str(exc)
            raise InvalidStateError(
                snapshot.message,
                subsystem="observation_sequence",
                details={"persistence_error": str(exc)},
            ) from exc
        self.runtime.sequence_persistence_error = None

    def _execute(
        self,
        command: str,
        action: Callable[[], SequenceExecutionSnapshot],
        *,
        params: dict | None = None,
    ) -> SequenceCommandResult:
        with self.runtime.sequence_lock:
            return self._execute_locked(command, action, params=params)

    def _execute_locked(
        self,
        command: str,
        action: Callable[[], SequenceExecutionSnapshot],
        *,
        params: dict | None = None,
    ) -> SequenceCommandResult:
        request = CommandRequest.create(
            subsystem="observation_sequence",
            action=command,
            params=params or {},
            source=CommandSource.API,
        )
        job = self.runtime.create_job(request)
        self.runtime.mark_job_running(job.job_id)

        try:
            self.runtime.require_open()
            if self.runtime.sequence_persistence_error is not None:
                raise InvalidStateError(
                    "Sequence persistence is unavailable; observation commands are blocked.",
                    subsystem="observation_sequence",
                    details={
                        "persistence_error": self.runtime.sequence_persistence_error,
                        "persistence_path": self.runtime.sequence_persistence_path,
                    },
                )
            snapshot = action()
            self._persist(snapshot)
        except ICSException as exc:
            if (self.runtime.detector is not None
                    and self.runtime.detector.state.value == "failed"
                    and self.runtime.sequence_execution is not None
                    and self.runtime.sequence_execution.state.value not in {"completed", "aborted", "failed"}):
                snapshot = self.runtime.sequence_execution
                snapshot.state = SequenceExecutionState.RECOVERY_REQUIRED
                snapshot.active_exposure = False
                snapshot.recovery = SequenceRecoveryInfo(
                    reason="acquisition_failure",
                    interrupted_state="running",
                    interrupted_index=snapshot.current_index,
                    file_issues=[str(exc)],
                    retry_allowed=False,
                    allowed_actions=[SequenceRecoveryAction.ABORT, SequenceRecoveryAction.MARK_FAILED],
                )
                snapshot.message = "Acquisition failed; review data and hardware before recovery."
                self._persist(snapshot)
            job = self.runtime.mark_job_rejected(job.job_id, exc)
            return SequenceCommandResult(
                command=command,
                ok=False,
                sequence=self.status(),
                job=job,
                error=exc,
            )

        job = self.runtime.mark_job_succeeded(
            job.job_id,
            result={"sequence": snapshot.to_status_dict()},
        )
        return SequenceCommandResult(
            command=command,
            ok=True,
            sequence=snapshot,
            job=job,
        )

    def _attach_setup_context(self, plan: ObservationPlan) -> ObservationPlan:
        if plan.setup_context is not None or self.setup_context_service is None:
            return plan
        context = self.setup_context_service.get_context()
        return plan.model_copy(update={"setup_context": context.to_persisted_dict()})

    def _step_note(self, plan: ObservationPlan, label: str | None) -> str | None:
        parts = [part for part in (plan.operator_note, label) if part]
        return " | ".join(parts) if parts else None

    def _step_setup_payloads(
        self,
        plan: ObservationPlan,
        index: int,
        reservation: SequenceFrameReservation | None = None,
    ) -> tuple[dict | None, dict | None]:
        if plan.setup_context is None:
            return None, None
        context = SessionDataContext.from_dict(plan.setup_context)
        if not plan.save_requested:
            return context.to_persisted_dict(), None
        context.next_frame_index += index
        preview = context.data_preview()
        if reservation is not None:
            preview = dict(reservation.step_data_previews[index])
        return context.to_persisted_dict(), preview

    def _reserve_frame_indices(
        self,
        plan: ObservationPlan,
    ) -> SequenceFrameReservation | None:
        if not plan.save_requested or plan.setup_context is None:
            return None
        plan_context = SessionDataContext.from_dict(plan.setup_context)
        start_index = plan_context.next_frame_index
        previews: list[dict[str, str]] = []
        for index in range(len(plan.exposures)):
            step_context = SessionDataContext.from_dict(plan.setup_context)
            step_context.next_frame_index = start_index + index
            previews.append(step_context.data_preview())

        if self.setup_context_service is not None:
            current = self.setup_context_service.get_context()
            identity_changed = (
                current.root_name != plan_context.root_name
                or current.date_prefix != plan_context.date_prefix
                or current.next_frame_index != start_index
                or current.data_directory != plan_context.data_directory
            )
            if identity_changed:
                raise InvalidStateError(
                    "Setup/data context changed after sequence preview; preview and load the plan again.",
                    subsystem="observation_sequence",
                    details={
                        "previewed_start_index": start_index,
                        "current_start_index": current.next_frame_index,
                        "previewed_root_name": plan_context.root_name,
                        "current_root_name": current.root_name,
                    },
                )
            current.next_frame_index = start_index + len(plan.exposures)
            self.setup_context_service.save_context(current)

        return SequenceFrameReservation(
            start_index=start_index,
            count=len(plan.exposures),
            end_index_exclusive=start_index + len(plan.exposures),
            step_data_previews=previews,
        )

    def _load(self, plan: ObservationPlan) -> SequenceExecutionSnapshot:
        current = self.status()
        if current is not None and current.state not in {
            SequenceExecutionState.COMPLETED,
            SequenceExecutionState.ABORTED,
            SequenceExecutionState.FAILED,
        }:
            raise InvalidStateError(
                "An observation sequence is already active.",
                subsystem="observation_sequence",
                details={"state": current.state.value},
            )

        preview = self.preview_plan(plan)
        if preview.blocked or not preview.executable:
            blocked_steps = [
                step.index for step in preview.steps if step.preview.blocked
            ]
            raise InterlockBlockedError(
                "Observation sequence load blocked by step readiness.",
                subsystem="observation_sequence",
                details={
                    "blocked_steps": blocked_steps,
                    "preview": preview.model_dump(mode="json"),
                },
            )

        reservation = self._reserve_frame_indices(preview.plan)
        snapshot = SequenceExecutionSnapshot(
            plan=preview.plan,
            frame_reservation=reservation,
            message="Sequence loaded. Start the first exposure when ready.",
        )
        self.runtime.sequence_execution = snapshot
        return snapshot

    def _require_sequence(self) -> SequenceExecutionSnapshot:
        snapshot = self.status()
        if snapshot is None:
            raise InvalidStateError(
                "No observation sequence is loaded.",
                subsystem="observation_sequence",
            )
        return snapshot

    def _require_dispatch_success(self, result, action: str) -> None:
        if result.job.status.value == "succeeded":
            return
        error = (result.payload or {}).get("error") or {}
        raise InvalidStateError(
            str(error.get("message") or f"Sequence step {action} failed."),
            subsystem="observation_sequence",
            details={"action": action, "detector_job": result.job.to_dict()},
        )

    def _start(self) -> SequenceExecutionSnapshot:
        snapshot = self._require_sequence()
        if snapshot.state not in {
            SequenceExecutionState.LOADED,
            SequenceExecutionState.RUNNING,
        }:
            raise InvalidStateError(
                "Sequence start is only valid while loaded or running between steps.",
                subsystem="observation_sequence",
                details={"state": snapshot.state.value},
            )
        if snapshot.active_exposure:
            raise InvalidStateError(
                "The current sequence exposure is already active.",
                subsystem="observation_sequence",
                details={"current_index": snapshot.current_index},
            )

        exposure = snapshot.current_exposure()
        if exposure is None:
            raise InvalidStateError(
                "The observation sequence has no remaining exposure.",
                subsystem="observation_sequence",
            )

        setup_context, data_preview = self._step_setup_payloads(
            snapshot.plan,
            snapshot.current_index,
            snapshot.frame_reservation,
        )
        previous_state = snapshot.state
        snapshot.state = SequenceExecutionState.RUNNING
        snapshot.active_step = SequenceActiveStep(
            index=snapshot.current_index,
            setup_file_stem=(data_preview or {}).get("file_stem"),
        )
        snapshot.message = "Current step reserved; detector arm is pending."
        self._persist(snapshot)

        try:
            arm_result = self.observation_service.arm(
                exp_time_s=exposure.exp_time_s,
                frame_type=exposure.frame_type.value,
                operator_note=self._step_note(snapshot.plan, exposure.label),
                save_requested=snapshot.plan.save_requested,
                setup_context_override=setup_context,
                data_preview_override=data_preview,
                sequence_owned=True
            )
            self._require_dispatch_success(arm_result, "arm")
            detector_status = self.observation_service.get_exposure_status()
            armed = detector_status.get("armed_exposure") or {}
            meta = detector_status.get("observation_meta") or {}
            snapshot.active_step.phase = "armed"
            snapshot.active_step.obs_id = armed.get("obs_id") or meta.get("obs_id")
            snapshot.active_step.exp_id = armed.get("exp_id") or meta.get("exp_id")
            self._persist(snapshot)

            start_result = self.observation_service.start(sequence_owned=True)
            if start_result.job.status.value != "succeeded":
                cleanup_result = self.observation_service.abort_discard(
                    sequence_owned=True
                )
                self._require_dispatch_success(cleanup_result, "start_cleanup_abort")
                self._require_dispatch_success(start_result, "start")
        except ICSException:
            detector_state = self.observation_service.get_exposure_status().get("state")
            if detector_state in {"armed", "exposing"}:
                cleanup_result = self.observation_service.abort_discard(
                    sequence_owned=True
                )
                self._require_dispatch_success(cleanup_result, "start_cleanup_abort")
            snapshot.state = previous_state
            snapshot.active_exposure = False
            snapshot.active_step = None
            snapshot.message = "Sequence step did not start; retry Start when ready."
            self._persist(snapshot)
            raise

        snapshot.state = SequenceExecutionState.RUNNING
        snapshot.active_exposure = True
        snapshot.active_step.phase = "exposing"
        snapshot.active_step.started_at_utc = utc_now_iso()
        snapshot.updated_at_utc = utc_now_iso()
        snapshot.message = (
            f"Exposure {snapshot.current_index + 1}/{snapshot.total_steps} is running."
        )
        self.runtime.schedule_readout(
            duration_s=float(exposure.exp_time_s),
            callback=self.finish_step,
            description=f"sequence-step-{snapshot.current_index + 1}",
        )
        return snapshot

    def _finish_step(self) -> SequenceExecutionSnapshot:
        self._require_active_step("finish")
        result = self.observation_service.finish(sequence_owned=True)
        self._require_dispatch_success(result, "finish")
        return self._complete_active_step(SequenceStepState.COMPLETED)

    def _stop_readout_step(self) -> SequenceExecutionSnapshot:
        self._require_active_step("stop_readout")
        result = self.observation_service.stop_readout(sequence_owned=True)
        self._require_dispatch_success(result, "stop_readout")
        return self._complete_active_step(
            SequenceStepState.COMPLETED,
            message="Exposure stopped early and read out.",
        )

    def _require_active_step(self, action: str) -> SequenceExecutionSnapshot:
        snapshot = self._require_sequence()
        if not snapshot.active_exposure:
            raise InvalidStateError(
                f"No active sequence exposure is available to {action}.",
                subsystem="observation_sequence",
                details={
                    "state": snapshot.state.value,
                    "current_index": snapshot.current_index,
                },
            )
        return snapshot

    def _complete_active_step(
        self,
        state: SequenceStepState,
        *,
        message: str | None = None,
    ) -> SequenceExecutionSnapshot:
        snapshot = self._require_sequence()
        if not snapshot.active_exposure:
            raise InvalidStateError(
                "No active sequence exposure is available to complete.",
                subsystem="observation_sequence",
            )

        exposure = snapshot.current_exposure()
        detector_status = self.observation_service.get_exposure_status()
        snapshot.step_results.append(
            SequenceStepResult(
                index=snapshot.current_index,
                exposure=exposure,
                state=state,
                exposure_record=detector_status.get("latest_exposure_record"),
                message=message,
            )
        )
        snapshot.current_index += 1
        snapshot.active_exposure = False
        snapshot.active_step = None
        snapshot.updated_at_utc = utc_now_iso()

        if snapshot.current_index >= snapshot.total_steps:
            snapshot.state = SequenceExecutionState.COMPLETED
            snapshot.message = "Observation sequence completed."
        elif snapshot.state == SequenceExecutionState.PAUSE_REQUESTED:
            snapshot.state = SequenceExecutionState.PAUSED
            snapshot.message = "Sequence paused between exposures."
        else:
            snapshot.state = SequenceExecutionState.RUNNING
            snapshot.message = "Step completed. Start the next exposure when ready."
        return snapshot

    def _pause(self) -> SequenceExecutionSnapshot:
        snapshot = self._require_sequence()
        if snapshot.state not in {
            SequenceExecutionState.LOADED,
            SequenceExecutionState.RUNNING,
        }:
            raise InvalidStateError(
                "Sequence pause is only valid while loaded or running.",
                subsystem="observation_sequence",
                details={"state": snapshot.state.value},
            )
        snapshot.state = (
            SequenceExecutionState.PAUSE_REQUESTED
            if snapshot.active_exposure
            else SequenceExecutionState.PAUSED
        )
        snapshot.updated_at_utc = utc_now_iso()
        snapshot.message = (
            "Pause requested; it will take effect after the active exposure."
            if snapshot.active_exposure
            else "Sequence paused between exposures."
        )
        return snapshot

    def _resume(self) -> SequenceExecutionSnapshot:
        snapshot = self._require_sequence()
        if snapshot.state != SequenceExecutionState.PAUSED:
            raise InvalidStateError(
                "Sequence resume is only valid while paused.",
                subsystem="observation_sequence",
                details={"state": snapshot.state.value},
            )
        snapshot.state = SequenceExecutionState.RUNNING
        snapshot.updated_at_utc = utc_now_iso()
        snapshot.message = "Sequence resumed. Start the next exposure when ready."
        return snapshot

    def _abort(self) -> SequenceExecutionSnapshot:
        snapshot = self._require_sequence()
        if snapshot.state in {
            SequenceExecutionState.COMPLETED,
            SequenceExecutionState.ABORTED,
        }:
            raise InvalidStateError(
                "Sequence abort is not valid after a terminal state.",
                subsystem="observation_sequence",
                details={"state": snapshot.state.value},
            )

        # Stop any pending automatic readout: the step is being abandoned.
        self.runtime.cancel_readout()

        if snapshot.active_exposure:
            result = self.observation_service.abort_discard(sequence_owned=True)
            self._require_dispatch_success(result, "abort_discard")
            exposure = snapshot.current_exposure()
            detector_status = self.observation_service.get_exposure_status()
            snapshot.step_results.append(
                SequenceStepResult(
                    index=snapshot.current_index,
                    exposure=exposure,
                    state=SequenceStepState.DISCARDED,
                    exposure_record=detector_status.get("latest_exposure_record"),
                    message="Active exposure aborted and discarded.",
                )
            )
            snapshot.active_exposure = False

        snapshot.state = SequenceExecutionState.ABORTED
        snapshot.active_step = None
        snapshot.updated_at_utc = utc_now_iso()
        snapshot.message = "Observation sequence aborted. Pending steps were not run."
        return snapshot

    def _retry_current_step(self) -> SequenceExecutionSnapshot:
        snapshot = self._require_sequence()
        recovery = snapshot.recovery
        if snapshot.state != SequenceExecutionState.RECOVERY_REQUIRED or recovery is None:
            raise InvalidStateError(
                "Retry Current Step is only valid while sequence recovery is required.",
                subsystem="observation_sequence",
                details={"state": snapshot.state.value},
            )
        if not recovery.retry_allowed:
            raise InvalidStateError(
                "Retry is blocked because a FITS file may already exist or the durable record is inconsistent.",
                subsystem="observation_sequence",
                details={
                    "reason": recovery.reason,
                    "detected_files": recovery.detected_files,
                    "file_issues": recovery.file_issues,
                },
            )
        snapshot.state = (
            SequenceExecutionState.LOADED
            if snapshot.current_index == 0
            else SequenceExecutionState.RUNNING
        )
        snapshot.active_exposure = False
        snapshot.active_step = None
        snapshot.recovery = None
        snapshot.updated_at_utc = utc_now_iso()
        snapshot.message = (
            "Recovery acknowledged. The current step is ready for an explicit Start."
        )
        return snapshot

    def _mark_failed(self) -> SequenceExecutionSnapshot:
        snapshot = self._require_sequence()
        if snapshot.state != SequenceExecutionState.RECOVERY_REQUIRED:
            raise InvalidStateError(
                "Mark Failed is only valid while sequence recovery is required.",
                subsystem="observation_sequence",
                details={"state": snapshot.state.value},
            )
        snapshot.state = SequenceExecutionState.FAILED
        snapshot.active_exposure = False
        snapshot.active_step = None
        snapshot.updated_at_utc = utc_now_iso()
        snapshot.message = (
            "Sequence marked failed by the operator after recovery review."
        )
        return snapshot
