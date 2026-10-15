import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from justls.ics.app.api.dependencies import get_setup_context_service
from justls.ics.app.main import app
from justls.ics.application.services.setup_context_service import SetupContextService
from justls.ics.application.services.setup_context_store import JsonSetupContextStore


@pytest.fixture()
def setup_context_client(tmp_path) -> Iterator[TestClient]:
    def override_setup_context_service() -> SetupContextService:
        return SetupContextService(
            store=JsonSetupContextStore(tmp_path / "setup_context.json")
        )

    app.dependency_overrides[get_setup_context_service] = override_setup_context_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_setup_context_service, None)


def test_get_setup_context_returns_default_context(setup_context_client: TestClient) -> None:
    response = setup_context_client.get("/api/v1/setup/context")

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")

    payload = response.json()
    assert payload["observers"] == ""
    assert payload["project_id"] == ""
    assert payload["pi_name"] == ""
    assert payload["support_operator"] == ""
    assert payload["root_name"] == "justls"
    assert payload["date_prefix"] == "AUTO"
    assert payload["comment"] == ""
    assert payload["next_frame_index"] == 1
    assert payload["data_directory"] == ""
    assert re.match(r"^\d{8}-0001$", payload["next_frame_token"])
    assert re.match(r"^justls_\d{8}_0001$", payload["file_stem"])
    assert re.match(r"^justls_\d{8}_0001\.fits$", payload["fits_filename"])


def test_get_setup_context_rejects_extra_response_fields_contractually(
    setup_context_client: TestClient,
) -> None:
    response = setup_context_client.get("/api/v1/setup/context")

    assert response.status_code == 200
    assert set(response.json()) == {
        "observers",
        "project_id",
        "pi_name",
        "support_operator",
        "root_name",
        "date_prefix",
        "comment",
        "next_frame_index",
        "data_directory",
        "next_frame_token",
        "file_stem",
        "fits_filename",
    }


def test_put_setup_context_persists_context(setup_context_client: TestClient) -> None:
    response = setup_context_client.put(
        "/api/v1/setup/context",
        json={
            "observers": "Observer",
            "project_id": "P-001",
            "pi_name": "PI",
            "support_operator": "Support",
            "root_name": "science",
            "date_prefix": "20260527",
            "comment": "night setup",
            "next_frame_index": 21,
            "data_directory": "/data/just",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["observers"] == "Observer"
    assert payload["project_id"] == "P-001"
    assert payload["pi_name"] == "PI"
    assert payload["support_operator"] == "Support"
    assert payload["root_name"] == "science"
    assert payload["date_prefix"] == "20260527"
    assert payload["comment"] == "night setup"
    assert payload["next_frame_index"] == 21
    assert payload["data_directory"] == "/data/just"
    assert payload["next_frame_token"] == "20260527-0021"
    assert payload["file_stem"] == "science_20260527_0021"
    assert payload["fits_filename"] == "science_20260527_0021.fits"

    get_response = setup_context_client.get("/api/v1/setup/context")
    assert get_response.status_code == 200
    assert get_response.json() == payload


def test_reload_setup_context_returns_persisted_context(setup_context_client: TestClient) -> None:
    put_response = setup_context_client.put(
        "/api/v1/setup/context",
        json={
            "observers": "Observer",
            "project_id": "P-001",
            "root_name": "science",
            "date_prefix": "20260527",
            "next_frame_index": 22,
        },
    )
    assert put_response.status_code == 200

    reload_response = setup_context_client.post("/api/v1/setup/context/reload")

    assert reload_response.status_code == 200
    payload = reload_response.json()
    assert payload["observers"] == "Observer"
    assert payload["project_id"] == "P-001"
    assert payload["root_name"] == "science"
    assert payload["next_frame_token"] == "20260527-0022"


def test_put_setup_context_rejects_invalid_root_name(
    setup_context_client: TestClient,
) -> None:
    response = setup_context_client.put(
        "/api/v1/setup/context",
        json={
            "root_name": "science run",
            "date_prefix": "20260527",
            "next_frame_index": 1,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "setup_context_validation_error"
    assert "root_name" in response.json()["detail"]["message"]

def test_put_setup_context_rejects_extra_request_fields(
    setup_context_client: TestClient,
) -> None:
    response = setup_context_client.put(
        "/api/v1/setup/context",
        json={
            "root_name": "science",
            "date_prefix": "20260527",
            "next_frame_index": 1,
            "next_frame_token": "should-not-be-accepted",
        },
    )

    assert response.status_code == 422