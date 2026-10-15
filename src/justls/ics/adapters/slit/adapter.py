from __future__ import annotations

from abc import ABC, abstractmethod

from justls.ics.drivers.sim.slit_driver import SimSlitDriver


class BaseSlitAdapter(ABC):
    @abstractmethod
    def get_width_um(self) -> float: ...

    @abstractmethod
    def get_angle_deg(self) -> float: ...

    @abstractmethod
    def set_width_um(self, width_um: float) -> None: ...

    @abstractmethod
    def set_angle_deg(self, angle_deg: float) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...


class SimSlitAdapter(BaseSlitAdapter):
    def __init__(self, driver: SimSlitDriver) -> None:
        self.driver = driver

    def get_width_um(self) -> float:
        return self.driver.get_width_um()

    def get_angle_deg(self) -> float:
        return self.driver.get_angle_deg()

    def set_width_um(self, width_um: float) -> None:
        self.driver.set_width_um(width_um)

    def set_angle_deg(self, angle_deg: float) -> None:
        self.driver.set_angle_deg(angle_deg)

    def stop(self) -> None:
        self.driver.stop()