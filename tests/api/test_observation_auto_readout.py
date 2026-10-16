from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from justls.ics.app.main import app
from justls.ics.kernel.runtime import reset_runtime


@pytest.fixture(autouse=True)
def _reset_runtime_singleton():
    reset_runtime()
    yield
    reset_runtime()


def _wait_for_state(client: TestClient, expected: str, timeout_s: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout_s
    payload: dict = {}
    while time.monotonic() < deadline:
        payload = client.get("/api/v1/observation/status").json()
        if payload.get("state") == expected:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"state never reached {expected!r}; last={payload}")


def test_exposure_completes_automatically_after_timer(
    monkeypatch,
) -> None:
    """A hardware exposure must not wait for an operator to click finish."""
    monkeypatch.setenv("JUSTLS_AUTO_READOUT_ENABLED", "1")
    client = TestClient(app)

    arm = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 0.2, "frame_type": "science"},
    )
    assert arm.json()["observation_state"] == "armed"

    start = client.post("/api/v1/observation/start")
    assert start.json()["observation_state"] == "exposing"

    payload = _wait_for_state(client, "completed")
    assert payload["last_exposure"]["result"] == "completed"
    assert payload["last_exposure"]["early_stop"] is False


def test_auto_readout_disabled_keeps_manual_control(monkeypatch) -> None:
    monkeypatch.setenv("JUSTLS_AUTO_READOUT_ENABLED", "0")
    client = TestClient(app)

    client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 0.1, "frame_type": "science"},
    )
    client.post("/api/v1/observation/start")
    time.sleep(0.4)

    payload = client.get("/api/v1/observation/status").json()
    assert payload["state"] == "exposing"

    assert client.post("/api/v1/observation/finish").json()["ok"] is True


def test_abort_cancels_pending_auto_readout(monkeypatch) -> None:
    monkeypatch.setenv("JUSTLS_AUTO_READOUT_ENABLED", "1")
    client = TestClient(app)

    client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 0.3, "frame_type": "science"},
    )
    client.post("/api/v1/observation/start")
    aborted = client.post("/api/v1/observation/abort_discard")
    assert aborted.json()["ok"] is True

    time.sleep(0.6)
    payload = client.get("/api/v1/observation/status").json()
    assert payload["state"] == "discarded"
    assert payload["last_exposure"]["result"] == "discarded"


def test_frame_can_be_saved_after_readout_on_demand() -> None:
    """Frames exposed without the save flag stay in memory and can be kept."""
    client = TestClient(app)

    client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 0.05, "frame_type": "science", "save_requested": False},
    )
    client.post("/api/v1/observation/start")
    finished = client.post("/api/v1/observation/finish").json()
    assert finished["ok"] is True

    payload = finished["details"]["payload"]
    assert payload["last_exposure"].get("file_uri") is None

    response = client.post("/api/v1/observation/save_last_frame")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True

    products = body["details"]["payload"]
    assert products["saved"] is True
    assert products["file_uri"]

    path = Path(products["file_uri"].removeprefix("file:///"))
    assert path.exists()


def test_save_last_frame_reports_already_saved_frame() -> None:
    client = TestClient(app)

    client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 0.05, "frame_type": "science", "save_requested": True},
    )
    client.post("/api/v1/observation/start")
    assert client.post("/api/v1/observation/finish").json()["ok"] is True

    body = client.post("/api/v1/observation/save_last_frame").json()
    assert body["ok"] is True
    assert body["details"]["payload"]["already_saved"] is True


def test_save_last_frame_rejects_when_no_frame_exists() -> None:
    client = TestClient(app)

    response = client.post("/api/v1/observation/save_last_frame")
    assert response.status_code == 400
    assert response.json()["ok"] is False
