from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from threading import RLock
from typing import Any

import numpy as np
from PIL import Image

from justls.ics.drivers.zwo.sdk import (
    ASI_EXPOSURE,
    ASI_GAIN,
    ASI_IMG_RAW16,
    ASI_OFFSET,
    ASI_TEMPERATURE,
    ZwoCameraDescriptor,
    ZwoCameraSession,
    ZwoSdk,
)
from justls.ics.infra.camera_config import CameraDeviceConfig

# JPEG payloads are for on-screen slit/guide monitoring only; capping the
# rendered size keeps API responses fast without touching the capture ROI.
_MAX_JPEG_EDGE = 1280
logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ZwoPreviewCameraDriver:
    """Hardware slit/guide preview driver using snap-mode RAW16 captures.

    Each preview frame is a single short exposure rendered to an 8-bit JPEG.
    This deliberately reuses the same hardened session handling as the
    science driver instead of the SDK's video mode: video streaming would
    conflict with the exclusive session model and is unnecessary for a
    ~1 Hz slit monitor.
    """

    def __init__(
        self,
        sdk: ZwoSdk,
        descriptor: ZwoCameraDescriptor,
        config: CameraDeviceConfig,
        *,
        role: str = "slit",
        gain: int | None = None,
        offset: int | None = None,
        binning: int | None = None,
    ) -> None:
        if config.driver != "zwo":
            raise ValueError("ZwoPreviewCameraDriver requires driver='zwo'")
        if config.width > descriptor.max_width or config.height > descriptor.max_height:
            raise ValueError("configured ROI exceeds the detected sensor dimensions")
        if "RAW16" not in descriptor.supported_image_types:
            raise ValueError("detected camera does not advertise RAW16 support")

        self.sdk = sdk
        self.descriptor = descriptor
        self.config = config
        self.role = role
        self.gain = int(config.gain if gain is None else gain)
        self.offset = int(config.offset if offset is None else offset)
        self.binning = int(config.binning if binning is None else binning)
        if self.binning not in descriptor.supported_bins:
            raise ValueError(
                f"detected camera does not support binning={self.binning}"
            )
        # ZWO ROI constraints: width must be a multiple of 8, height of 2.
        self.width = int(config.width) - (int(config.width) % 8)
        self.height = int(config.height) - (int(config.height) % 2)
        if self.width <= 0 or self.height <= 0:
            raise ValueError("configured ROI is too small after ZWO alignment")

        self._lock = RLock()
        self._session_context: ZwoCameraSession | None = None
        self._session: ZwoCameraSession | None = None
        self.detected_serial: str | None = None
        self._preview_enabled = False
        self._sequence = 0
        self._last_capture: dict[str, Any] | None = None
        self._last_error: str | None = None
        self._failed_frames = 0
        self._temperature_c: float | None = None
        self.control_limits: dict[int, Any] = {}


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
            self._preview_enabled = True
            raw, _ = session.control_value(ASI_TEMPERATURE)
            self._temperature_c = raw / 10.0 if raw != 0 else None

    def disconnect(self) -> None:
        with self._lock:
            self._preview_enabled = False
            context = self._session_context
            self._session_context = None
            self._session = None
            if context is not None:
                context.__exit__(None, None, None)

    def __enter__(self) -> "ZwoPreviewCameraDriver":
        self.connect()
        return self

    def __exit__(self, *_exc_info: Any) -> None:
        self.disconnect()

    def start_preview(self) -> dict[str, Any]:
        with self._lock:
            self._require_session()
            self._preview_enabled = True
            return self.status()

    def stop_preview(self) -> dict[str, Any]:
        with self._lock:
            self._preview_enabled = False
            return self.status()

    def capture_jpeg(self) -> tuple[bytes, dict[str, Any]]:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("slit/guide frame is already being read; retry next refresh")
        try:
            result = self._capture_jpeg_locked()
            self._last_error = None
            return result
        except Exception as exc:
            if self._preview_enabled:
                self._failed_frames += 1
                self._last_error = f"{type(exc).__name__}: {exc}"
                logger.exception("Guide capture failed device=%s frame=%s", self.config.device_id, self._sequence + 1)
                # A failed snap must be cleared before the next requested frame.
                # The native gate prevents cleanup entering a quarantined DLL.
                try:
                    if self._session is not None:
                        self._session.stop_exposure()
                except Exception:
                    logger.warning("Guide frame cleanup failed", exc_info=True)
            raise
        finally:
            self._lock.release()

    def _capture_jpeg_locked(self) -> tuple[bytes, dict[str, Any]]:
        with self._lock:
            if not self._preview_enabled:
                raise RuntimeError("slit/guide preview is stopped")
            session = self._require_session()

            exposure_ms = float(self.config.preview_exposure_ms)
            exposure_us = max(1, round(exposure_ms * 1000))
            session.set_control_value(ASI_GAIN, self.gain)
            session.set_control_value(ASI_OFFSET, self.offset)
            actual_exposure_us, _ = session.set_control_value(
                ASI_EXPOSURE,
                exposure_us,
            )
            session.start_exposure(dark=False)
            status = session.wait_for_exposure(
                timeout_s=max(10.0, actual_exposure_us / 1_000_000.0 + 10.0)
            )
            if status != "success":
                raise RuntimeError(f"ZWO preview exposure ended with status={status!r}")
            payload = session.read_exposure_data(
                buffer_size=self.width * self.height * 2
            )
            self._sequence += 1
            sequence = self._sequence

        image = np.frombuffer(payload, dtype="<u2").reshape(self.height, self.width)
        jpeg = self._render_jpeg(image)
        captured_at = utc_now_iso()
        meta = {
            "device_id": self.config.device_id,
            "role": self.role,
            "driver": self.config.driver,
            "model": self.descriptor.name,
            "serial": self.detected_serial or self.config.serial,
            "sequence": sequence,
            "captured_at": captured_at,
            "width": self.width,
            "height": self.height,
            "binning": self.binning,
            "exposure_ms": actual_exposure_us / 1000.0,
            "gain": self.gain,
            "offset": self.offset,
            "media_type": "image/jpeg",
        }
        with self._lock:
            self._last_capture = {k: v for k, v in meta.items() if k != "media_type"}
        return jpeg, meta

    def status(self) -> dict[str, Any]:
        # A UI heartbeat must not wait for USB nor make another USB request.
        session = self._session
        error = getattr(self.sdk, "health_error", None)
        return {
            "device_id": self.config.device_id,
            "role": self.role,
            "driver": self.config.driver,
            "model": self.descriptor.name,
            "serial": self.detected_serial or self.config.serial,
            "state": "previewing" if self._preview_enabled else "stopped",
            "preview_enabled": self._preview_enabled,
            "connected": session is not None and error is None,
            "error": error or self._last_error,
            "failed_frames": self._failed_frames,
            "sequence": self._sequence,
            "temperature_c": self._temperature_c,
            "last_capture": dict(self._last_capture) if self._last_capture else None,
        }

    def _render_jpeg(self, image: np.ndarray) -> bytes:
        # Robust percentile stretch: slit illumination is highly non-uniform,
        # and a fixed 16-bit->8-bit shift would crush either the sky
        # background or the star on the slit.
        lo, hi = np.percentile(image, (0.5, 99.5))
        if hi <= lo:
            hi = lo + 1
        scaled = np.clip((image.astype(np.float32) - lo) * (255.0 / (hi - lo)), 0, 255)
        rendered = scaled.astype(np.uint8)
        pil_image = Image.fromarray(rendered)
        longest = max(pil_image.size)
        if longest > _MAX_JPEG_EDGE:
            ratio = _MAX_JPEG_EDGE / longest
            pil_image = pil_image.resize(
                (
                    max(1, round(pil_image.size[0] * ratio)),
                    max(1, round(pil_image.size[1] * ratio)),
                )
            )
        output = io.BytesIO()
        pil_image.save(output, format="JPEG", quality=88)
        return output.getvalue()

    def _require_session(self) -> ZwoCameraSession:
        if self._session is None:
            raise RuntimeError("ZWO slit/guide camera is not connected")
        return self._session
