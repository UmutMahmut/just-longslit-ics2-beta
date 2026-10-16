from __future__ import annotations

import pytest

from justls.ics.domain.setup.instrument import InstrumentContext


def beta_platform_context() -> InstrumentContext:
    """The beta platform: 50 cm f/10 + Lhires III, 1200 l/mm, 40 um slit."""
    return InstrumentContext(
        telescope_name="50cm-beta",
        telescope_aperture_m=0.5,
        telescope_focal_length_mm=5000.0,
        spectrograph_model="Shelyak Lhires III",
        grating_lines_per_mm=1200,
        grating_micrometer_reading="12.345",
        central_wavelength_nm=656.3,
        slit_width_um=40.0,
        slit_angle_deg=0.0,
        lamp_type="Ne",
        lamp_on=False,
        declared_by="operator",
    )


def test_plate_scale_is_derived_from_focal_length_not_hardcoded() -> None:
    context = beta_platform_context()

    # f_mm * 1000 / 206265 = 5000 * 1000 / 206265 = 24.24 um/arcsec.
    assert context.slit_um_per_arcsec == pytest.approx(24.2405, rel=1e-3)
    assert context.slit_width_arcsec == pytest.approx(40.0 / 24.2405, rel=1e-3)
    assert context.telescope_focal_ratio == pytest.approx(10.0)


def test_fits_cards_carry_manual_provenance() -> None:
    cards = beta_platform_context().to_fits_cards()

    assert cards["TELESCOP"] == "50cm-beta"
    assert cards["APERTURE"] == pytest.approx(0.5)
    assert cards["FOCALLEN"] == pytest.approx(5000.0)
    assert cards["FOCRATIO"] == pytest.approx(10.0)
    assert cards["INSTRUME"] == "Shelyak Lhires III"
    assert cards["GRATING"] == "1200 l/mm"
    assert cards["GRATPOS"] == "12.345"
    assert cards["GRATSRC"] == "manual"
    assert cards["WAVCENTR"] == pytest.approx(656.3)
    assert cards["WAVSRC"] == "manual-est"
    assert cards["SLITWID"] == pytest.approx(40.0)
    assert cards["SLITWAS"] == pytest.approx(1.65, rel=1e-2)
    assert cards["SLITSRC"] == "manual"
    assert cards["LAMP"] is False
    assert cards["LAMPTYP"] == "Ne"
    assert cards["LAMPSRC"] == "manual"


def test_empty_declaration_yields_only_identity_and_lamp_cards() -> None:
    cards = InstrumentContext().to_fits_cards()

    # INSTRUME (the declared default model) and LAMP/LAMPTYP/LAMPSRC are
    # always emitted (off/none is also a declared state); everything else
    # is omitted rather than guessed.
    assert cards == {
        "INSTRUME": "Shelyak Lhires III",
        "LAMP": False,
        "LAMPTYP": "none",
        "LAMPSRC": "manual",
    }


def test_all_keywords_fit_the_8_character_fits_limit() -> None:
    for keyword in beta_platform_context().to_fits_cards():
        assert len(keyword) <= 8
        assert keyword == keyword.upper()


def test_round_trip_through_persisted_dict() -> None:
    context = beta_platform_context()
    restored = InstrumentContext.from_dict(context.to_persisted_dict())

    assert restored.to_persisted_dict() == context.to_persisted_dict()


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValueError, match="unknown instrument context fields"):
        InstrumentContext.from_dict({"wavelength_nm": 656.3})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("telescope_aperture_m", 0.0),
        ("telescope_focal_length_mm", 10.0),
        ("grating_lines_per_mm", 10),
        ("central_wavelength_nm", 50.0),
        ("central_wavelength_nm", 5000.0),
        ("slit_width_um", 0.0),
        ("slit_angle_deg", 360.0),
        ("lamp_type", "xenon-arc"),
    ],
)
def test_implausible_values_are_rejected(field: str, value) -> None:
    with pytest.raises(ValueError):
        InstrumentContext(**{field: value})


def test_stamp_records_operator_and_timestamp() -> None:
    context = InstrumentContext()
    context.stamp(declared_by="night-op")

    assert context.declared_by == "night-op"
    assert context.updated_at
    cards = context.to_fits_cards()
    assert cards["INSTDECL"] == "night-op"
    assert "INSTUPD" in cards
