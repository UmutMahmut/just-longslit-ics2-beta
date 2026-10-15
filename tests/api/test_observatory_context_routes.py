from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from justls.ics.app.main import app
from justls.ics.kernel.runtime import reset_runtime


@pytest.fixture(autouse=True)
def _reset_runtime_singleton():
    reset_runtime()
    yield
    reset_runtime()


def test_observatory_context_is_read_only_and_unavailable_by_default() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/observatory/context")
    assert response.status_code == 200
    data = response.json()

    assert data["source"] == "ics-local-placeholder"
    assert data["run_mode"] == "sim"
    assert data["writable"] is False
    assert data["target"]["target_name"] is None
    assert data["ocs"]["state"] == "unavailable"
    assert data["tcs"]["state"] == "unavailable"
    assert data["telescope"]["connected"] is False
    assert "not implemented" in data["ocs"]["message"]


def test_observatory_context_has_no_write_route() -> None:
    client = TestClient(app)

    response = client.post("/api/v1/observatory/context", json={})
    assert response.status_code == 405


def test_status_full_includes_observatory_context() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/status/full")
    assert response.status_code == 200
    observatory = response.json()["observatory"]

    assert observatory["writable"] is False
    assert observatory["tcs"]["state"] == "unavailable"
    assert observatory["weather"]["state"] == "unavailable"

