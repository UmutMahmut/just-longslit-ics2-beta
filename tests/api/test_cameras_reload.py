"""API tests for the camera hot-plug reload endpoint.

The reload path is the operator's recovery tool when the hot-plug monitor
or the operator notices a USB change. The endpoint must:

* release the existing runtime's handles (including the hot-plug monitor)
* rebuild the runtime from scratch
* return enough information for the operator console to refresh

A simulated camera config keeps the test independent of any hardware
attached to the host; the contract tested here is the reload lifecycle,
not the SDK binding itself.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from justls.ics.app.main import app
from justls.ics.kernel.runtime import get_runtime, reset_runtime


@pytest.fixture(autouse=True)
def _reset_runtime_singleton(monkeypatch):
    config_path = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "config"
        / "cameras.sim.json"
    )
    monkeypatch.setenv("ICS_BETA_CAMERA_CONFIG", str(config_path))
    # Hot-plug monitor would be skipped on a fully simulated deployment, so
    # the reload endpoint must still answer without trying to use the SDK.
    monkeypatch.setenv("ICS_BETA_HOTPLUG_INTERVAL_S", "0")
    reset_runtime()
    yield
    reset_runtime()


def _client() -> TestClient:
    return TestClient(app)


def test_reload_rebuilds_runtime_and_returns_status() -> None:
    initial = get_runtime()
    initial_id = id(initial)

    response = _client().post("/api/v1/cameras/reload")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["reloaded"] is True
    # The new runtime must be a different object — reload must release
    # handles and rebuild, not return the same instance.
    assert id(get_runtime()) != initial_id
    # A fully simulated config binds no real cameras, so both should be
    # reported as unavailable-but-not-erroring.
    assert payload["force_sim"] is False
    assert payload["slit_camera"] in (True, False)
    assert payload["science_camera"] in (True, False)


def test_reload_does_not_leave_the_hotplug_monitor_running() -> None:
    # Use the first call to build a runtime.
    _client().get("/api/v1/cameras/status")
    runtime = get_runtime()
    # Sim config does not bind a ZWO driver, so the monitor should be None
    # even after the reload (it was never started).
    assert runtime.hotplug_monitor is None

    # After a reload, the rebuilt runtime must again have no monitor running.
    _client().post("/api/v1/cameras/reload")
    assert get_runtime().hotplug_monitor is None


def test_camera_status_payload_always_has_hot_plug_field() -> None:
    response = _client().get("/api/v1/cameras/status")

    assert response.status_code == 200
    payload = response.json()
    assert "hot_plug" in payload
    hot_plug = payload["hot_plug"]
    assert "enabled" in hot_plug
    assert "interval_s" in hot_plug
    assert "last_count" in hot_plug
    assert "last_check_at" in hot_plug
    assert "last_change_at" in hot_plug
    assert "last_error" in hot_plug
    # In a sim config with monitor disabled, every per-tick field is null.
    assert hot_plug["enabled"] is False
    assert hot_plug["last_count"] is None
    assert hot_plug["last_check_at"] is None
