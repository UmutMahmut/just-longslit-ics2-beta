from __future__ import annotations

from typing import Any, Protocol


class _PreviewDriver(Protocol):
    """Structural interface shared by sim and ZWO preview drivers."""

    def capture_jpeg(self) -> tuple[bytes, dict[str, Any]]: ...

    def start_preview(self) -> dict[str, Any]: ...

    def stop_preview(self) -> dict[str, Any]: ...

    def status(self) -> dict[str, Any]: ...


class PreviewCameraAdapter:
    """Driver-agnostic slit/guide preview adapter (sim or ZWO hardware)."""

    def __init__(self, driver: _PreviewDriver) -> None:
        self.driver = driver

    def get_preview(self) -> tuple[bytes, dict]:
        return self.driver.capture_jpeg()

    def start_preview(self) -> dict:
        return self.driver.start_preview()

    def stop_preview(self) -> dict:
        return self.driver.stop_preview()

    def get_status(self) -> dict:
        return self.driver.status()


# Backwards-compatible alias; the adapter is no longer sim-specific.
SimPreviewCameraAdapter = PreviewCameraAdapter
