from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

import numpy as np

from justls.ics.domain.detector.frame import DetectorFrameMetadata
from justls.ics.drivers.sim.camera_driver import synthetic_spectrum
from justls.ics.infra.camera_config import CameraDeviceConfig


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SimDetectorDriver:
    """Stateful science-camera simulator with hardware-shaped lifecycle calls."""

    def __init__(
        self,
        config: CameraDeviceConfig | None = None,
        *,
        role: str = "science",
    ) -> None:
        self.config = config or CameraDeviceConfig(
            device_id="science-camera-01",
            manufacturer="SIMULATED",
        )
        self.role = role
        self.sensor_shape = (self.config.width, self.config.height)
        self._lock = RLock()
        self._active: dict[str, Any] | None = None
        self._latest_image: np.ndarray | None = None
        self._latest_capture: dict[str, Any] | None = None


    def get_settings(self) -> dict:
        from justls.ics.infra.acquisition_settings import describe
        return describe(self)

    def configure_settings(self, updates: dict) -> dict:
        with self._lock:
            from justls.ics.infra.acquisition_settings import configure_simulated
            return configure_simulated(self, updates)

    def start_exposure(
        self,
        *,
        obs_id: str,
        exp_id: str,
        exp_time_s: float,
        frame_type: str,
        save_requested: bool,
    ) -> dict[str, Any]:
        with self._lock:
            if self._active is not None:
                raise RuntimeError("science camera already has an active exposure")
            self._active = {
                "obs_id": obs_id,
                "exp_id": exp_id,
                "frame_type": frame_type,
                "exp_time_s": float(exp_time_s),
                "save_requested": bool(save_requested),
                "frame_token": f"frame-{uuid4().hex[:12]}",
                "started_at": utc_now_iso(),
                "detector_metadata": DetectorFrameMetadata(
                    manufacturer="SIMULATED",
                    model=self.config.model or "synthetic-spectrum",
                    serial=self.config.serial,
                    width=self.config.width,
                    height=self.config.height,
                    pixel_format=(
                        "MONO8" if self.config.bit_depth <= 8 else "MONO16"
                    ),
                    sensor_bit_depth=self.config.bit_depth,
                    bin_x=self.config.binning,
                    bin_y=self.config.binning,
                    gain=self.config.gain,
                    offset=float(self.config.offset),
                ).model_dump(mode="json"),
            }
            return dict(self._active)

    def finish_exposure(self) -> dict[str, Any]:
        return self._readout(early_stop=False)

    def stop_exposure_and_readout(self) -> dict[str, Any]:
        return self._readout(early_stop=True)

    def _readout(self, *, early_stop: bool) -> dict[str, Any]:
        with self._lock:
            if self._active is None:
                raise RuntimeError("science camera has no active exposure")
            active = self._active
            finished_at = datetime.now(timezone.utc)
            started_at = datetime.fromisoformat(active["started_at"])
            actual_exp_time_s = max(
                0.0,
                (finished_at - started_at).total_seconds(),
            )
            image = synthetic_spectrum(
                width=self.config.width,
                height=self.config.height,
                seed_text=active["frame_token"],
            )
            result = {
                **active,
                "finished_at": finished_at.isoformat(),
                "requested_exp_time_s": active["exp_time_s"],
                "actual_exp_time_s": actual_exp_time_s,
                "result": "completed",
                "early_stop": early_stop,
                "physical_camera_id": self.config.device_id,
                "image": image,
            }
            self._latest_image = image
            self._latest_capture = {
                key: value for key, value in result.items() if key != "image"
            }
            self._active = None
            return result

    def abort_exposure(self) -> dict[str, Any]:
        with self._lock:
            active = self._active
            self._active = None
            return {
                "result": "aborted",
                "finished_at": utc_now_iso(),
                "had_active_exposure": active is not None,
            }

    def get_latest_image(self) -> np.ndarray:
        with self._lock:
            if self._latest_image is None:
                raise RuntimeError("science camera has no completed acquisition")
            return self._latest_image.copy()

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "device_id": self.config.device_id,
                "role": self.role,
                "driver": self.config.driver,
                "model": self.config.model,
                "serial": self.config.serial,
                "state": "exposing" if self._active is not None else "idle",
                "active_exposure": dict(self._active) if self._active else None,
                "latest_capture": dict(self._latest_capture)
                if self._latest_capture
                else None,
            }

    def acquire_exposure(
        self,
        *,
        obs_id: str,
        exp_time_s: float,
        frame_type: str,
        save_requested: bool = True,
    ) -> dict[str, Any]:
        """Compatibility convenience for the original one-shot adapter contract."""
        self.start_exposure(
            obs_id=obs_id,
            exp_id=f"exp-{uuid4().hex[:12]}",
            exp_time_s=exp_time_s,
            frame_type=frame_type,
            save_requested=save_requested,
        )
        return self.finish_exposure()
