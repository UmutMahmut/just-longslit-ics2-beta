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


def test_save_last_frame_rejected_after_abort() -> None:
    """A discarded exposure must not be savable afterwards."""
    client = TestClient(app)

    client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 0.05, "frame_type": "science", "save_requested": False},
    )
    client.post("/api/v1/observation/start")
    assert client.post("/api/v1/observation/finish").json()["ok"] is True

    # A second exposure, this one aborted.
    client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 5.0, "frame_type": "science", "save_requested": True},
    )
    client.post("/api/v1/observation/start")
    assert client.post("/api/v1/observation/abort_discard").json()["ok"] is True

    response = client.post("/api/v1/observation/save_last_frame")
    assert response.status_code == 400
    assert response.json()["ok"] is False
