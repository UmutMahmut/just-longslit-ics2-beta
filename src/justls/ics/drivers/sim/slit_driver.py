from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SimSlitState:
    width_um: float = 120.0
    angle_deg: float = 0.0


class SimSlitDriver:
    def __init__(self) -> None:
        self._state = SimSlitState()

    def get_width_um(self) -> float:
        return self._state.width_um

    def get_angle_deg(self) -> float:
        return self._state.angle_deg

    def set_width_um(self, width_um: float) -> None:
        self._state.width_um = float(width_um)

    def set_angle_deg(self, angle_deg: float) -> None:
        self._state.angle_deg = float(angle_deg)

    def stop(self) -> None:
        return None