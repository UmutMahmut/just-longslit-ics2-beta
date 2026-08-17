from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from justls.ics.application.services.observation_preview_service import (
    ObservationPreviewService,
)
from justls.ics.application.services.observation_service import ObservationService
from justls.ics.application.services.setup_context_service import SetupContextService
from justls.ics.domain.observation.models import ObservationRequest, utc_now_iso
from justls.ics.domain.observation.sequence import (
    ObservationPlan,
    SequenceExecutionSnapshot,
    SequenceExecutionState,
    SequencePreview,
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

    The service deliberately does not create a timer thread or bypass the
    detector command lifecycle. Each sequence step is armed, started, and
    completed through ObservationService, so the existing readiness gate and
    ExposureRecord contract remain authoritative.
    """

    def __init__(
        self,
        runtime: Runtime,
        observation_service: ObservationService,
        preview_service: ObservationPreviewService,
        setup_context_service: SetupContextService | None = None,
    ) -> None:
        self.runtime = runtime
        self.observation_service = observation_service
        self.preview_service = preview_service
        self.setup_context_service = setup_context_service

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

    def _execute(
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
            snapshot = action()
        except ICSException as exc:
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
    ) -> tuple[dict | None, dict | None]:
        if plan.setup_context is None:
            return None, None
        context = SessionDataContext.from_dict(plan.setup_context)
        context.next_frame_index += index
        return context.to_persisted_dict(), context.data_preview()

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

        snapshot = SequenceExecutionSnapshot(
            plan=preview.plan,
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
        )
        arm_result = self.observation_service.arm(
            exp_time_s=exposure.exp_time_s,
            frame_type=exposure.frame_type.value,
            operator_note=self._step_note(snapshot.plan, exposure.label),
            setup_context_override=setup_context,
            data_preview_override=data_preview,
            sequence_owned=True,
        )
        self._require_dispatch_success(arm_result, "arm")
        start_result = self.observation_service.start(sequence_owned=True)
        if start_result.job.status.value != "succeeded":
            cleanup_result = self.observation_service.abort_discard(
                sequence_owned=True
            )
            self._require_dispatch_success(cleanup_result, "start_cleanup_abort")
            self._require_dispatch_success(start_result, "start")

        snapshot.state = SequenceExecutionState.RUNNING
        snapshot.active_exposure = True
        snapshot.updated_at_utc = utc_now_iso()
        snapshot.message = (
            f"Exposure {snapshot.current_index + 1}/{snapshot.total_steps} is running."
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
        snapshot.updated_at_utc = utc_now_iso()
        snapshot.message = "Observation sequence aborted. Pending steps were not run."
        return snapshot
