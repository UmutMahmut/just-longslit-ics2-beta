from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

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


class DetectorDriver(Protocol):
    def start_exposure(self, **kwargs: Any) -> dict[str, Any]: ...

    def finish_exposure(self) -> dict[str, Any]: ...

    def stop_exposure_and_readout(self) -> dict[str, Any]: ...

    def abort_exposure(self) -> dict[str, Any]: ...

    def get_status(self) -> dict[str, Any]: ...

    def get_latest_image(self) -> Any: ...


class DetectorAdapter(BaseDetectorAdapter):
    def __init__(
        self,
        driver: DetectorDriver,
        *,
        writer: LocalDataProductWriter | None = None,
        logical_channels: tuple[str, ...] = ("B", "G", "R"),
        simulated: bool = False,
    ) -> None:
        self.driver = driver
        self.writer = writer
        self.logical_channels = logical_channels
        self.simulated = simulated
        self._latest_preview: bytes | None = None
        # The last completed frame stays available so an operator who forgot to
        # request saving at arm time can still persist it afterwards.
        self._last_image: Any | None = None
        self._last_result: dict[str, Any] | None = None
        self._last_products: dict[str, Any] | None = None

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
        result["simulated"] = self.simulated

        self._last_image = image
        self._last_result = dict(result)
        self._last_products = None

        if result["save_requested"] and self.writer is not None:
            self._last_products = self._write_frame(image, result)
            result.update(self._last_products)
        return result

    def _write_frame(self, image: Any, result: dict[str, Any]) -> dict[str, Any]:
        products = self.writer.write(
            image,
            obs_id=result["obs_id"],
            exp_id=result["exp_id"],
            frame_token=result["frame_token"],
            frame_type=result["frame_type"],
            exp_time_s=result["exp_time_s"],
            actual_exp_time_s=result.get("actual_exp_time_s"),
            camera_id=result["physical_camera_id"],
            logical_channels=self.logical_channels,
            started_at=result["started_at"],
            finished_at=result["finished_at"],
            detector_metadata=result.get("detector_metadata"),
            simulated=self.simulated,
        )
        return products.to_result_fragment()

    def save_last_frame(self) -> dict[str, Any]:
        """Persist the most recent completed frame.

        Returns the data-product fragment. Frames that were already saved at
        readout time are reported back without writing a second copy.
        """
        if self._last_image is None or self._last_result is None:
            raise RuntimeError("no completed frame is available to save")
        if self.writer is None:
            raise RuntimeError("no data writer is configured for this detector")

        if self._last_products is not None:
            return {
                **self._last_products,
                "saved": True,
                "already_saved": True,
                "frame_token": self._last_result["frame_token"],
            }

        self._last_products = self._write_frame(self._last_image, self._last_result)
        return {
            **self._last_products,
            "saved": True,
            "already_saved": False,
            "frame_token": self._last_result["frame_token"],
        }

    def abort_exposure(self) -> dict[str, Any]:
        # A discarded exposure yields no image, so the pending save buffer must
        # be dropped; otherwise "save last frame" would silently re-persist the
        # previous frame under the aborted observation.
        self._last_image = None
        self._last_result = None
        self._last_products = None
        return self.driver.abort_exposure()

    def get_status(self) -> dict[str, Any]:
        status = self.driver.get_status()
        status["logical_channels"] = list(self.logical_channels)
        status["shared_across_logical_channels"] = len(self.logical_channels) > 1
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


class SimDetectorAdapter(DetectorAdapter):
    def __init__(
        self,
        driver: SimDetectorDriver,
        *,
        writer: LocalDataProductWriter | None = None,
        logical_channels: tuple[str, ...] = ("B", "G", "R"),
    ) -> None:
        super().__init__(
            driver,
            writer=writer,
            logical_channels=logical_channels,
            simulated=True,
        )
