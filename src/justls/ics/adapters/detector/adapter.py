from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from justls.ics.drivers.sim.detector_driver import SimDetectorDriver
from justls.ics.infra.data_products import (
    LocalDataProductWriter,
    render_quicklook_png,
)


class BaseDetectorAdapter(ABC):
    @abstractmethod
    def start_exposure(
        self,
        *,
        obs_id: str,
        exp_id: str,
        exp_time_s: float,
        frame_type: str,
        save_requested: bool,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def finish_exposure(self) -> dict[str, Any]: ...

    @abstractmethod
    def stop_exposure_and_readout(self) -> dict[str, Any]: ...

    @abstractmethod
    def abort_exposure(self) -> dict[str, Any]: ...

    @abstractmethod
    def get_status(self) -> dict[str, Any]: ...

    @abstractmethod
    def get_latest_preview(self) -> tuple[bytes, dict[str, Any]]: ...


class SimDetectorAdapter(BaseDetectorAdapter):
    def __init__(
        self,
        driver: SimDetectorDriver,
        *,
        writer: LocalDataProductWriter | None = None,
        logical_channels: tuple[str, ...] = ("B", "G", "R"),
    ) -> None:
        self.driver = driver
        self.writer = writer
        self.logical_channels = logical_channels
        self._latest_preview: bytes | None = None

    def start_exposure(
        self,
        *,
        obs_id: str,
        exp_id: str,
        exp_time_s: float,
        frame_type: str,
        save_requested: bool,
    ) -> dict[str, Any]:
        return self.driver.start_exposure(
            obs_id=obs_id,
            exp_id=exp_id,
            exp_time_s=exp_time_s,
            frame_type=frame_type,
            save_requested=save_requested,
        )

    def finish_exposure(self) -> dict[str, Any]:
        return self._complete(self.driver.finish_exposure())

    def stop_exposure_and_readout(self) -> dict[str, Any]:
        return self._complete(self.driver.stop_exposure_and_readout())

    def _complete(self, result: dict[str, Any]) -> dict[str, Any]:
        image = result.pop("image")
        self._latest_preview = render_quicklook_png(image)
        result["logical_channels"] = list(self.logical_channels)
        result["shared_capture_id"] = result["frame_token"]
        result["simulated"] = True

        if result["save_requested"] and self.writer is not None:
            products = self.writer.write(
                image,
                obs_id=result["obs_id"],
                exp_id=result["exp_id"],
                frame_token=result["frame_token"],
                frame_type=result["frame_type"],
                exp_time_s=result["exp_time_s"],
                camera_id=result["physical_camera_id"],
                logical_channels=self.logical_channels,
                started_at=result["started_at"],
                finished_at=result["finished_at"],
            )
            result.update(products.to_result_fragment())
        return result

    def abort_exposure(self) -> dict[str, Any]:
        return self.driver.abort_exposure()

    def get_status(self) -> dict[str, Any]:
        status = self.driver.get_status()
        status["logical_channels"] = list(self.logical_channels)
        status["shared_across_logical_channels"] = True
        return status

    def get_latest_preview(self) -> tuple[bytes, dict[str, Any]]:
        if self._latest_preview is None:
            self._latest_preview = render_quicklook_png(self.driver.get_latest_image())
        status = self.get_status()
        status["media_type"] = "image/png"
        return self._latest_preview, status

    def acquire_exposure(
        self,
        *,
        obs_id: str,
        exp_time_s: float,
        frame_type: str,
        save_requested: bool = True,
    ) -> dict[str, Any]:
        """Compatibility one-shot call retained for older adapter consumers."""
        result = self.driver.acquire_exposure(
            obs_id=obs_id,
            exp_time_s=exp_time_s,
            frame_type=frame_type,
            save_requested=save_requested,
        )
        return self._complete(result)
