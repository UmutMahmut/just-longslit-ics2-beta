from fastapi.testclient import TestClient

from justls.ics.app.main import app


def _clear_v7_runtime_env(monkeypatch):
    for name in (
        "JUSTLS_UI_V7_RUNTIME_ENABLED",
        "JUSTLS_UI_V7_RUNTIME_STATUS_ENABLED",
        "JUSTLS_UI_V7_SETUP_RUNTIME_ENABLED",
        "JUSTLS_UI_V7_INSTRUMENT_RUNTIME_ENABLED",
        "JUSTLS_UI_V7_PRESET_RUNTIME_ENABLED",
        "JUSTLS_UI_V7_OBSERVE_RUNTIME_ENABLED",
        "JUSTLS_UI_V7_OBSERVE_GUARD_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)


def test_ui_root_is_default_v7_operator_console_prototype(monkeypatch):
    _clear_v7_runtime_env(monkeypatch)
    client = TestClient(app)

    response = client.get("/ui")

    assert response.status_code == 200
    assert "v7.1 Operator Console Prototype" in response.text
    assert "UI Alpha Skeleton" not in response.text
    assert "/ui-assets/v5/phase2d6_operational_status.js" not in response.text

    assert "/ui-assets/v7/runtime_status.js" in response.text
    assert "/ui-assets/v7/setup_runtime.js" in response.text
    assert "/ui-assets/v7/instrument_runtime.js" in response.text
    assert "/ui-assets/v7/preset_runtime.js" in response.text
    assert "/ui-assets/v7/observe_runtime.js" in response.text
    assert "/ui-assets/v7/observe_guard.js" in response.text
    assert "/ui-assets/v7/sequence_runtime.js" in response.text

    assert 'data-role="v7-message-rail"' in response.text
    assert "Operator Feedback" in response.text
    assert 'data-bind="v7.message.phase"' in response.text


def test_v5_legacy_fallback_routes_stay_available():
    client = TestClient(app)

    for route in ("/ui/v5", "/ui/legacy"):
        response = client.get(route)

        assert response.status_code == 200
        assert "UI Alpha Skeleton" in response.text
        assert "v7.1 Operator Console Prototype" not in response.text
        assert "/ui-assets/v5/phase2d6_operational_status.js" in response.text


def test_ui_v6_review_shell_stays_available():
    client = TestClient(app)

    response = client.get("/ui/v6")

    assert response.status_code == 200
    assert "v6" in response.text.lower()


def test_ui_v7_default_runtime_injects_status_observe_and_guard(monkeypatch):
    _clear_v7_runtime_env(monkeypatch)
    client = TestClient(app)

    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["ui"] == "/ui"
    assert root.json()["ui_default"] == "v7"
    assert root.json()["ui_v5"] == "/ui/v5"
    assert root.json()["ui_legacy"] == "/ui/legacy"
    assert root.json()["ui_v7"] == "/ui/v7"

    switches = root.json()["ui_safety_switches"]
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
    assert "v7.1 Operator Console Prototype" in response.text
    assert "Instrument / Configure" in response.text

    assert "/ui-assets/v7/runtime_status.js" in response.text
    assert "/ui-assets/v7/setup_runtime.js" in response.text
    assert "/ui-assets/v7/instrument_runtime.js" in response.text
    assert "/ui-assets/v7/preset_runtime.js" in response.text
    assert "/ui-assets/v7/observe_runtime.js" in response.text
    assert "/ui-assets/v7/observe_guard.js" in response.text
    assert "/ui-assets/v7/sequence_runtime.js" in response.text


def test_v7_default_and_explicit_v7_shells_are_aligned():
    client = TestClient(app)

    default_response = client.get("/ui")
    explicit_response = client.get("/ui/v7")

    assert default_response.status_code == 200
    assert explicit_response.status_code == 200
    assert default_response.text == explicit_response.text
