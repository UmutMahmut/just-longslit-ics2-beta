from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CalibrationMode(str, Enum):
    SCIENCE = "science"
    CALIBRATION = "calibration"


class CalibrationLampType(str, Enum):
    FLAT = "flat"
    ARC_HGAR = "arc_hgar"
    ARC_NE = "arc_ne"


@dataclass(slots=True)
class SimCalibrationState:
    mode: CalibrationMode = CalibrationMode.SCIENCE
    active_lamp: CalibrationLampType | None = None
    lamp_enabled: bool = False
    mirror_inserted: bool = False


class SimCalibrationDriver:
    def __init__(self) -> None:
        self._state = SimCalibrationState()

    def get_mode(self) -> CalibrationMode:
        return self._state.mode

    def get_active_lamp(self) -> CalibrationLampType | None:
        return self._state.active_lamp

    def is_lamp_enabled(self) -> bool:
        return self._state.lamp_enabled

    def is_mirror_inserted(self) -> bool:
        return self._state.mirror_inserted

    def set_mode(self, mode: CalibrationMode) -> None:
        self._state.mode = mode
        self._state.mirror_inserted = mode == CalibrationMode.CALIBRATION
        if mode == CalibrationMode.SCIENCE:
            self._state.lamp_enabled = False
            self._state.active_lamp = None

    def set_active_lamp(self, lamp: CalibrationLampType | None) -> None:
        self._state.active_lamp = lamp

    def set_lamp_enabled(self, enabled: bool) -> None:
        self._state.lamp_enabled = bool(enabled)
        if not enabled:
            self._state.active_lamp = None
            self._state.mode = CalibrationMode.SCIENCE
            self._state.mirror_inserted = False
        else:
            self._state.mode = CalibrationMode.CALIBRATION
            self._state.mirror_inserted = True
            if self._state.active_lamp is None:
                self._state.active_lamp = CalibrationLampType.FLAT