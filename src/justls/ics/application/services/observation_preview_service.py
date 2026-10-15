from __future__ import annotations

from justls.ics.application.services.setup_context_service import SetupContextService
from justls.ics.domain.observation.models import (
    ObservationFrameType,
    ObservationPreviewResult,
    ObservationRequest,
    ReadinessItem,
    ReadinessSnapshot,
    ReadinessState,
    ValidationIssue,
    ValidationSeverity,
)
from justls.ics.kernel.runtime import Runtime
from justls.ics.kernel.states import ControlState, ExposureState


_ARMABLE_EXPOSURE_STATES = {
    ExposureState.READY_TO_ARM,
    ExposureState.COMPLETED,
    ExposureState.ABORTED,
    ExposureState.DISCARDED,
    ExposureState.FAILED,
}

_BUSY_EXPOSURE_STATES = {
    ExposureState.ARMED,
    ExposureState.EXPOSING,
    ExposureState.READING_OUT,
}


class ObservationPreviewService:
    def __init__(
        self,
        runtime: Runtime,
        setup_context_service: SetupContextService | None = None,
    ) -> None:
        self.runtime = runtime
        self.setup_context_service = setup_context_service

    def preview_request(
        self,
        request: ObservationRequest,
    ) -> ObservationPreviewResult:
        request = self._attach_setup_context_if_needed(request)
        readiness = self._build_readiness_snapshot(request)
        validation_issues = self._build_validation_issues(request, readiness)

        return ObservationPreviewResult.from_request(
            request,
            readiness=readiness,
            validation_issues=validation_issues,
        )

    def _attach_setup_context_if_needed(
        self,
        request: ObservationRequest,
    ) -> ObservationRequest:
        if request.setup_context is not None:
            return request

        if self.setup_context_service is None:
            return request

        context = self.setup_context_service.get_context()
        return request.model_copy(
            update={"setup_context": context.to_persisted_dict()}
        )

    def _build_readiness_snapshot(
        self,
        request: ObservationRequest,
    ) -> ReadinessSnapshot:
        return ReadinessSnapshot(
            detector=self._detector_readiness(),
            calibration=self._calibration_readiness(request),
            slit=self._subsystem_control_readiness(
                "slit",
                unavailable_message="Slit subsystem is not available.",
            ),
        )

    def _subsystem_control_readiness(
        self,
        subsystem: str,
        *,
        unavailable_message: str,
    ) -> ReadinessItem:
        try:
            state = self.runtime.get_subsystem_state(subsystem)
        except KeyError:
            return ReadinessItem(
                state=ReadinessState.UNAVAILABLE,
                message=unavailable_message,
            )

        if not state.connected:
            return ReadinessItem(
                state=ReadinessState.BLOCKED,
                message=f"{subsystem} subsystem is not connected.",
                updated_at_utc=state.updated_at.isoformat(),
            )

        if state.state == ControlState.FAULT:
            return ReadinessItem(
                state=ReadinessState.BLOCKED,
                message=f"{subsystem} subsystem is faulted: {state.message}",
                updated_at_utc=state.updated_at.isoformat(),
            )

        if state.state == ControlState.BUSY:
            return ReadinessItem(
                state=ReadinessState.BLOCKED,
                message=f"{subsystem} subsystem is busy: {state.message}",
                updated_at_utc=state.updated_at.isoformat(),
            )

        if state.state == ControlState.INITIALIZING:
            return ReadinessItem(
                state=ReadinessState.UNKNOWN,
                message=f"{subsystem} subsystem is still initializing.",
                updated_at_utc=state.updated_at.isoformat(),
            )

        return ReadinessItem(
            state=ReadinessState.READY,
            message=f"{subsystem} subsystem is ready.",
            updated_at_utc=state.updated_at.isoformat(),
        )

    def _detector_readiness(self) -> ReadinessItem:
        if self.runtime.detector is None:
            return ReadinessItem(
                state=ReadinessState.BLOCKED,
                message="Detector subsystem is not available.",
            )

        control_readiness = self._subsystem_control_readiness(
            "detector",
            unavailable_message="Detector subsystem is not available.",
        )
        if control_readiness.is_blocking():
            return control_readiness

        exposure_state = self.runtime.detector.get_snapshot().state

        if exposure_state in _ARMABLE_EXPOSURE_STATES:
            return ReadinessItem(
                state=ReadinessState.READY,
                message=(
                    "Detector exposure state "
                    f"{exposure_state.value!r} is compatible with arm."
                ),
            )

        if exposure_state in _BUSY_EXPOSURE_STATES:
            return ReadinessItem(
                state=ReadinessState.BLOCKED,
                message=(
                    "Detector is already committed to an exposure: "
                    f"{exposure_state.value}."
                ),
            )

        return ReadinessItem(
            state=ReadinessState.UNKNOWN,
            message=f"Detector exposure state is {exposure_state.value}.",
        )

    def _calibration_readiness(
        self,
        request: ObservationRequest,
    ) -> ReadinessItem:
        spec = request.single_exposure_spec()
        if spec is None:
            return ReadinessItem(
                state=ReadinessState.UNKNOWN,
                message="Calibration readiness requires a single ExposureSpec.",
            )

        if self.runtime.lamps is None:
            if spec.frame_type in {
                ObservationFrameType.FLAT,
                ObservationFrameType.ARC,
            }:
                return ReadinessItem(
                    state=ReadinessState.BLOCKED,
                    message=(
                        "Calibration subsystem is required for flat/arc "
                        "frames but is not available."
                    ),
                )
            return ReadinessItem(
                state=ReadinessState.UNAVAILABLE,
                message="Calibration subsystem is not available.",
            )

        control_readiness = self._subsystem_control_readiness(
            "lamps",
            unavailable_message="Calibration subsystem is not available.",
        )
        if control_readiness.is_blocking():
            return control_readiness

        snapshot = self.runtime.lamps.get_snapshot()
        mode = snapshot.mode.value
        active_lamp = (
            snapshot.active_lamp.value
            if snapshot.active_lamp is not None
            else None
        )
        lamp_enabled = snapshot.lamp_enabled
        mirror_inserted = snapshot.mirror_inserted

        if spec.frame_type in {
            ObservationFrameType.SCIENCE,
            ObservationFrameType.BIAS,
            ObservationFrameType.DARK,
        }:
            if mode == "science" and not lamp_enabled and not mirror_inserted:
                label = spec.frame_type.value.capitalize()
                return ReadinessItem(
                    state=ReadinessState.READY,
                    message=f"Calibration path is ready for {label} frame.",
                )
            label = spec.frame_type.value.capitalize()
            return ReadinessItem(
                state=ReadinessState.BLOCKED,
                message=(
                    f"{label} frame requires science calibration mode with "
                    "lamp disabled and mirror removed."
                ),
            )

        if spec.frame_type == ObservationFrameType.FLAT:
            if mode == "calibration" and active_lamp == "flat" and lamp_enabled:
                return ReadinessItem(
                    state=ReadinessState.READY,
                    message="Flat lamp is enabled for flat frame preview.",
                )
            return ReadinessItem(
                state=ReadinessState.BLOCKED,
                message=(
                    "Flat frame requires calibration mode with flat lamp enabled."
                ),
            )

        if spec.frame_type == ObservationFrameType.ARC:
            if (
                mode == "calibration"
                and active_lamp in {"arc_hgar", "arc_ne"}
                and lamp_enabled
            ):
                return ReadinessItem(
                    state=ReadinessState.READY,
                    message="Arc lamp is enabled for arc frame preview.",
                )
            return ReadinessItem(
                state=ReadinessState.BLOCKED,
                message=(
                    "Arc frame requires calibration mode with an arc lamp enabled."
                ),
            )

        return ReadinessItem(
            state=ReadinessState.READY,
            message="Test frame does not enforce calibration mode/lamp readiness yet.",
        )

    def _build_validation_issues(
        self,
        request: ObservationRequest,
        readiness: ReadinessSnapshot,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        spec = request.single_exposure_spec()
        if spec is None:
            return issues

        if readiness.calibration.is_blocking():
            issues.append(
                ValidationIssue(
                    code=f"{spec.frame_type.value}_calibration_not_ready",
                    severity=ValidationSeverity.ERROR,
                    field="exposures.0.frame_type",
                    message=readiness.calibration.message
                    or "Calibration readiness blocks this frame type.",
                )
            )

        return issues
