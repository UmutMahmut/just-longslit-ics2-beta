from __future__ import annotations

import time
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

import numpy as np

from justls.ics.domain.detector.frame import DetectorFrameMetadata
from justls.ics.domain.observation.models import validate_exposure_time
from justls.ics.kernel.errors import InvalidStateError, UnsupportedError
from justls.ics.infra.camera_config import CameraDeviceConfig
from justls.ics.drivers.zwo.sdk import (
    ASI_COOLER_ON,
    ASI_COOLER_POWER_PERCENT,
    ASI_EXPOSURE,
    ASI_GAIN,
    ASI_IMG_RAW16,
    ASI_OFFSET,
    ASI_TARGET_TEMPERATURE,
    ASI_TEMPERATURE,
    ZwoCameraDescriptor,
    ZwoCameraSession,
    ZwoSdk,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ZwoDetectorDriver:
    """Hardware detector driver for one ZWO camera using snap-mode RAW16."""

    def __init__(
        self,
        sdk: ZwoSdk,
        descriptor: ZwoCameraDescriptor,
        config: CameraDeviceConfig,
        *,
        gain: int = 0,
        offset: int = 30,
        binning: int = 1,
    ) -> None:
        if config.driver != "zwo":
            raise ValueError("ZwoDetectorDriver requires driver='zwo'")
        if config.width > descriptor.max_width or config.height > descriptor.max_height:
            raise ValueError("configured ROI exceeds the detected sensor dimensions")
        if "RAW16" not in descriptor.supported_image_types:
            raise ValueError("detected camera does not advertise RAW16 support")
        if binning not in descriptor.supported_bins:
            raise ValueError(f"detected camera does not support binning={binning}")

        self.sdk = sdk
        self.descriptor = descriptor
        self.config = config
        self.gain = int(gain)
        self.offset = int(offset)
        self.binning = int(binning)
        self.width = int(config.width)
        self.height = int(config.height)
        self._lock = RLock()
        self._session_context: ZwoCameraSession | None = None
        self._session: ZwoCameraSession | None = None
        self.detected_serial: str | None = None
        self._active: dict[str, Any] | None = None
        self._exposure_deadline = 0.0
        self._latest_image: np.ndarray | None = None
        self._latest_capture: dict[str, Any] | None = None
        # Last trustworthy temperature reading, for stale/invalid semantics.
        self._last_temperature_c: float | None = None
        self._last_temperature_at: float | None = None
        self.control_limits: dict[int, Any] = {}
        self._last_cooling: dict[str, Any] | None = None


    def get_settings(self) -> dict:
        from justls.ics.infra.acquisition_settings import describe
        return describe(self)

    def configure_settings(self, updates: dict) -> dict:
        with self._lock:
            from justls.ics.drivers.zwo.settings import configure
            return configure(self, updates)

    def connect(self) -> None:
        with self._lock:
            if self._session is not None:
                return
            context = self.sdk.open_camera(self.descriptor.camera_id)
            try:
                session = context.__enter__()
                session.set_roi_format(
                    width=self.width,
                    height=self.height,
                    binning=self.binning,
                    image_type=ASI_IMG_RAW16,
                )
                detected_serial = session.serial_number()
                controls = getattr(session, "controls", None)
                if callable(controls):
                    self.control_limits = {control.control_type: control for control in controls()}
                if self.config.serial and self.config.serial != detected_serial:
                    raise RuntimeError(
                        "detected ZWO serial number does not match the deployment "
                        f"profile: expected={self.config.serial}, "
                        f"detected={detected_serial}"
                    )
            except Exception:
                context.__exit__(None, None, None)
                raise
            self._session_context = context
            self._session = session
            self.detected_serial = detected_serial
            if self.descriptor.cooler:
                self.cooling_status()

    def disconnect(self) -> None:
        with self._lock:
            if self._active is not None:
                self.abort_exposure()
            context = self._session_context
            self._session_context = None
            self._session = None
            if context is not None:
                context.__exit__(None, None, None)

    def __enter__(self) -> "ZwoDetectorDriver":
        self.connect()
        return self

    def __exit__(self, *_exc_info: Any) -> None:
        self.disconnect()

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
            validate_exposure_time(float(exp_time_s), frame_type)
            session = self._require_session()

            exposure_limit = self.control_limits.get(ASI_EXPOSURE)
            minimum_us = exposure_limit.minimum if exposure_limit is not None else 1
            exposure_us = max(minimum_us, round(float(exp_time_s) * 1_000_000))
            if exposure_limit is not None and exposure_us > exposure_limit.maximum:
                from justls.ics.kernel.errors import InvalidParamError
                raise InvalidParamError("Requested exposure exceeds this camera's SDK maximum", subsystem="detector")
            self.gain, _ = session.set_control_value(ASI_GAIN, self.gain)
            self.offset, _ = session.set_control_value(ASI_OFFSET, self.offset)
            actual_exposure_us, _ = session.set_control_value(
                ASI_EXPOSURE,
                exposure_us,
            )

            active = {
                "obs_id": obs_id,
                "exp_id": exp_id,
                "frame_type": frame_type,
                "exp_time_s": float(exp_time_s),
                "requested_exp_time_s": float(exp_time_s),
                "actual_exp_time_s": actual_exposure_us / 1_000_000.0,
                "save_requested": bool(save_requested),
                "frame_token": f"frame-{uuid4().hex[:12]}",
                "started_at": utc_now_iso(),
            }
            session.start_exposure(dark=frame_type.strip().lower() in {"bias", "dark"})
            self._exposure_deadline = time.monotonic() + active["actual_exp_time_s"]
            self._active = active
            return {
                **active,
                "detector_metadata": self._frame_metadata().model_dump(mode="json"),
            }

    def finish_exposure(self) -> dict[str, Any]:
        with self._lock:
            active = self._require_active()
            session = self._require_session()
            timeout_s = max(10.0, active["actual_exp_time_s"] + 10.0)
            status = session.wait_for_exposure(timeout_s=timeout_s)
            if status != "success":
                self._active = None
                raise RuntimeError(f"ZWO exposure ended with status={status!r}")
            return self._readout(early_stop=False)

    def ensure_readout_ready(self) -> None:
        """Reject premature Finish without blocking Abort for a long integration."""
        with self._lock:
            self._require_active()
            if time.monotonic() < self._exposure_deadline - 0.1:
                raise InvalidStateError(
                    "Exposure is still integrating; wait for automatic readout or use Abort.",
                    subsystem="detector",
                )

    def stop_exposure_and_readout(self) -> dict[str, Any]:
        self.ensure_early_readout_supported()

    def ensure_early_readout_supported(self) -> None:
        # Snap-mode Stop has no verified retained-image contract. Do not
        # destroy an integration in an attempt to implement Stop & Readout.
        raise UnsupportedError(
            "Retained early readout is not supported by this ZWO snap adapter; "
            "wait for normal readout or use Abort to discard the exposure.",
            subsystem="detector",
        )

    def _readout(self, *, early_stop: bool) -> dict[str, Any]:
        active = self._require_active()
        session = self._require_session()
        payload = session.read_exposure_data(
            buffer_size=self.width * self.height * 2
        )
        image = np.frombuffer(payload, dtype="<u2").reshape(
            self.height,
            self.width,
        )
        finished_at = utc_now_iso()
        result = {
            **active,
            "finished_at": finished_at,
            "result": "completed",
            "early_stop": early_stop,
            "physical_camera_id": self.config.device_id,
            "detector_metadata": self._frame_metadata().model_dump(mode="json"),
            "image": image,
        }
        self._latest_image = image.copy()
        self._latest_capture = {
            key: value for key, value in result.items() if key != "image"
        }
        self._active = None
        return result

    def abort_exposure(self) -> dict[str, Any]:
        with self._lock:
            active = self._active
            if active is not None:
                self._require_session().stop_exposure()
            self._active = None
            return {
                "result": "aborted",
                "finished_at": utc_now_iso(),
                "had_active_exposure": active is not None,
            }

    def acquire_exposure(
        self,
        *,
        obs_id: str,
        exp_time_s: float,
        frame_type: str,
        save_requested: bool = True,
    ) -> dict[str, Any]:
        self.start_exposure(
            obs_id=obs_id,
            exp_id=f"exp-{uuid4().hex[:12]}",
            exp_time_s=exp_time_s,
            frame_type=frame_type,
            save_requested=save_requested,
        )
        return self.finish_exposure()

    def set_cooling(
        self,
        *,
        enabled: bool,
        target_temperature_c: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if not self.descriptor.cooler:
                raise RuntimeError("detected camera does not advertise a cooler")
            session = self._require_session()
            if target_temperature_c is not None:
                session.set_control_value(
                    ASI_TARGET_TEMPERATURE,
                    int(target_temperature_c),
                )
            session.set_control_value(ASI_COOLER_ON, int(enabled))
            return self.cooling_status()

    def cooling_status(self) -> dict[str, Any]:
        """Cooler telemetry with explicit validity semantics.

        ``temperature_state`` is one of:

        - ``"stable"``  — fresh, trustworthy reading from the sensor;
        - ``"stale"``   — the current read failed or is untrustworthy, so the
          last trustworthy reading is reported instead;
        - ``"invalid"`` — no trustworthy reading exists at all
          (``detector_temperature_c`` is then ``None`` and must not be
          written into FITS as if it were a measurement).

        An exact 0.0 C raw reading is treated as untrustworthy: that is what
        the ASI294MC Pro reports when its 12 V cooler supply is unplugged
        (verified on the bench 2026-10-08; a companion camera read a sane
        room temperature at the same time).
        """
        session = self._require_session()
        temperature_c: float | None = None
        try:
            temperature_raw, _ = session.control_value(ASI_TEMPERATURE)
            if temperature_raw != 0:
                temperature_c = temperature_raw / 10.0
        except Exception:
            temperature_c = None

        now = time.monotonic()
        if temperature_c is not None:
            self._last_temperature_c = temperature_c
            self._last_temperature_at = now
            temperature_state = "stable"
        elif self._last_temperature_c is not None:
            temperature_c = self._last_temperature_c
            temperature_state = "stale"
        else:
            temperature_state = "invalid"

        target, _ = session.control_value(ASI_TARGET_TEMPERATURE)
        enabled, _ = session.control_value(ASI_COOLER_ON)
        power, _ = session.control_value(ASI_COOLER_POWER_PERCENT)
        result = {
            "detector_temperature_c": temperature_c,
            "temperature_state": temperature_state,
            "temperature_age_s": (
                None
                if self._last_temperature_at is None
                else round(now - self._last_temperature_at, 3)
            ),
            "cooler_target_c": float(target),
            "cooler_enabled": bool(enabled),
            "cooler_power_pct": float(power),
        }
        self._last_cooling = dict(result)
        return result

    def get_latest_image(self) -> np.ndarray:
        with self._lock:
            if self._latest_image is None:
                raise RuntimeError("science camera has no completed acquisition")
            return self._latest_image.copy()

    def get_status(self) -> dict[str, Any]:
        # Status polling must not perform SDK I/O or queue behind a readout.
        session = self._session
        active = self._active
        error = getattr(self.sdk, "health_error", None)
        cooling = dict(self._last_cooling) if self._last_cooling else None
        if cooling is not None and self._last_temperature_at is not None:
            cooling["temperature_age_s"] = round(time.monotonic() - self._last_temperature_at, 3)
            if cooling["temperature_age_s"] > 5:
                cooling["temperature_state"] = "stale"
        exposure_state = "unavailable" if error else ("working" if active else "idle")
        return {
            "device_id": self.config.device_id,
            "role": "science",
            "driver": self.config.driver,
            "model": self.descriptor.name,
            "serial": self.detected_serial or self.config.serial,
            "state": exposure_state,
            "connected": session is not None and error is None,
            "error": error,
            "active_exposure": dict(active) if active else None,
            "latest_capture": dict(self._latest_capture)
            if self._latest_capture
            else None,
            "cooling": cooling,
        }

    def _frame_metadata(self) -> DetectorFrameMetadata:
        cooling = self.cooling_status() if self.descriptor.cooler else {}
        # Telemetry-only diagnostics that do not belong in the FITS contract.
        cooling.pop("temperature_age_s", None)
        if cooling.get("temperature_state") == "invalid":
            # Never write an untrustworthy reading (e.g. 0.0 C with the 12 V
            # cooler supply unplugged) into CCD-TEMP as if it were real.
            cooling["detector_temperature_c"] = None
        return DetectorFrameMetadata(
            manufacturer=self.config.manufacturer or "ZWO",
            model=self.descriptor.name,
            serial=self.detected_serial or self.config.serial,
            width=self.width,
            height=self.height,
            pixel_format="RAW16",
            sensor_bit_depth=self.descriptor.bit_depth,
            bayer_pattern=self.descriptor.bayer_pattern,
            bin_x=self.binning,
            bin_y=self.binning,
            gain=float(self.gain),
            offset=float(self.offset),
            **cooling,
        )

    def _require_session(self) -> ZwoCameraSession:
        if self._session is None:
            raise RuntimeError("ZWO camera is not connected")
        return self._session

    def _require_active(self) -> dict[str, Any]:
        if self._active is None:
            raise RuntimeError("science camera has no active exposure")
        return self._active
