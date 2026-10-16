from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class InstrumentContextUpdateReq(BaseModel):
    """Attended declaration of telescope + spectrograph state.

    All fields are optional so the operator can update a single knob (e.g.
    the grating micrometer reading) without resending everything; omitted
    fields fall back to the declared defaults, so partial updates should be
    done via GET -> modify -> PUT.
    """

    model_config = ConfigDict(extra="forbid")

    telescope_name: str = ""
    telescope_aperture_m: float | None = None
    telescope_focal_length_mm: float | None = None

    spectrograph_model: str = "Shelyak Lhires III"
    grating_lines_per_mm: int | None = None
    grating_micrometer_reading: str = ""
    central_wavelength_nm: float | None = None
    slit_width_um: float | None = None
    slit_angle_deg: float | None = None
    focus_position: str = ""

    lamp_type: str = "none"
    lamp_on: bool = False

    declared_by: str = ""


class InstrumentContextResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    telescope_name: str = ""
    telescope_aperture_m: float | None = None
    telescope_focal_length_mm: float | None = None
    telescope_focal_ratio: float | None = None

    spectrograph_model: str = ""
    grating_lines_per_mm: int | None = None
    grating_micrometer_reading: str = ""
    central_wavelength_nm: float | None = None
    slit_width_um: float | None = None
    slit_width_arcsec: float | None = None
    slit_angle_deg: float | None = None
    slit_um_per_arcsec: float | None = None
    focus_position: str = ""

    lamp_type: str = "none"
    lamp_on: bool = False

    declared_by: str = ""
    updated_at: str = ""
    fits_cards: dict[str, Any] = {}
