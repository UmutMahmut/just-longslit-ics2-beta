from __future__ import annotations

from dataclasses import dataclass

from justls.ics.adapters.lamps.adapter import BaseCalibrationAdapter
from justls.ics.drivers.sim.lamp_driver import CalibrationLampType, CalibrationMode
from justls.ics.kernel.errors import InvalidParamError


@dataclass(slots=True)
class CalibrationSnapshot:
    mode: CalibrationMode
    active_lamp: CalibrationLampType | None
    lamp_enabled: bool
    mirror_inserted: bool

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "active_lamp": self.active_lamp.value if self.active_lamp is not None else None,
            "lamp_enabled": self.lamp_enabled,
            "mirror_inserted": self.mirror_inserted,
        }

    def to_legacy_state_fragment(self) -> dict[str, bool]:
        return {
            "lamp_on": self.lamp_enabled,
        }


class CalibrationSubsystem:
    def __init__(self, adapter: BaseCalibrationAdapter) -> None:
        self.adapter = adapter

    def get_snapshot(self) -> CalibrationSnapshot:
        return CalibrationSnapshot(
            mode=self.adapter.get_mode(),
            active_lamp=self.adapter.get_active_lamp(),
            lamp_enabled=self.adapter.is_lamp_enabled(),
            mirror_inserted=self.adapter.is_mirror_inserted(),
        )

    def set_mode(self, mode: str | CalibrationMode) -> CalibrationSnapshot:
        if isinstance(mode, str):
            try:
                mode = CalibrationMode(mode)
            except ValueError as exc:
                raise InvalidParamError(
                    "unsupported calibration mode",
                    subsystem="lamps",
                    details={"mode": mode},
                ) from exc

        self.adapter.set_mode(mode)
        return self.get_snapshot()

    def select_lamp(self, lamp: str | CalibrationLampType, *, enable: bool = True) -> CalibrationSnapshot:
        if isinstance(lamp, str):
            try:
                lamp = CalibrationLampType(lamp)
            except ValueError as exc:
                raise InvalidParamError(
                    "unsupported calibration lamp",
                    subsystem="lamps",
                    details={"lamp": lamp},
                ) from exc

        self.adapter.set_active_lamp(lamp)
        self.adapter.set_lamp_enabled(enable)
        return self.get_snapshot()

    def set_legacy_on(self, on: bool) -> CalibrationSnapshot:
        if on:
            self.adapter.set_active_lamp(CalibrationLampType.FLAT)
            self.adapter.set_lamp_enabled(True)
        else:
            self.adapter.set_lamp_enabled(False)
        return self.get_snapshot()