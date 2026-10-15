from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from justls.ics.app.api.dependencies import get_instrument_context_service
from justls.ics.app.main import app
from justls.ics.application.services.instrument_context_service import (
    InstrumentContextService,
)


@pytest.fixture()
def instrument_client(tmp_path) -> Iterator[TestClient]:
    def override_service() -> InstrumentContextService:
        return InstrumentContextService(path=tmp_path / "instrument_context.json")

    app.dependency_overrides[get_instrument_context_service] = override_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_instrument_context_service, None)


def test_get_returns_empty_declaration_by_default(
    instrument_client: TestClient,
) -> None:
    response = instrument_client.get("/api/v1/instrument/context")

    assert response.status_code == 200
    payload = response.json()
    assert payload["spectrograph_model"] == "Shelyak Lhires III"
    assert payload["grating_lines_per_mm"] is None
    assert payload["lamp_type"] == "none"
    assert payload["lamp_on"] is False
    assert payload["fits_cards"] == {
        "INSTRUME": "Shelyak Lhires III",
        "LAMP": False,
        "LAMPTYP": "none",
        "LAMPSRC": "manual",
    }


def test_put_persists_declaration_and_stamps_provenance(
    instrument_client: TestClient,
) -> None:
    response = instrument_client.put(
        "/api/v1/instrument/context",
        json={
            "telescope_name": "50cm-beta",
            "telescope_aperture_m": 0.5,
            "telescope_focal_length_mm": 5000.0,
            "grating_lines_per_mm": 1200,
            "grating_micrometer_reading": "12.345",
            "central_wavelength_nm": 656.3,
            "slit_width_um": 40.0,
            "lamp_type": "Ne",
            "declared_by": "night-op",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["grating_lines_per_mm"] == 1200
    assert payload["declared_by"] == "night-op"
    assert payload["updated_at"]
    assert payload["telescope_focal_ratio"] == pytest.approx(10.0)
    assert payload["slit_um_per_arcsec"] == pytest.approx(24.2405, rel=1e-3)
    assert payload["fits_cards"]["GRATING"] == "1200 l/mm"
    assert payload["fits_cards"]["GRATSRC"] == "manual"

    reloaded = instrument_client.get("/api/v1/instrument/context")
    assert reloaded.status_code == 200
    assert reloaded.json()["grating_lines_per_mm"] == 1200
    assert reloaded.json()["slit_width_um"] == 40.0


def test_put_rejects_implausible_values(instrument_client: TestClient) -> None:
    response = instrument_client.put(
        "/api/v1/instrument/context",
        json={"grating_lines_per_mm": 10},
    )

    assert response.status_code == 422
    assert "grating" in response.text


def test_put_rejects_unknown_fields(instrument_client: TestClient) -> None:
    response = instrument_client.put(
        "/api/v1/instrument/context",
        json={"grating_lines_per_mm": 1200, "wavelength_nm": 656.3},
    )

    assert response.status_code == 422
