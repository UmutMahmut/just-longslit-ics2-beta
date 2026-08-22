from __future__ import annotations

import hashlib
import io
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
from PIL import Image

from justls.ics.domain.detector.frame import DetectorFrameMetadata


FITS_BLOCK_SIZE = 2880
SUPPORTED_FRAME_TYPES = frozenset({"science", "bias", "dark", "flat", "arc", "test"})
_FITS_KEYWORD = re.compile(r"^[A-Z0-9_-]{1,8}$")
_RESERVED_FITS_KEYWORDS = {
    "SIMPLE",
    "BITPIX",
    "NAXIS",
    "NAXIS1",
    "NAXIS2",
    "EXTEND",
    "BZERO",
    "BSCALE",
    "END",
}


def _safe_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return token or "unknown"


def _fits_value(value: Any) -> str:
    if isinstance(value, bool):
        return "T" if value else "F"
    if isinstance(value, str):
        return f"'{value.replace(chr(39), chr(39) * 2)}'"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("FITS floating-point values must be finite")
        return f"{value:.10G}"
    return str(value)


def _fits_card(keyword: str, value: Any | None = None) -> bytes:
    if keyword == "END":
        text = "END"
    else:
        if not _FITS_KEYWORD.fullmatch(keyword):
            raise ValueError(f"Invalid FITS keyword: {keyword!r}")
        rendered = _fits_value(value)
        text = f"{keyword:<8}= {rendered:>20}"
    if len(text) > 80:
        raise ValueError(f"FITS card {keyword!r} exceeds 80 characters")
    try:
        return text.ljust(80).encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(f"FITS card {keyword!r} must contain ASCII text") from exc


def _pad_fits_block(payload: bytes, *, pad_byte: bytes) -> bytes:
    remainder = len(payload) % FITS_BLOCK_SIZE
    if remainder == 0:
        return payload
    return payload + pad_byte * (FITS_BLOCK_SIZE - remainder)


def build_fits_bytes(image: np.ndarray, cards: dict[str, Any]) -> bytes:
    pixels = np.asarray(image, dtype=np.uint16)
    if pixels.ndim != 2:
        raise ValueError("FITS writer expects a two-dimensional monochrome image")

    conflicts = _RESERVED_FITS_KEYWORDS.intersection(cards)
    if conflicts:
        raise ValueError(
            "FITS cards cannot override structural keywords: "
            + ", ".join(sorted(conflicts))
        )

    required_cards = [
        ("SIMPLE", True),
        ("BITPIX", 16),
        ("NAXIS", 2),
        ("NAXIS1", int(pixels.shape[1])),
        ("NAXIS2", int(pixels.shape[0])),
        ("EXTEND", True),
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


def build_science_fits_cards(
    *,
    obs_id: str,
    exp_id: str,
    frame_type: str,
    requested_exp_time_s: float,
    actual_exp_time_s: float | None,
    camera_id: str,
    logical_channels: tuple[str, ...],
    started_at: str,
    finished_at: str,
    simulated: bool,
    detector_metadata: DetectorFrameMetadata | dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_frame_type = frame_type.strip().lower()
    if normalized_frame_type not in SUPPORTED_FRAME_TYPES:
        raise ValueError(f"Unsupported FITS frame type: {frame_type!r}")

    metadata = (
        DetectorFrameMetadata.model_validate(detector_metadata)
        if detector_metadata is not None
        else None
    )
    cards: dict[str, Any] = {
        "OBS_ID": obs_id,
        "EXP_ID": exp_id,
        "FRAMETYP": normalized_frame_type.upper(),
        "EXPREQ": float(requested_exp_time_s),
        "EXPTIME": float(
            requested_exp_time_s
            if actual_exp_time_s is None
            else actual_exp_time_s
        ),
        "DATE-OBS": started_at,
        "DATE-END": finished_at,
        "CAMERA": camera_id,
        "SHARED": len(logical_channels) > 1,
        "CHANNELS": ",".join(logical_channels),
        "SAVEREQ": True,
        "SIMULATE": simulated,
    }
    if metadata is not None:
        cards.update(metadata.to_fits_cards())
    return {key: value for key, value in cards.items() if value is not None}


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
    quicklook_checksum: str
    file_size_bytes: int
    quicklook_size_bytes: int
    fits_header_cards: dict[str, Any]
    simulated: bool

    def to_result_fragment(self) -> dict[str, Any]:
        return {
            "file_uri": self.file_uri,
            "quicklook_uri": self.quicklook_uri,
            "file_path": self.file_path,
            "quicklook_path": self.quicklook_path,
            "checksum": self.checksum,
            "quicklook_checksum": self.quicklook_checksum,
            "file_size_bytes": self.file_size_bytes,
            "quicklook_size_bytes": self.quicklook_size_bytes,
            "fits_header_cards": dict(self.fits_header_cards),
            "exists": True,
            "simulated": self.simulated,
        }


def _write_synced_temp(destination: Path, payload: bytes) -> Path:
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return temporary


def _publish_pair_no_overwrite(
    *,
    fits_path: Path,
    fits_bytes: bytes,
    quicklook_path: Path,
    quicklook_bytes: bytes,
) -> None:
    for destination in (fits_path, quicklook_path):
        if destination.exists():
            raise FileExistsError(f"Refusing to overwrite data product: {destination}")

    fits_tmp: Path | None = None
    quicklook_tmp: Path | None = None
    published: list[Path] = []
    try:
        fits_tmp = _write_synced_temp(fits_path, fits_bytes)
        quicklook_tmp = _write_synced_temp(quicklook_path, quicklook_bytes)

        # Publish the optional derivative first and the authoritative FITS last.
        # Hard links make each destination appear atomically and fail if a racing
        # writer has already claimed the name.
        os.link(quicklook_tmp, quicklook_path)
        published.append(quicklook_path)
        os.link(fits_tmp, fits_path)
        published.append(fits_path)
    except Exception:
        for destination in reversed(published):
            destination.unlink(missing_ok=True)
        raise
    finally:
        if fits_tmp is not None:
            fits_tmp.unlink(missing_ok=True)
        if quicklook_tmp is not None:
            quicklook_tmp.unlink(missing_ok=True)


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
        actual_exp_time_s: float | None,
        camera_id: str,
        logical_channels: tuple[str, ...],
        started_at: str,
        finished_at: str,
        detector_metadata: DetectorFrameMetadata | dict[str, Any] | None = None,
        simulated: bool = True,
    ) -> WrittenDataProducts:
        date_path = datetime.now(timezone.utc).strftime("%Y%m%d")
        output_dir = self.data_root / date_path / _safe_token(obs_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        stem = f"{_safe_token(exp_id)}-{_safe_token(frame_token)}"
        fits_path = output_dir / f"{stem}.fits"
        quicklook_path = output_dir / f"{stem}-quicklook.png"

        metadata = (
            DetectorFrameMetadata.model_validate(detector_metadata)
            if detector_metadata is not None
            else None
        )
        if metadata is not None and (
            metadata.width != int(image.shape[1])
            or metadata.height != int(image.shape[0])
        ):
            raise ValueError(
                "Detector metadata dimensions do not match the raw frame: "
                f"metadata={metadata.width}x{metadata.height}, "
                f"frame={image.shape[1]}x{image.shape[0]}"
            )
        fits_header_cards = build_science_fits_cards(
            obs_id=obs_id,
            exp_id=exp_id,
            frame_type=frame_type,
            requested_exp_time_s=exp_time_s,
            actual_exp_time_s=actual_exp_time_s,
            camera_id=camera_id,
            logical_channels=logical_channels,
            started_at=started_at,
            finished_at=finished_at,
            simulated=simulated,
            detector_metadata=metadata,
        )
        fits_bytes = build_fits_bytes(image, fits_header_cards)
        quicklook_bytes = render_quicklook_png(image)

        _publish_pair_no_overwrite(
            fits_path=fits_path,
            fits_bytes=fits_bytes,
            quicklook_path=quicklook_path,
            quicklook_bytes=quicklook_bytes,
        )

        return WrittenDataProducts(
            file_uri=fits_path.resolve().as_uri(),
            quicklook_uri=quicklook_path.resolve().as_uri(),
            file_path=str(fits_path.resolve()),
            quicklook_path=str(quicklook_path.resolve()),
            checksum=hashlib.sha256(fits_bytes).hexdigest(),
            quicklook_checksum=hashlib.sha256(quicklook_bytes).hexdigest(),
            file_size_bytes=len(fits_bytes),
            quicklook_size_bytes=len(quicklook_bytes),
            fits_header_cards=fits_header_cards,
            simulated=simulated,
        )
