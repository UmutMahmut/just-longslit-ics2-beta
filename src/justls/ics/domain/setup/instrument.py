"""Instrument (telescope + spectrograph) context for FITS provenance.

The Lhires III is a fully manual instrument: slit width, grating,
micrometer wavelength setting and the comparison lamp have no electronic
readback. The values here are therefore an **attended declaration** — the
operator declares the physical state, the software validates the ranges and
stamps every FITS card with its ``manual`` provenance so nothing is ever
mistaken for a live sensor reading.

All platform-specific numbers (focal length, grating, slit width, ...) are
parameters of this model; nothing is hardcoded to a specific telescope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

_LAMP_TYPES = frozenset({"none", "Ne", "ThAr", "NeAr", "halogen", "other"})


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _optional_float(value: Any, *, name: str) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number or null") from exc


def _optional_int(value: Any, *, name: str) -> int | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer or null") from exc
    return parsed


@dataclass(slots=True)
class InstrumentContext:
    """Operator-declared telescope + spectrograph state."""

    # Telescope (drives the plate scale, e.g. slit um/arcsec = f_mm / 206.265).
    telescope_name: str = ""
    telescope_aperture_m: float | None = None
    telescope_focal_length_mm: float | None = None

    # Spectrograph.
    spectrograph_model: str = "Shelyak Lhires III"
    grating_lines_per_mm: int | None = None
    # Raw dial reading, kept verbatim ("as read") for later reduction.
    grating_micrometer_reading: str = ""
    central_wavelength_nm: float | None = None
    slit_width_um: float | None = None
    slit_angle_deg: float | None = None
    focus_position: str = ""

    # Comparison lamp (manual knob on the Lhires III).
    lamp_type: str = "none"
    lamp_on: bool = False

    # Provenance.
    declared_by: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        self.telescope_name = _clean(self.telescope_name)
        self.spectrograph_model = _clean(self.spectrograph_model)
        self.grating_micrometer_reading = _clean(self.grating_micrometer_reading)
        self.focus_position = _clean(self.focus_position)
        self.lamp_type = _clean(self.lamp_type) or "none"
        self.declared_by = _clean(self.declared_by)
        self.updated_at = _clean(self.updated_at)

        self.telescope_aperture_m = _optional_float(
            self.telescope_aperture_m, name="telescope_aperture_m"
        )
        self.telescope_focal_length_mm = _optional_float(
            self.telescope_focal_length_mm, name="telescope_focal_length_mm"
        )
        self.grating_lines_per_mm = _optional_int(
            self.grating_lines_per_mm, name="grating_lines_per_mm"
        )
        self.central_wavelength_nm = _optional_float(
            self.central_wavelength_nm, name="central_wavelength_nm"
        )
        self.slit_width_um = _optional_float(self.slit_width_um, name="slit_width_um")
        self.slit_angle_deg = _optional_float(self.slit_angle_deg, name="slit_angle_deg")

        if self.telescope_aperture_m is not None and not (0.01 <= self.telescope_aperture_m <= 30):
            raise ValueError("telescope_aperture_m is outside the plausible range 0.01–30 m")
        if self.telescope_focal_length_mm is not None and not (50 <= self.telescope_focal_length_mm <= 100000):
            raise ValueError("telescope_focal_length_mm is outside the plausible range 50–100000 mm")
        if self.grating_lines_per_mm is not None and not (50 <= self.grating_lines_per_mm <= 5000):
            raise ValueError("grating_lines_per_mm is outside the plausible range 50–5000 l/mm")
        if self.central_wavelength_nm is not None and not (200 <= self.central_wavelength_nm <= 1200):
            raise ValueError("central_wavelength_nm is outside the optical range 200–1200 nm")
        if self.slit_width_um is not None and not (1 <= self.slit_width_um <= 2000):
            raise ValueError("slit_width_um is outside the plausible range 1–2000 um")
        if self.slit_angle_deg is not None and not (0 <= self.slit_angle_deg < 360):
            raise ValueError("slit_angle_deg must be within [0, 360)")
        if self.lamp_type not in _LAMP_TYPES:
            raise ValueError(
                f"lamp_type must be one of {sorted(_LAMP_TYPES)}, got {self.lamp_type!r}"
            )
        self.lamp_on = bool(self.lamp_on)

    @property
    def telescope_focal_ratio(self) -> float | None:
        if self.telescope_aperture_m and self.telescope_focal_length_mm:
            return self.telescope_focal_length_mm / (self.telescope_aperture_m * 1000.0)
        return None

    @property
    def slit_um_per_arcsec(self) -> float | None:
        """Plate scale factor at the slit: um/arcsec = f_mm * 1000 / 206265."""
        if self.telescope_focal_length_mm:
            return self.telescope_focal_length_mm * 1000.0 / 206265.0
        return None

    @property
    def slit_width_arcsec(self) -> float | None:
        scale = self.slit_um_per_arcsec
        if self.slit_width_um is not None and scale:
            return self.slit_width_um / scale
        return None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InstrumentContext":
        known = {
            "telescope_name",
            "telescope_aperture_m",
            "telescope_focal_length_mm",
            "spectrograph_model",
            "grating_lines_per_mm",
            "grating_micrometer_reading",
            "central_wavelength_nm",
            "slit_width_um",
            "slit_angle_deg",
            "focus_position",
            "lamp_type",
            "lamp_on",
            "declared_by",
            "updated_at",
        }
        unknown = set(payload) - known
        if unknown:
            raise ValueError(f"unknown instrument context fields: {sorted(unknown)}")
        return cls(**{key: payload[key] for key in known if key in payload})

    def to_persisted_dict(self) -> dict[str, Any]:
        return {
            "telescope_name": self.telescope_name,
            "telescope_aperture_m": self.telescope_aperture_m,
            "telescope_focal_length_mm": self.telescope_focal_length_mm,
            "spectrograph_model": self.spectrograph_model,
            "grating_lines_per_mm": self.grating_lines_per_mm,
            "grating_micrometer_reading": self.grating_micrometer_reading,
            "central_wavelength_nm": self.central_wavelength_nm,
            "slit_width_um": self.slit_width_um,
            "slit_angle_deg": self.slit_angle_deg,
            "focus_position": self.focus_position,
            "lamp_type": self.lamp_type,
            "lamp_on": self.lamp_on,
            "declared_by": self.declared_by,
            "updated_at": self.updated_at,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.to_persisted_dict(),
            "telescope_focal_ratio": self.telescope_focal_ratio,
            "slit_um_per_arcsec": self.slit_um_per_arcsec,
            "slit_width_arcsec": self.slit_width_arcsec,
            "fits_cards": self.to_fits_cards(),
        }

    def stamp(self, *, declared_by: str | None = None) -> None:
        if declared_by is not None:
            self.declared_by = _clean(declared_by)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_fits_cards(self) -> dict[str, Any]:
        """FITS header cards; every value is operator-declared (`manual`).

        Keywords stay within the 8-character FITS limit. Provenance cards
        (*SRC) make it explicit that the spectrograph values are attended
        declarations, not sensor readouts.
        """
        cards: dict[str, Any] = {}
        if self.telescope_name:
            cards["TELESCOP"] = self.telescope_name
        if self.telescope_aperture_m is not None:
            cards["APERTURE"] = round(self.telescope_aperture_m, 4)
        if self.telescope_focal_length_mm is not None:
            cards["FOCALLEN"] = round(self.telescope_focal_length_mm, 2)
        ratio = self.telescope_focal_ratio
        if ratio is not None:
            cards["FOCRATIO"] = round(ratio, 3)

        if self.spectrograph_model:
            cards["INSTRUME"] = self.spectrograph_model
        if self.grating_lines_per_mm is not None:
            cards["GRATING"] = f"{self.grating_lines_per_mm} l/mm"
            cards["GRATSRC"] = "manual"
        if self.grating_micrometer_reading:
            cards["GRATPOS"] = self.grating_micrometer_reading
            cards["GRATSRC"] = "manual"
        if self.central_wavelength_nm is not None:
            cards["WAVCENTR"] = round(self.central_wavelength_nm, 2)
            cards["WAVSRC"] = "manual-est"

        if self.slit_width_um is not None:
            cards["SLITWID"] = round(self.slit_width_um, 2)
            cards["SLITSRC"] = "manual"
        width_arcsec = self.slit_width_arcsec
        if width_arcsec is not None:
            cards["SLITWAS"] = round(width_arcsec, 3)
        if self.slit_angle_deg is not None:
            cards["SLITANG"] = round(self.slit_angle_deg, 2)
            cards["SLITSRC"] = "manual"

        cards["LAMP"] = bool(self.lamp_on)
        cards["LAMPTYP"] = self.lamp_type
        cards["LAMPSRC"] = "manual"

        if self.declared_by:
            cards["INSTDECL"] = self.declared_by
        if self.updated_at:
            cards["INSTUPD"] = self.updated_at
        return {key: value for key, value in cards.items() if value is not None}
