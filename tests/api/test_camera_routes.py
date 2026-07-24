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


def test_camera_status_describes_replaceable_devices_and_shared_bridge() -> None:
    response = TestClient(app).get("/api/v1/cameras/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile_name"] == "campus-beta-sim"
    assert payload["science_camera"]["device_id"] == "science-camera-01"
    assert payload["science_camera"]["model"] is None
    assert payload["slit_camera"]["device_id"] == "slit-camera-01"
    assert payload["bridge"] == {
        "physical_camera_id": "science-camera-01",
        "logical_channels": ["B", "G", "R"],
        "shared_capture": True,
    }


def test_bgr_routes_share_one_physical_camera_preview() -> None:
    client = TestClient(app)
    responses = [client.get(f"/camera/{channel}/latest.jpg") for channel in "bgr"]

    assert all(response.status_code == 200 for response in responses)
    assert all(response.headers["content-type"] == "image/png" for response in responses)
    assert len({response.content for response in responses}) == 1
    assert {
        response.headers["x-ics-physical-camera"] for response in responses
    } == {"science-camera-01"}
    assert {
        response.headers["x-ics-logical-channel"] for response in responses
    } == {"B", "G", "R"}
    assert all(
        response.headers["x-ics-shared-capture"] == "true"
        for response in responses
    )


def test_slit_camera_route_returns_independent_live_jpeg_frames() -> None:
    client = TestClient(app)
    first = client.get("/camera/slit/latest.jpg")
    second = client.get("/camera/slit/latest.jpg")

    assert first.status_code == 200
    assert first.headers["content-type"] == "image/jpeg"
    assert first.headers["x-ics-camera-role"] == "slit"
    assert first.headers["x-ics-camera-id"] == "slit-camera-01"
    assert first.content.startswith(b"\xff\xd8")
    assert first.content != second.content
    assert int(second.headers["x-ics-frame-sequence"]) == (
        int(first.headers["x-ics-frame-sequence"]) + 1
    )
