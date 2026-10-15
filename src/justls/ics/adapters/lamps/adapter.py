from __future__ import annotations

from abc import ABC, abstractmethod

from justls.ics.drivers.sim.lamp_driver import (
    CalibrationLampType,
    CalibrationMode,
    SimCalibrationDriver,
)


class BaseCalibrationAdapter(ABC):
    @abstractmethod
    def get_mode(self) -> CalibrationMode: ...

    @abstractmethod
    def get_active_lamp(self) -> CalibrationLampType | None: ...

    @abstractmethod
    def is_lamp_enabled(self) -> bool: ...

    @abstractmethod
    def is_mirror_inserted(self) -> bool: ...

    @abstractmethod
    def set_mode(self, mode: CalibrationMode) -> None: ...

    @abstractmethod
    def set_active_lamp(self, lamp: CalibrationLampType | None) -> None: ...

    @abstractmethod
    def set_lamp_enabled(self, enabled: bool) -> None: ...


class SimCalibrationAdapter(BaseCalibrationAdapter):
    def __init__(self, driver: SimCalibrationDriver) -> None:
        self.driver = driver

    def get_mode(self) -> CalibrationMode:
        return self.driver.get_mode()

    def get_active_lamp(self) -> CalibrationLampType | None:
        return self.driver.get_active_lamp()

    def is_lamp_enabled(self) -> bool:
        return self.driver.is_lamp_enabled()

    def is_mirror_inserted(self) -> bool:
        return self.driver.is_mirror_inserted()

    def set_mode(self, mode: CalibrationMode) -> None:
        self.driver.set_mode(mode)

    def set_active_lamp(self, lamp: CalibrationLampType | None) -> None:
        self.driver.set_active_lamp(lamp)

    def set_lamp_enabled(self, enabled: bool) -> None:
        self.driver.set_lamp_enabled(enabled)