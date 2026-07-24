from __future__ import annotations

from justls.ics.drivers.sim.camera_driver import SimPreviewCameraDriver


class SimPreviewCameraAdapter:
    def __init__(self, driver: SimPreviewCameraDriver) -> None:
        self.driver = driver

    def get_preview(self) -> tuple[bytes, dict]:
        return self.driver.capture_jpeg()

    def get_status(self) -> dict:
        return self.driver.status()
