from __future__ import annotations

from typing import Any

from justls.ics.application.usecases.preset_plan import PresetPlan
from justls.ics.domain.detector.config import DetectorConfig
from justls.ics.kernel.errors import ErrorCode, ICSException, InvalidStateError
from justls.ics.kernel.jobs import CommandRequest
from justls.ics.kernel.runtime import Runtime
from justls.ics.kernel.states import CommandSource, ControlState


class PresetConfirmationRequiredError(ICSException):
    def __init__(self, plan: PresetPlan) -> None:
        super().__init__(
            code=ErrorCode.CONFIRMATION_REQUIRED,
            message=f"Preset {plan.name} requires explicit confirmation before apply.",
            subsystem="presets",
            retriable=False,
            details={
                "preset": plan.name,
                "category": plan.category,
                "risk_level": plan.risk_level,
                "requires_confirmation": plan.requires_confirmation,
            },
        )


class ManagementService:
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime

    def _assert_mutation_allowed(self, action_name: str) -> None:
        if self.runtime.detector is None:
            return

        state = self.runtime.detector.get_snapshot().state.value
        if state in {"armed", "exposing"}:
            raise InvalidStateError(
                f"{action_name} is blocked while observation state is {state}",
                subsystem="detector",
                details={
                    "observation_state": state,
                    "blocked_action": action_name,
                },
            )

    def _assert_preset_confirmation_allowed(self, plan: PresetPlan, confirmed: bool) -> None:
        if plan.requires_confirmation and not confirmed:
            raise PresetConfirmationRequiredError(plan)

    def _mutation_block_reason(self, action_name: str) -> str | None:
        if self.runtime.detector is None:
            return None

        state = self.runtime.detector.get_snapshot().state.value
        if state in {"armed", "exposing"}:
            return f"{action_name} is blocked while observation state is {state}"
        return None

    def _diff_values(self, path: str, current: Any, target: Any) -> list[dict[str, Any]]:
        if isinstance(current, dict) and isinstance(target, dict):
            changes: list[dict[str, Any]] = []
            for key in sorted(set(current) | set(target)):
                child_path = f"{path}.{key}" if path else str(key)
                changes.extend(
                    self._diff_values(child_path, current.get(key), target.get(key))
                )
            return changes

        if current != target:
            return [
                {
                    "path": path,
                    "current": current,
                    "target": target,
                }
            ]
        return []

    def _target_calibration_preview(self, plan: PresetPlan) -> dict[str, Any] | None:
        if plan.calibration is None:
            return None

        if plan.calibration.mode == "science":
            return {
                "mode": "science",
                "active_lamp": None,
                "lamp_enabled": False,
                "mirror_inserted": False,
            }

        if plan.calibration.mode == "calibration":
            return {
                "mode": "calibration",
                "active_lamp": plan.calibration.lamp,
                "lamp_enabled": plan.calibration.enabled,
                "mirror_inserted": True,
            }

        return {
            "mode": plan.calibration.mode,
            "active_lamp": plan.calibration.lamp,
            "lamp_enabled": plan.calibration.enabled,
            "mirror_inserted": None,
        }

    def _target_slit_preview(self, plan: PresetPlan) -> dict[str, Any] | None:
        if plan.slit is None:
            return None
        return plan.slit.to_dict()

    def _current_slit_preview(self) -> dict[str, Any] | None:
        if self.runtime.slit is None:
            return None
        return self.runtime.slit.get_snapshot().to_dict()

    def _preset_apply_job_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": "preset_apply",
            "preset": payload["applied_preset"],
            "category": payload["category"],
            "risk_level": payload["risk_level"],
            "requires_confirmation": payload["requires_confirmation"],
            "changed_fields_count": len(payload["changed_fields"]),
            "calibration_applied": payload["calibration_applied"],
            "slit_applied": payload["slit_applied"],
            "skipped_fields": payload["skipped_fields"],
            "blocked_fields": payload["blocked_fields"],
        }

    def set_connected(self, subsystem: str, connected: bool, *, message: str = "") -> dict:
        state = self.runtime.set_subsystem_connected(subsystem, connected, message=message)
        return state.to_dict()

    def set_state(self, subsystem: str, state: ControlState, *, message: str = "") -> dict:
        updated = self.runtime.set_subsystem_state(subsystem, state, message=message)
        return updated.to_dict()

    def get_detector_config(self) -> DetectorConfig:
        return self.runtime.get_detector_config()

    def get_detector_config_dict(self) -> dict:
        return self.runtime.get_detector_config_dict()

    def set_detector_config(self, config: DetectorConfig | dict) -> dict:
        self._assert_mutation_allowed("set_detector_config")
        updated = self.runtime.set_detector_config(config)
        return updated.to_dict()

    def preview_preset_plan(self, plan: PresetPlan) -> dict:
        detector_config_changes = self._diff_values(
            "detector_config",
            self.runtime.get_detector_config_dict(),
            plan.detector_config.to_dict(),
        )

        calibration_changes: list[dict[str, Any]] = []
        target_calibration = self._target_calibration_preview(plan)
        if target_calibration is not None and self.runtime.lamps is not None:
            current_calibration = self.runtime.lamps.get_snapshot().to_dict()
            calibration_changes = self._diff_values(
                "calibration",
                current_calibration,
                target_calibration,
            )

        slit_changes: list[dict[str, Any]] = []
        target_slit = self._target_slit_preview(plan)
        current_slit = self._current_slit_preview()
        if target_slit is not None and current_slit is not None:
            slit_changes = self._diff_values("slit", current_slit, target_slit)

        block_reason = self._mutation_block_reason("apply_preset_plan")

        return {
            "preset": plan.name,
            "summary": plan.summary,
            "category": plan.category,
            "risk_level": plan.risk_level,
            "requires_confirmation": plan.requires_confirmation,
            "blocked": block_reason is not None,
            "blocked_reason": block_reason,
            "detector_config_changes": detector_config_changes,
            "calibration_changes": calibration_changes,
            "slit_changes": slit_changes,
            "changes": detector_config_changes + calibration_changes + slit_changes,
        }

    def apply_preset_plan(self, plan: PresetPlan, *, confirmed: bool = True) -> dict:
        self._assert_preset_confirmation_allowed(plan, confirmed)
        self._assert_mutation_allowed("apply_preset_plan")
        preview = self.preview_preset_plan(plan)

        detector_config = self.runtime.set_detector_config(plan.detector_config).to_dict()

        calibration_result = None
        calibration_applied = False

        if plan.calibration is not None and self.runtime.lamps is not None:
            if plan.calibration.mode == "science":
                snapshot = self.runtime.lamps.set_mode("science")
                calibration_result = snapshot.to_dict()
                calibration_applied = True
            elif plan.calibration.mode == "calibration":
                self.runtime.lamps.set_mode("calibration")
                if plan.calibration.lamp is not None:
                    snapshot = self.runtime.lamps.select_lamp(
                        plan.calibration.lamp,
                        enable=plan.calibration.enabled,
                    )
                else:
                    snapshot = self.runtime.lamps.get_snapshot()
                calibration_result = snapshot.to_dict()
                calibration_applied = True

        skipped_fields: list[str] = []
        if plan.slit is not None and not preview["slit_changes"]:
            skipped_fields.append("slit")

        payload = {
            "applied_preset": plan.name,
            "summary": plan.summary,
            "category": plan.category,
            "risk_level": plan.risk_level,
            "requires_confirmation": plan.requires_confirmation,
            "job_id": None,
            "detector_config": detector_config,
            "calibration": calibration_result,
            "calibration_applied": calibration_applied,
            "slit_plan": plan.slit.to_dict() if plan.slit is not None else None,
            "slit_applied": False,
            "detector_config_changes": preview["detector_config_changes"],
            "calibration_changes": preview["calibration_changes"],
            "slit_changes": preview["slit_changes"],
            "changed_fields": preview["changes"],
            "skipped_fields": skipped_fields,
            "blocked_fields": [],
        }

        request = CommandRequest.create(
            subsystem="presets",
            action="apply_preset",
            params={
                "name": plan.name,
                "category": plan.category,
                "risk_level": plan.risk_level,
                "requires_confirmation": plan.requires_confirmation,
                "confirmed": confirmed,
            },
            source=CommandSource.API,
        )
        job = self.runtime.create_job(request)
        self.runtime.mark_job_succeeded(job.job_id, result=self._preset_apply_job_result(payload))
        payload["job_id"] = job.job_id

        return payload
