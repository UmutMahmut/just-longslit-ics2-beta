from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DetectorFrameMetadata(BaseModel):
    """Vendor-neutral detector metadata captured with one raw frame."""

    model_config = ConfigDict(extra="forbid")

    manufacturer: str | None = None
    model: str | None = None
    serial: str | None = None
    width: int = Field(..., gt=0)
    height: int = Field(..., gt=0)
    pixel_format: str = Field(..., min_length=1)
    sensor_bit_depth: int = Field(..., ge=1, le=32)
    bayer_pattern: Literal["RGGB", "BGGR", "GRBG", "GBRG"] | None = None
    bin_x: int = Field(default=1, ge=1)
    bin_y: int = Field(default=1, ge=1)
    gain: float | None = None
    offset: float | None = None
    detector_temperature_c: float | None = None
    cooler_enabled: bool | None = None
    cooler_target_c: float | None = None
    cooler_power_pct: float | None = Field(default=None, ge=0, le=100)

    def to_fits_cards(self) -> dict[str, str | int | float | bool | None]:
        return {
            "DETMANUF": self.manufacturer,
            "DETMODEL": self.model,
            "DETSER": self.serial,
            "COLORTYP": self.pixel_format,
            "BITDEPTH": self.sensor_bit_depth,
            "BAYERPAT": self.bayer_pattern,
            "XBINNING": self.bin_x,
            "YBINNING": self.bin_y,
            "GAIN": self.gain,
            "OFFSET": self.offset,
            "CCD-TEMP": self.detector_temperature_c,
            "COOLER": self.cooler_enabled,
            "SET-TEMP": self.cooler_target_c,
            "COOLPOWR": self.cooler_power_pct,
        }
