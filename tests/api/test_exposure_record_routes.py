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


def _payload(data: dict) -> dict:
    assert data["ok"] is True
    return data["details"]["payload"]


def test_observation_finish_returns_latest_exposure_record() -> None:
    client = TestClient(app)

    arm = client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 5.0, "frame_type": "science"},
    )
    assert arm.status_code == 200

    start = client.post("/api/v1/observation/start")
    assert start.status_code == 200

    finish = client.post("/api/v1/observation/finish")
    assert finish.status_code == 200
    payload = _payload(finish.json())

    record = payload["latest_exposure_record"]
    assert record["state"] == "completed"
    assert record["data_product_state"] == "available"
    assert record["primary_data_product"]["exists"] is True
    assert record["primary_data_product"]["simulated"] is True
    assert record["primary_data_product"]["uri"].startswith("file:///")
    assert record["quicklook"]["exists"] is True
    assert record["quicklook"]["uri"].startswith("file:///")
    assert record["logical_channels"] == ["B", "G", "R"]
    assert record["shared_capture_id"].startswith("frame-")
    assert payload["observation_meta"]["exposure_record"]["record_id"] == record["record_id"]


def test_status_full_exposes_latest_exposure_record_after_completion() -> None:
    client = TestClient(app)

    assert client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 5.0, "frame_type": "science"},
    ).status_code == 200
    assert client.post("/api/v1/observation/start").status_code == 200
    assert client.post("/api/v1/observation/finish").status_code == 200

    status = client.get("/api/v1/status/full")
    assert status.status_code == 200
    record = status.json()["observation"]["latest_exposure_record"]

    assert record["state"] == "completed"
    assert record["data_product_state"] == "available"
    assert record["primary_data_product"]["exists"] is True
    assert record["fits_header"]["cards"]["SIMULATE"] is True
    assert record["fits_header"]["cards"]["SHARED"] is True
    assert record["fits_header"]["cards"]["CHANNELS"] == "B,G,R"


def test_abort_discard_returns_record_without_data_product() -> None:
    client = TestClient(app)

    assert client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 5.0, "frame_type": "test"},
    ).status_code == 200

    abort = client.post("/api/v1/observation/abort_discard")
    assert abort.status_code == 200
    payload = _payload(abort.json())
    record = payload["latest_exposure_record"]

    assert record["state"] == "discarded"
    assert record["data_product_state"] == "not_created"
    assert record["primary_data_product"]["exists"] is False
    assert record["primary_data_product"]["uri"] is None
