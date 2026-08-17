from __future__ import annotations

from justls.ics.drivers.sim.camera_driver import SimPreviewCameraDriver


class SimPreviewCameraAdapter:
    def __init__(self, driver: SimPreviewCameraDriver) -> None:
        self.driver = driver

    def get_preview(self) -> tuple[bytes, dict]:
        return self.driver.capture_jpeg()

    def start_preview(self) -> dict:
        return self.driver.start_preview()

    def stop_preview(self) -> dict:
        return self.driver.stop_preview()

    def get_status(self) -> dict:
        return self.driver.status()
