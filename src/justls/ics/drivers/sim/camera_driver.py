from __future__ import annotations

import io
from datetime import datetime, timezone
from hashlib import sha256
from threading import RLock
from typing import Any

import numpy as np
from PIL import Image

from justls.ics.infra.camera_config import CameraDeviceConfig


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SimPreviewCameraDriver:
    """Continuous-preview simulator used for the slit/guide camera role."""

    def __init__(self, config: CameraDeviceConfig, *, role: str = "slit") -> None:
        self.config = config
        self.role = role
        self._lock = RLock()
        self._sequence = 0
        self._preview_enabled = True

    def start_preview(self) -> dict[str, Any]:
        with self._lock:
            self._preview_enabled = True
            return self.status()

    def stop_preview(self) -> dict[str, Any]:
        with self._lock:
            self._preview_enabled = False
            return self.status()

    def capture_jpeg(self) -> tuple[bytes, dict[str, Any]]:
        with self._lock:
            if not self._preview_enabled:
                raise RuntimeError("slit/guide preview is stopped")
            self._sequence += 1
            sequence = self._sequence
        height, width = self.config.height, self.config.width
        rng = np.random.default_rng(sequence)
        image = rng.normal(18.0, 3.0, size=(height, width))

        y, x = np.mgrid[:height, :width]
        star_x = width * (0.47 + 0.015 * np.sin(sequence / 4.0))
        star_y = height * (0.50 + 0.01 * np.cos(sequence / 5.0))
        halo = 205.0 * np.exp(
            -(
                ((x - star_x) ** 2) / (2 * (width * 0.025) ** 2)
                + ((y - star_y) ** 2) / (2 * (height * 0.025) ** 2)
            )
        )
        image += halo

        slit_half_width = max(1, height // 160)
        slit_center = height // 2
        image[
            slit_center - slit_half_width : slit_center + slit_half_width + 1,
            :,
        ] *= 0.12
        image[:, width // 2 - 1 : width // 2 + 1] += 35

        rendered = np.clip(image, 0, 255).astype(np.uint8)
        output = io.BytesIO()
        Image.fromarray(rendered).save(output, format="JPEG", quality=88)
        captured_at = utc_now_iso()
        return output.getvalue(), {
            "device_id": self.config.device_id,
            "role": self.role,
            "driver": self.config.driver,
            "sequence": sequence,
            "captured_at": captured_at,
            "width": width,
            "height": height,
            "media_type": "image/jpeg",
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "device_id": self.config.device_id,
                "role": self.role,
                "driver": self.config.driver,
                "model": self.config.model,
                "serial": self.config.serial,
                "state": "previewing" if self._preview_enabled else "stopped",
                "preview_enabled": self._preview_enabled,
                "sequence": self._sequence,
            }


def synthetic_spectrum(
    *,
    width: int,
    height: int,
    seed_text: str,
) -> np.ndarray:
    seed = int.from_bytes(sha256(seed_text.encode("utf-8")).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[:height, :width]

    continuum = 1700 + 700 * (x / max(width - 1, 1))
    spatial = np.exp(-((y - height * 0.51) ** 2) / (2 * (height * 0.07) ** 2))
    signal = continuum * (0.22 + 2.8 * spatial)

    for center, strength, sigma in (
        (0.18, 8000, 0.005),
        (0.38, 5200, 0.008),
        (0.63, 10500, 0.004),
        (0.82, 6400, 0.006),
    ):
        line = strength * np.exp(
            -((x - width * center) ** 2) / (2 * (width * sigma) ** 2)
        )
        signal += line * (0.35 + 1.8 * spatial)

    image = signal + rng.normal(0, 75, size=(height, width)) + 480
    return np.clip(image, 0, 65535).astype(np.uint16)
