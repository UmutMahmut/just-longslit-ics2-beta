from fastapi.testclient import TestClient

from justls.ics.app.main import app, phase_2d8_v7_runtime_module_flags


def test_v7_setup_runtime_is_injected_by_default(monkeypatch):
    monkeypatch.delenv("JUSTLS_UI_V7_RUNTIME_ENABLED", raising=False)
    monkeypatch.delenv("JUSTLS_UI_V7_SETUP_RUNTIME_ENABLED", raising=False)

    response = TestClient(app).get("/ui/v7")

    assert response.status_code == 200
    assert "/ui-assets/v7/setup_runtime.js" in response.text


def test_v7_setup_runtime_requires_master_and_module_gate(monkeypatch):
    monkeypatch.setenv("JUSTLS_UI_V7_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("JUSTLS_UI_V7_SETUP_RUNTIME_ENABLED", "0")

    response = TestClient(app).get("/ui/v7")

    assert response.status_code == 200
    assert "/ui-assets/v7/setup_runtime.js" not in response.text


def test_v7_setup_runtime_is_injected_when_enabled(monkeypatch):
    monkeypatch.setenv("JUSTLS_UI_V7_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("JUSTLS_UI_V7_SETUP_RUNTIME_ENABLED", "1")

    response = TestClient(app).get("/ui/v7")

    assert response.status_code == 200
    assert "/ui-assets/v7/setup_runtime.js" in response.text


def test_v7_runtime_module_flags_include_setup(monkeypatch):
    monkeypatch.setenv("JUSTLS_UI_V7_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("JUSTLS_UI_V7_SETUP_RUNTIME_ENABLED", "1")

    flags = phase_2d8_v7_runtime_module_flags()

    assert flags["setup"] is True
