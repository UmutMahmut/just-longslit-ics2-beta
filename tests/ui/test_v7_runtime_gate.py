from fastapi.testclient import TestClient

from justls.ics.app.main import app


def test_v7_runtime_scripts_inject_operator_workflow_by_default(monkeypatch):
    monkeypatch.delenv("JUSTLS_UI_V7_RUNTIME_ENABLED", raising=False)
    monkeypatch.delenv("JUSTLS_UI_V7_RUNTIME_STATUS_ENABLED", raising=False)
    monkeypatch.delenv("JUSTLS_UI_V7_SETUP_RUNTIME_ENABLED", raising=False)
    monkeypatch.delenv("JUSTLS_UI_V7_INSTRUMENT_RUNTIME_ENABLED", raising=False)
    monkeypatch.delenv("JUSTLS_UI_V7_PRESET_RUNTIME_ENABLED", raising=False)
    monkeypatch.delenv("JUSTLS_UI_V7_OBSERVE_RUNTIME_ENABLED", raising=False)
    monkeypatch.delenv("JUSTLS_UI_V7_OBSERVE_GUARD_ENABLED", raising=False)
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    switches = response.json()["ui_safety_switches"]

    assert switches["phase2d8_v7_runtime_enabled"] is True
    assert switches["phase2d8_v7_runtime_modules"] == {
        "status": True,
        "setup": True,
        "instrument": True,
        "presets": True,
        "observe": True,
        "observe_guard": True,
    }

    response = client.get("/ui/v7")
    assert response.status_code == 200
    assert "/ui-assets/v7/runtime_status.js" in response.text
    assert "/ui-assets/v7/observe_runtime.js" in response.text
    assert "/ui-assets/v7/observe_guard.js" in response.text
    assert "/ui-assets/v7/setup_runtime.js" in response.text
    assert "/ui-assets/v7/instrument_runtime.js" in response.text
    assert "/ui-assets/v7/preset_runtime.js" in response.text
    assert "/ui-assets/v7/sequence_runtime.js" in response.text


def test_v7_runtime_master_gate_can_disable_all_runtime_modules(monkeypatch):
    monkeypatch.setenv("JUSTLS_UI_V7_RUNTIME_ENABLED", "0")
    monkeypatch.delenv("JUSTLS_UI_V7_RUNTIME_STATUS_ENABLED", raising=False)
    monkeypatch.delenv("JUSTLS_UI_V7_SETUP_RUNTIME_ENABLED", raising=False)
    monkeypatch.delenv("JUSTLS_UI_V7_INSTRUMENT_RUNTIME_ENABLED", raising=False)
    monkeypatch.delenv("JUSTLS_UI_V7_PRESET_RUNTIME_ENABLED", raising=False)
    monkeypatch.delenv("JUSTLS_UI_V7_OBSERVE_RUNTIME_ENABLED", raising=False)
    monkeypatch.delenv("JUSTLS_UI_V7_OBSERVE_GUARD_ENABLED", raising=False)
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    switches = response.json()["ui_safety_switches"]

    assert switches["phase2d8_v7_runtime_enabled"] is False
    assert switches["phase2d8_v7_runtime_modules"] == {
        "status": False,
        "setup": False,
        "instrument": False,
        "presets": False,
        "observe": False,
        "observe_guard": False,
    }

    response = client.get("/ui/v7")
    assert response.status_code == 200
    assert "/ui-assets/v7/runtime_status.js" not in response.text
    assert "/ui-assets/v7/setup_runtime.js" not in response.text
    assert "/ui-assets/v7/instrument_runtime.js" not in response.text
    assert "/ui-assets/v7/preset_runtime.js" not in response.text
    assert "/ui-assets/v7/observe_runtime.js" not in response.text
    assert "/ui-assets/v7/observe_guard.js" not in response.text
    assert "/ui-assets/v7/sequence_runtime.js" not in response.text
    assert "/ui-assets/v7/camera_runtime.js" not in response.text


def test_v7_runtime_modules_are_individually_opt_in(monkeypatch):
    monkeypatch.setenv("JUSTLS_UI_V7_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("JUSTLS_UI_V7_INSTRUMENT_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("JUSTLS_UI_V7_PRESET_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("JUSTLS_UI_V7_OBSERVE_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("JUSTLS_UI_V7_OBSERVE_GUARD_ENABLED", "1")
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    switches = response.json()["ui_safety_switches"]
    assert switches["phase2d8_v7_runtime_modules"] == {
        "status": True,
        "setup": True,
        "instrument": True,
        "presets": True,
        "observe": True,
        "observe_guard": True,
    }

    response = client.get("/ui/v7")

    assert response.status_code == 200
    assert response.text.index("/ui-assets/v7/runtime_status.js") < response.text.index("/ui-assets/v7/instrument_runtime.js")
    assert response.text.index("/ui-assets/v7/instrument_runtime.js") < response.text.index("/ui-assets/v7/preset_runtime.js")
    assert response.text.index("/ui-assets/v7/preset_runtime.js") < response.text.index("/ui-assets/v7/observe_runtime.js")
    assert response.text.index("/ui-assets/v7/observe_runtime.js") < response.text.index("/ui-assets/v7/observe_guard.js")


def test_v7_status_runtime_can_be_disabled_even_when_observe_defaults_on(monkeypatch):
    monkeypatch.setenv("JUSTLS_UI_V7_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("JUSTLS_UI_V7_RUNTIME_STATUS_ENABLED", "0")
    monkeypatch.delenv("JUSTLS_UI_V7_OBSERVE_RUNTIME_ENABLED", raising=False)
    monkeypatch.delenv("JUSTLS_UI_V7_OBSERVE_GUARD_ENABLED", raising=False)
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    modules = response.json()["ui_safety_switches"]["phase2d8_v7_runtime_modules"]

    assert modules["status"] is False
    assert modules["setup"] is True
    assert modules["instrument"] is True
    assert modules["presets"] is True
    assert modules["observe"] is True
    assert modules["observe_guard"] is True

    response = client.get("/ui/v7")

    assert response.status_code == 200
    assert "/ui-assets/v7/runtime_status.js" not in response.text
    assert "/ui-assets/v7/setup_runtime.js" in response.text
    assert "/ui-assets/v7/instrument_runtime.js" in response.text
    assert "/ui-assets/v7/preset_runtime.js" in response.text
    assert "/ui-assets/v7/observe_runtime.js" in response.text
    assert "/ui-assets/v7/observe_guard.js" in response.text
