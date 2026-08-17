from __future__ import annotations

from typing import Any

from justls.ics.application.dispatcher import DispatchResult
from justls.ics.application.services.observation_preview_service import (
    ObservationPreviewService,
)
from justls.ics.application.services.setup_context_service import SetupContextService
from justls.ics.domain.observation.models import (
    ExposureSpec,
    ObservationCommandError,
    ObservationCommandFeedback,
    ObservationCommandName,
    ObservationPreviewResult,
    ObservationRequest,
)
from justls.ics.kernel.errors import ICSException, InterlockBlockedError
from justls.ics.kernel.jobs import CommandRequest
from justls.ics.kernel.runtime import Runtime
from justls.ics.kernel.states import CommandSource


class ObservationService:
    def __init__(
        self,
        runtime: Runtime,
        dispatcher,
        setup_context_service: SetupContextService | None = None,
        preview_service: ObservationPreviewService | None = None,
    ) -> None:
        self.runtime = runtime
        self.dispatcher = dispatcher
        self.setup_context_service = setup_context_service
        self.preview_service = preview_service or ObservationPreviewService(
            runtime,
            setup_context_service,
        )

    def get_exposure_status(self) -> dict:
        if self.runtime.detector is None:
            return {
                "state": self.runtime.get_snapshot().exposure_state.value,
                "armed_exposure": None,
                "last_exposure": None,
                "observation_meta": None,
            }
        return self.runtime.detector.get_snapshot().to_dict()

    def _enforce_sequence_ownership(self, *, sequence_owned: bool) -> None:
        if sequence_owned:
            return
        sequence = self.runtime.sequence_execution
        if sequence is None or sequence.state.value in {
            "completed",
            "aborted",
            "failed",
        }:
            return
        raise InterlockBlockedError(
            "Direct exposure commands are blocked while an observation sequence is active.",
            subsystem="detector",
            details={
                "sequence_plan_id": sequence.plan.plan_id,
                "sequence_state": sequence.state.value,
                "use_sequence_commands": True,
            },
        )

    def _setup_context_payloads(self) -> tuple[dict | None, dict | None]:
        if self.setup_context_service is None:
            return None, None
        context = self.setup_context_service.get_context()
        return context.to_persisted_dict(), context.data_preview()

    def _arm_preview_request(
        self,
        *,
        exp_time_s: float,
        frame_type: str,
        operator_note: str | None,
        setup_context: dict | None,
    ) -> ObservationRequest:
        return ObservationRequest(
            exposures=[
                ExposureSpec(
                    frame_type=frame_type,
                    exp_time_s=exp_time_s,
                )
            ],
            operator_note=operator_note,
            setup_context=setup_context,
        )

    def _arm_gate_message(self, preview: ObservationPreviewResult) -> str:
        issue_codes = [issue.code for issue in preview.validation_issues]
        blocked_components = preview.readiness.blocked_components()

        if issue_codes and blocked_components:
            return (
                "Observation arm blocked by preview readiness gate: "
                f"issues={issue_codes}, blocked_components={blocked_components}."
            )
        if issue_codes:
            return (
                "Observation arm blocked by preview validation issues: "
                f"{issue_codes}."
            )
        if blocked_components:
            return (
                "Observation arm blocked by preview readiness components: "
                f"{blocked_components}."
            )
        return "Observation arm blocked by preview readiness gate."

    def _enforce_arm_preview_gate(
        self,
        *,
        exp_time_s: float,
        frame_type: str,
        operator_note: str | None,
        setup_context: dict | None,
    ) -> ObservationPreviewResult:
        request = self._arm_preview_request(
            exp_time_s=exp_time_s,
            frame_type=frame_type,
            operator_note=operator_note,
            setup_context=setup_context,
        )
        preview = self.preview_service.preview_request(request)

        if preview.blocked or not preview.single_exposure_compatible:
            raise InterlockBlockedError(
                self._arm_gate_message(preview),
                subsystem="detector",
                details={
                    "preview": preview.model_dump(mode="json"),
                    "blocked_components": preview.readiness.blocked_components(),
                    "validation_issue_codes": [
                        issue.code for issue in preview.validation_issues
                    ],
                },
            )

        return preview

    def _job_payload(self, result: DispatchResult) -> dict[str, Any]:
        job = result.job

        if hasattr(job, "to_dict"):
            payload = job.to_dict()
            if isinstance(payload, dict):
                return payload

        if hasattr(job, "model_dump"):
            payload = job.model_dump(mode="json")
            if isinstance(payload, dict):
                return payload

        status = getattr(job, "status", None)
        return {
            "job_id": getattr(job, "job_id", None),
            "subsystem": getattr(job, "subsystem", None),
            "action": getattr(job, "action", None),
            "status": getattr(status, "value", status),
        }

    def _observation_state_from_payload(self, payload: dict[str, Any]) -> str | None:
        state = payload.get("state") or payload.get("observation_state")
        return str(state) if state is not None else None

    def _dispatch_error_from_payload(
        self,
        payload: dict[str, Any],
        *,
        latest_job: dict[str, Any],
    ) -> ObservationCommandError:
        raw_error = payload.get("error")
        default_message = "Observation command dispatch failed."

        if isinstance(raw_error, dict):
            code = raw_error.get("code") or "invalid_state"
            message = raw_error.get("message") or default_message
            error_details = raw_error.get("details")
            details: dict[str, Any] = {
                "job": latest_job,
                "payload": payload,
            }
            if isinstance(error_details, dict):
                details["error_details"] = error_details

            return ObservationCommandError(
                code=str(code),
                message=str(message),
                details=details,
            )

        if isinstance(raw_error, str) and raw_error:
            return ObservationCommandError(
                code=str(payload.get("code") or payload.get("error_code") or "invalid_state"),
                message=raw_error,
                details={
                    "job": latest_job,
                    "payload": payload,
                },
            )

        return ObservationCommandError(
            code=str(payload.get("code") or payload.get("error_code") or "invalid_state"),
            message=str(payload.get("message") or default_message),
            details={
                "job": latest_job,
                "payload": payload,
            },
        )

    def feedback_from_dispatch_result(
        self,
        command: ObservationCommandName | str,
        result: DispatchResult,
        *,
        request_id: str | None = None,
    ) -> ObservationCommandFeedback:
        payload = result.payload if isinstance(result.payload, dict) else {}
        latest_job = self._job_payload(result)

        if result.job.status.value == "failed":
            error = self._dispatch_error_from_payload(payload, latest_job=latest_job)
            return ObservationCommandFeedback.failed(
                command,
                message=error.message,
                request_id=request_id,
                error=error,
                details={
                    "payload": payload,
                },
            )

        return ObservationCommandFeedback.succeeded(
            command,
            message="Observation command accepted.",
            request_id=request_id,
            observation_state=self._observation_state_from_payload(payload),
            latest_job=latest_job,
            details={
                "payload": payload,
            },
        )

    def feedback_from_exception(
        self,
        command: ObservationCommandName | str,
        exc: ICSException,
        *,
        request_id: str | None = None,
    ) -> ObservationCommandFeedback:
        details = exc.info.details or {}
        preview_payload = details.get("preview")
        preview: ObservationPreviewResult | None = None

        if isinstance(preview_payload, dict):
            preview = ObservationPreviewResult.model_validate(preview_payload)

        error = ObservationCommandError(
            code=exc.code.value,
            message=exc.info.message,
            details=details,
        )

        if exc.code.value == "interlock_blocked":
            return ObservationCommandFeedback.blocked_by_readiness_gate(
                command,
                message=exc.info.message,
                request_id=request_id,
                preview=preview,
                blocked_components=details.get("blocked_components"),
                error=error,
                details=details,
            )

        return ObservationCommandFeedback.failed(
            command,
            message=exc.info.message,
            request_id=request_id,
            error=error,
            details=details,
        )

    def arm(
        self,
        *,
        exp_time_s: float,
        frame_type: str = "science",
        operator_note: str | None = None,
        setup_context_override: dict | None = None,
        data_preview_override: dict | None = None,
        sequence_owned: bool = False,
    ) -> DispatchResult:
        self._enforce_sequence_ownership(sequence_owned=sequence_owned)
        setup_context, data_preview = self._setup_context_payloads()
        if setup_context_override is not None:
            setup_context = setup_context_override
        if data_preview_override is not None:
            data_preview = data_preview_override

        self._enforce_arm_preview_gate(
            exp_time_s=exp_time_s,
            frame_type=frame_type,
            operator_note=operator_note,
            setup_context=setup_context,
        )

        params = {
            "exp_time_s": exp_time_s,
            "frame_type": frame_type,
            "operator_note": operator_note,
        }
        if setup_context is not None:
            params["setup_context"] = setup_context
        if data_preview is not None:
            params["data_preview"] = data_preview

        request = CommandRequest.create(
            subsystem="detector",
            action="arm_exposure",
            params=params,
            source=CommandSource.API,
        )
        return self.dispatcher.dispatch(request)

    def start(self, *, sequence_owned: bool = False) -> DispatchResult:
        self._enforce_sequence_ownership(sequence_owned=sequence_owned)
        request = CommandRequest.create(
            subsystem="detector",
            action="start_exposure",
            params={},
            source=CommandSource.API,
        )
        return self.dispatcher.dispatch(request)

    def finish(self, *, sequence_owned: bool = False) -> DispatchResult:
        self._enforce_sequence_ownership(sequence_owned=sequence_owned)
        request = CommandRequest.create(
            subsystem="detector",
            action="finish_exposure",
            params={},
            source=CommandSource.API,
        )
        return self.dispatcher.dispatch(request)

    def stop_readout(self, *, sequence_owned: bool = False) -> DispatchResult:
        self._enforce_sequence_ownership(sequence_owned=sequence_owned)
        request = CommandRequest.create(
            subsystem="detector",
            action="stop_readout",
            params={},
            source=CommandSource.API,
        )
        return self.dispatcher.dispatch(request)

    def abort_discard(self, *, sequence_owned: bool = False) -> DispatchResult:
        self._enforce_sequence_ownership(sequence_owned=sequence_owned)
        request = CommandRequest.create(
            subsystem="detector",
            action="abort_discard",
            params={},
            source=CommandSource.API,
        )
        return self.dispatcher.dispatch(request)
