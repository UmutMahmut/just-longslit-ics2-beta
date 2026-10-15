from __future__ import annotations

from dataclasses import dataclass

from justls.ics.adapters.slit.adapter import BaseSlitAdapter
from justls.ics.kernel.errors import InvalidParamError


MIN_ANGLE_DEG = -90.0
MAX_ANGLE_DEG = 90.0


@dataclass(slots=True)
class SlitSnapshot:
    width_um: float
    angle_deg: float

    def to_dict(self) -> dict[str, float]:
        return {
            "width_um": self.width_um,
            "angle_deg": self.angle_deg,
        }

    def to_state_fragment(self) -> dict[str, float]:
        return {
            "slit_width_um": self.width_um,
            "slit_angle_deg": self.angle_deg,
        }


class SlitSubsystem:
    def __init__(
        self,
        adapter: BaseSlitAdapter,
        *,
        max_width_um: float | None = None,
    ) -> None:
        self.adapter = adapter
        self.max_width_um = max_width_um

    def get_snapshot(self) -> SlitSnapshot:
        return SlitSnapshot(
            width_um=self.adapter.get_width_um(),
            angle_deg=self.adapter.get_angle_deg(),
        )

    def get_width_um(self) -> float:
        return self.adapter.get_width_um()

    def get_angle_deg(self) -> float:
        return self.adapter.get_angle_deg()

    def set_width_um(self, width_um: float) -> SlitSnapshot:
        width_um = float(width_um)

        if width_um <= 0:
            raise InvalidParamError(
                "slit width must be > 0 um",
                subsystem="slit",
                details={"width_um": width_um},
            )

        if self.max_width_um is not None and width_um > self.max_width_um:
            raise InvalidParamError(
                "slit width exceeds current configured limit",
                subsystem="slit",
                details={
                    "width_um": width_um,
                    "max_width_um": self.max_width_um,
                },
            )

        self.adapter.set_width_um(width_um)
        return self.get_snapshot()

    def set_angle_deg(self, angle_deg: float) -> SlitSnapshot:
        angle_deg = float(angle_deg)

        if angle_deg < MIN_ANGLE_DEG or angle_deg > MAX_ANGLE_DEG:
            raise InvalidParamError(
                "slit angle must be within [-90, 90] deg",
                subsystem="slit",
                details={"angle_deg": angle_deg},
            )

        self.adapter.set_angle_deg(angle_deg)
        return self.get_snapshot()

    def stop(self) -> None:
        self.adapter.stop()