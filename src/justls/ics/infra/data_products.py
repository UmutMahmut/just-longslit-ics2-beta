from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


FITS_BLOCK_SIZE = 2880


def _safe_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return token or "unknown"


def _fits_value(value: Any) -> str:
    if isinstance(value, bool):
        return "T" if value else "F"
    if isinstance(value, str):
        return f"'{value.replace(chr(39), chr(39) * 2)}'"
    if isinstance(value, float):
        return f"{value:.10G}"
    return str(value)


def _fits_card(keyword: str, value: Any | None = None) -> bytes:
    if keyword == "END":
        text = "END"
    else:
        rendered = _fits_value(value)
        text = f"{keyword[:8]:<8}= {rendered:>20}"
    return text[:80].ljust(80).encode("ascii", errors="replace")


def _pad_fits_block(payload: bytes, *, pad_byte: bytes) -> bytes:
    remainder = len(payload) % FITS_BLOCK_SIZE
    if remainder == 0:
        return payload
    return payload + pad_byte * (FITS_BLOCK_SIZE - remainder)


def build_fits_bytes(image: np.ndarray, cards: dict[str, Any]) -> bytes:
    pixels = np.asarray(image, dtype=np.uint16)
    if pixels.ndim != 2:
        raise ValueError("FITS writer expects a two-dimensional monochrome image")

    required_cards = [
        ("SIMPLE", True),
        ("BITPIX", 16),
        ("NAXIS", 2),
        ("NAXIS1", int(pixels.shape[1])),
        ("NAXIS2", int(pixels.shape[0])),
        ("BZERO", 32768),
        ("BSCALE", 1),
    ]
    header = b"".join(_fits_card(key, value) for key, value in required_cards)
    for key, value in cards.items():
        if value is not None:
            header += _fits_card(key, value)
    header += _fits_card("END")
    header = _pad_fits_block(header, pad_byte=b" ")

    signed_storage = (pixels.astype(np.int32) - 32768).astype(">i2")
    data = _pad_fits_block(signed_storage.tobytes(order="C"), pad_byte=b"\0")
    return header + data


def render_quicklook_png(image: np.ndarray) -> bytes:
    pixels = np.asarray(image, dtype=np.float32)
    low, high = np.percentile(pixels, (1.0, 99.5))
    if high <= low:
        high = low + 1.0
    scaled = np.clip((pixels - low) * 255.0 / (high - low), 0, 255).astype(
        np.uint8
    )
    output = io.BytesIO()
    Image.fromarray(scaled).save(output, format="PNG", optimize=True)
    return output.getvalue()


@dataclass(frozen=True, slots=True)
class WrittenDataProducts:
    file_uri: str
    quicklook_uri: str
    file_path: str
    quicklook_path: str
    checksum: str

    def to_result_fragment(self) -> dict[str, Any]:
        return {
            "file_uri": self.file_uri,
            "quicklook_uri": self.quicklook_uri,
            "file_path": self.file_path,
            "quicklook_path": self.quicklook_path,
            "checksum": self.checksum,
            "exists": True,
            "simulated": True,
        }


class LocalDataProductWriter:
    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root.resolve()

    def write(
        self,
        image: np.ndarray,
        *,
        obs_id: str,
        exp_id: str,
        frame_token: str,
        frame_type: str,
        exp_time_s: float,
        camera_id: str,
        logical_channels: tuple[str, ...],
        started_at: str,
        finished_at: str,
    ) -> WrittenDataProducts:
        date_path = datetime.now(timezone.utc).strftime("%Y%m%d")
        output_dir = self.data_root / date_path / _safe_token(obs_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        stem = f"{_safe_token(exp_id)}-{_safe_token(frame_token)}"
        fits_path = output_dir / f"{stem}.fits"
        quicklook_path = output_dir / f"{stem}-quicklook.png"

        fits_bytes = build_fits_bytes(
            image,
            {
                "OBS_ID": obs_id,
                "EXP_ID": exp_id,
                "FRAMETYP": frame_type,
                "EXPTIME": float(exp_time_s),
                "DATE-OBS": started_at,
                "DATE-END": finished_at,
                "CAMERA": camera_id,
                "SHARED": True,
                "CHANNELS": ",".join(logical_channels),
                "SIMULATE": True,
            },
        )
        quicklook_bytes = render_quicklook_png(image)

        fits_tmp = fits_path.with_suffix(".fits.tmp")
        quicklook_tmp = quicklook_path.with_suffix(".png.tmp")
        fits_tmp.write_bytes(fits_bytes)
        quicklook_tmp.write_bytes(quicklook_bytes)
        fits_tmp.replace(fits_path)
        quicklook_tmp.replace(quicklook_path)

        return WrittenDataProducts(
            file_uri=fits_path.resolve().as_uri(),
            quicklook_uri=quicklook_path.resolve().as_uri(),
            file_path=str(fits_path.resolve()),
            quicklook_path=str(quicklook_path.resolve()),
            checksum=hashlib.sha256(fits_bytes).hexdigest(),
        )
