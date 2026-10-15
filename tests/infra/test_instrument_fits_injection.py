from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from astropy.io import fits

from justls.ics.domain.setup.instrument import InstrumentContext
from justls.ics.infra.data_products import LocalDataProductWriter
from justls.ics.infra.instrument_context import (
    load_instrument_fits_cards,
    save_instrument_context,
)


def _write_frame(writer: LocalDataProductWriter, tmp_path: Path):
    image = np.arange(64 * 48, dtype=np.uint16).reshape(48, 64)
    return writer.write(
        image,
        obs_id="obs-test",
        exp_id="exp-test",
        frame_token="frame-test",
        frame_type="science",
        exp_time_s=1.0,
        actual_exp_time_s=1.0,
        camera_id="cam-test",
        logical_channels=("SCI",),
        started_at="2026-10-09T00:00:00+00:00",
        finished_at="2026-10-09T00:00:01+00:00",
        simulated=False,
    )


def test_writer_stamps_declared_instrument_cards_into_real_fits(tmp_path: Path) -> None:
    declaration_path = tmp_path / "instrument_context.json"
    save_instrument_context(
        declaration_path,
        InstrumentContext(
            telescope_name="50cm-beta",
            telescope_focal_length_mm=5000.0,
            grating_lines_per_mm=1200,
            slit_width_um=40.0,
            lamp_type="Ne",
            declared_by="night-op",
        ),
    )
    writer = LocalDataProductWriter(
        tmp_path / "data",
        instrument_cards_provider=lambda: load_instrument_fits_cards(
            declaration_path
        ),
    )

    products = _write_frame(writer, tmp_path)

    with fits.open(products.file_path) as hdul:
        header = hdul[0].header
        assert header["SIMULATE"] is False
        assert header["TELESCOP"] == "50cm-beta"
        assert header["FOCALLEN"] == 5000.0
        assert header["INSTRUME"] == "Shelyak Lhires III"
        assert header["GRATING"] == "1200 l/mm"
        assert header["GRATSRC"] == "manual"
        assert header["SLITWID"] == 40.0
        assert header["SLITSRC"] == "manual"
        assert header["LAMPTYP"] == "Ne"
        assert header["LAMPSRC"] == "manual"
        assert header["INSTDECL"] == "night-op"


def test_missing_declaration_file_never_blocks_capture(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.json"
    writer = LocalDataProductWriter(
        tmp_path / "data",
        instrument_cards_provider=lambda: load_instrument_fits_cards(missing),
    )

    products = _write_frame(writer, tmp_path)

    assert Path(products.file_path).is_file()
    with fits.open(products.file_path) as hdul:
        header = hdul[0].header
        assert "GRATING" not in header
        assert "TELESCOP" not in header


def test_corrupt_declaration_file_yields_no_cards_and_no_failure(
    tmp_path: Path,
) -> None:
    corrupt = tmp_path / "instrument_context.json"
    corrupt.write_text("{ not json", encoding="utf-8")
    assert load_instrument_fits_cards(corrupt) == {}

    corrupt.write_text(json.dumps({"grating_lines_per_mm": 5}), encoding="utf-8")
    assert load_instrument_fits_cards(corrupt) == {}


def test_declaration_update_lands_on_the_next_frame(tmp_path: Path) -> None:
    declaration_path = tmp_path / "instrument_context.json"
    save_instrument_context(
        declaration_path,
        InstrumentContext(grating_lines_per_mm=1200),
    )
    writer = LocalDataProductWriter(
        tmp_path / "data",
        instrument_cards_provider=lambda: load_instrument_fits_cards(
            declaration_path
        ),
    )

    # Operator swaps the grating mid-session and re-declares.
    save_instrument_context(
        declaration_path,
        InstrumentContext(grating_lines_per_mm=2400),
    )
    products = _write_frame(writer, tmp_path)

    with fits.open(products.file_path) as hdul:
        assert hdul[0].header["GRATING"] == "2400 l/mm"
