from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import pytest
from fastapi.testclient import TestClient

from justls.ics.app.main import app
from justls.ics.infra.output_location import load_output_location, load_recent_roots
from justls.ics.kernel.runtime import get_runtime, reset_runtime


@pytest.fixture(autouse=True)
def _reset_runtime_singleton():
    reset_runtime()
    yield
    reset_runtime()


@pytest.fixture
def _isolated_state(tmp_path, monkeypatch):
    """Keep the persisted selection out of the repository's .justls/."""
    state_file = tmp_path / "state" / "output_location.json"
    monkeypatch.setenv("JUSTLS_OUTPUT_LOCATION_PATH", str(state_file))
    return state_file


def _client() -> TestClient:
    return TestClient(app)


def _local_path(uri: str) -> Path:
    return Path(url2pathname(urlparse(uri).path))


def test_output_location_reports_the_configured_default() -> None:
    response = _client().get("/api/v1/system/output-location")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_root"]
    assert isinstance(payload["exists"], bool)
    assert isinstance(payload["writable"], bool)
    assert payload["message"]


def test_output_location_put_applies_live_and_persists(
    _isolated_state: Path,
    tmp_path: Path,
) -> None:
    target = tmp_path / "nights" / "20261014"

    response = _client().put(
        "/api/v1/system/output-location",
        json={"data_root": str(target)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_root"] == str(target.resolve())
    assert payload["exists"] is True
    assert payload["writable"] is True
    # The directory is created eagerly so a typo is caught now, not at readout.
    assert target.is_dir()

    runtime = get_runtime()
    assert runtime.data_root == str(target.resolve())
    # The writer is the thing that actually publishes FITS files; moving only
    # the runtime pointer would leave frames in the old folder.
    assert str(runtime.detector.adapter.writer.data_root) == str(target.resolve())

    assert load_output_location(_isolated_state) == str(target.resolve())
    assert (
        _client().get("/api/v1/system/output-location").json()["data_root"]
        == str(target.resolve())
    )


def test_output_location_put_moves_the_next_saved_frame(
    _isolated_state: Path,
    tmp_path: Path,
) -> None:
    """End-to-end: the frame written after the change lands in the new root."""
    client = _client()
    target = tmp_path / "moved"

    assert client.put(
        "/api/v1/system/output-location", json={"data_root": str(target)}
    ).status_code == 200

    client.post(
        "/api/v1/observation/arm",
        json={"exp_time_s": 0.05, "frame_type": "science", "save_requested": True},
    )
    client.post("/api/v1/observation/start")
    finished = client.post("/api/v1/observation/finish").json()

    record = finished["details"]["payload"]["latest_exposure_record"]
    fits_path = _local_path(record["primary_data_product"]["uri"])

    assert fits_path.exists()
    assert target.resolve() in fits_path.parents


def test_output_location_put_rejects_blank_value(_isolated_state: Path) -> None:
    response = _client().put(
        "/api/v1/system/output-location", json={"data_root": "   "}
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "output_location_invalid"
    assert _isolated_state.exists() is False


def test_output_location_put_rejects_a_regular_file(
    _isolated_state: Path,
    tmp_path: Path,
) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("occupied", encoding="utf-8")

    response = _client().put(
        "/api/v1/system/output-location", json={"data_root": str(blocker)}
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "output_location_invalid"


def test_output_location_put_rejects_empty_body() -> None:
    response = _client().put("/api/v1/system/output-location", json={"data_root": ""})

    assert response.status_code == 422


def test_output_location_recent_roots_promote_and_dedupe(
    _isolated_state: Path,
    tmp_path: Path,
) -> None:
    """Each Apply pushes the path to the head of the recent list and dedupes."""
    client = _client()
    first = tmp_path / "night-1"
    second = tmp_path / "night-2"
    third = tmp_path / "night-3"

    for target in (first, second, third):
        assert client.put(
            "/api/v1/system/output-location", json={"data_root": str(target)}
        ).status_code == 200

    # Going back to the second path promotes it; the order should be
    # [second, third, first] (the current selection always leads).
    assert client.put(
        "/api/v1/system/output-location", json={"data_root": str(second)}
    ).status_code == 200

    payload = client.get("/api/v1/system/output-location").json()
    assert payload["data_root"] == str(second.resolve())
    recent = payload["recent_roots"]
    assert recent[0] == str(second.resolve())
    assert str(third.resolve()) in recent
    assert str(first.resolve()) in recent
    # No duplicates and current root only at the head.
    assert len(recent) == len(set(recent))
    assert recent.count(str(second.resolve())) == 1

    on_disk = load_recent_roots(_isolated_state)
    assert on_disk == recent
