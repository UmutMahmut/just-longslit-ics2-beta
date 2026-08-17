from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from justls.ics.domain.observatory.context import ObservatoryContext
from justls.ics.kernel.runtime import Runtime
from justls.ics.kernel.states import ControlState, ExposureState


STALE_THRESHOLD_S = 5.0


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class HealthService:
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime

    def get_state_dto(self) -> dict:
        slit_snapshot = self.runtime.slit.get_snapshot() if self.runtime.slit is not None else None
        lamp_snapshot = self.runtime.lamps.get_snapshot() if self.runtime.lamps is not None else None

        return {
            "slit_width_um": slit_snapshot.width_um if slit_snapshot is not None else None,
            "slit_angle_deg": slit_snapshot.angle_deg if slit_snapshot is not None else None,
            "lamp_on": lamp_snapshot.lamp_enabled if lamp_snapshot is not None else False,
            "temperature_c": None,
        }

    def get_capabilities(self) -> dict:
        return self.runtime.get_capabilities_dict()

    def get_calibration_status(self) -> dict | None:
        if self.runtime.lamps is None:
            return None
        return self.runtime.lamps.get_snapshot().to_dict()

    def get_observation_status(self) -> dict | None:
        if self.runtime.detector is None:
            return None
        return self.runtime.detector.get_snapshot().to_dict()

    def get_observatory_context(self) -> dict:
        return ObservatoryContext.default_unavailable(
            run_mode=self.runtime.config.run_mode.value,
        ).model_dump(mode="json")

    def get_operational_status(self) -> dict[str, Any]:
        """
        Return an observer-facing operational summary for GUI state gating.

        Phase 2.6 deliberately keeps this as a derived status block. It does not
        add a new state machine. Instead, it translates the existing subsystem,
        exposure, and latest-job state into stable flags that the UI can render
        as OK / busy / warning / fault / interlock indicators.
        """
        snapshot = self.runtime.get_snapshot()
        subsystems = snapshot.iter_subsystems()
        latest_job = self.runtime.latest_job_dict()

        busy_subsystems = [
            subsystem.name
            for subsystem in subsystems
            if subsystem.state == ControlState.BUSY
        ]
        fault_subsystems = [
            subsystem.name
            for subsystem in subsystems
            if subsystem.state == ControlState.FAULT
        ]
        disconnected_subsystems = [
            subsystem.name
            for subsystem in subsystems
            if not subsystem.connected
        ]

        exposure_state = snapshot.exposure_state
        exposure_busy = exposure_state in {
            ExposureState.ARMED,
            ExposureState.EXPOSING,
            ExposureState.READING_OUT,
        }

        latest_error_code = self._latest_job_error_code(latest_job)
        interlock_blocked = latest_error_code == "interlock_blocked"

        flags = {
            "busy": bool(busy_subsystems) or exposure_busy,
            "fault": bool(fault_subsystems),
            "disconnected": bool(disconnected_subsystems),
            "interlock_blocked": interlock_blocked,
            "armed": exposure_state == ExposureState.ARMED,
            "exposing": exposure_state == ExposureState.EXPOSING,
            "reading_out": exposure_state == ExposureState.READING_OUT,
        }

        level = self._operational_level(flags)

        return {
            "level": level,
            "summary": self._operational_summary(
                level,
                flags,
                busy_subsystems=busy_subsystems,
                fault_subsystems=fault_subsystems,
                disconnected_subsystems=disconnected_subsystems,
            ),
            "control_state": snapshot.overall_state.value,
            "exposure_state": exposure_state.value,
            "flags": flags,
            "busy_subsystems": busy_subsystems,
            "fault_subsystems": fault_subsystems,
            "disconnected_subsystems": disconnected_subsystems,
            "latest_job": latest_job,
            "latest_error_code": latest_error_code,
            "stale_threshold_s": STALE_THRESHOLD_S,
            "refresh_hint": "Refresh /api/v1/status/full to reconcile dashboard state.",
            "ui_hints": {
                "show_request_id": True,
                "show_refresh_action": True,
                "show_engineering_escape_hatch": bool(fault_subsystems) or interlock_blocked,
            },
        }

    def _latest_job_error_code(self, latest_job: dict[str, Any] | None) -> str | None:
        if latest_job is None:
            return None

        error = latest_job.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            return str(code) if code else None

        return None

    def _operational_level(self, flags: dict[str, bool]) -> str:
        if flags["fault"]:
            return "error"
        if flags["disconnected"] or flags["interlock_blocked"]:
            return "warning"
        if flags["busy"]:
            return "busy"
        return "ok"

    def _operational_summary(
        self,
        level: str,
        flags: dict[str, bool],
        *,
        busy_subsystems: list[str],
        fault_subsystems: list[str],
        disconnected_subsystems: list[str],
    ) -> str:
        if level == "error":
            return f"Fault in: {', '.join(fault_subsystems)}."
        if flags["interlock_blocked"]:
            return "Last command was blocked by an interlock."
        if level == "warning":
            return f"Disconnected subsystem(s): {', '.join(disconnected_subsystems)}."
        if flags["reading_out"]:
            return "Detector is reading out; stop/abort actions are not available."
        if flags["exposing"]:
            return "Exposure is in progress."
        if flags["armed"]:
            return "Observation is armed and waiting to start."
        if level == "busy":
            return f"Busy subsystem(s): {', '.join(busy_subsystems)}."
        return "System is ready for observer operations."

    def get_status_full(self) -> dict:
        return {
            "state": self.get_state_dto(),
            "capabilities": self.get_capabilities(),
            "calibration": self.get_calibration_status(),
            "observation": self.get_observation_status(),
            "observation_sequence": self.runtime.sequence_execution,
            "observatory": self.get_observatory_context(),
            "operational_status": self.get_operational_status(),
            "detector_config": self.runtime.get_detector_config_dict(),
            "hal": self.runtime.config.run_mode.value,
            "run_mode": self.runtime.config.run_mode.value,
            "timestamp_utc": utc_now_iso(),
        }

    def get_health(self) -> dict:
        return {
            "ok": True,
            "service": "just-longslit-ics-2.0",
            "runtime": self.runtime.status_dict(),
        }

    def get_status(self) -> dict:
        return self.get_status_full()
