from fastapi.testclient import TestClient

from justls.ics.app.main import app, env_flag, inject_phase_2d6_ui_adapter
from justls.ics.kernel.runtime import reset_runtime

V5_ADAPTER_PATH = "/ui-assets/v5/phase2d6_operational_status.js"


def setup_function():
    reset_runtime()


def teardown_function():
    reset_runtime()


def test_v5_ui_injection_is_idempotent():
    html = "<html><body><main>UI</main></body></html>"

    once = inject_phase_2d6_ui_adapter(html)
    twice = inject_phase_2d6_ui_adapter(once)

    assert once == twice
    assert once.count(V5_ADAPTER_PATH) == 1
    assert once.index(V5_ADAPTER_PATH) < once.index("</body>")


def test_v5_fallback_routes_serve_operational_adapter():
    client = TestClient(app)

    for route in ("/ui/v5", "/ui/legacy"):
        response = client.get(route)

        assert response.status_code == 200
        assert V5_ADAPTER_PATH in response.text


def test_v6_route_available_and_uses_v5_operational_adapter():
    client = TestClient(app)

    response = client.get("/ui/v6")

    assert response.status_code == 200
    assert "Operational UI v6" in response.text
    assert 'data-command="observation.start"' in response.text
    assert 'data-command="observation.stop_readout"' in response.text
    assert 'data-command="observation.abort_discard"' in response.text
    assert 'data-risk="high-impact-config"' in response.text
    assert "/ui-assets/v6/job_alignment.js" in response.text
    assert V5_ADAPTER_PATH in response.text
    assert "/ui-assets/v6/command_runtime.js" in response.text


def test_root_advertises_ui_v6():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["ui_v6"] == "/ui/v6"


def test_env_flag_parsing(monkeypatch):
    monkeypatch.delenv("JUSTLS_TEST_FLAG", raising=False)
    assert env_flag("JUSTLS_TEST_FLAG", default=True) is True
    assert env_flag("JUSTLS_TEST_FLAG", default=False) is False

    for value in ["0", "false", "False", "no", "off", "disabled"]:
        monkeypatch.setenv("JUSTLS_TEST_FLAG", value)
        assert env_flag("JUSTLS_TEST_FLAG", default=True) is False

    for value in ["1", "true", "yes", "on", "enabled"]:
        monkeypatch.setenv("JUSTLS_TEST_FLAG", value)
        assert env_flag("JUSTLS_TEST_FLAG", default=False) is True


def test_v5_adapter_can_be_disabled_by_env(monkeypatch):
    monkeypatch.setenv("JUSTLS_UI_PHASE2D6_ADAPTER_ENABLED", "0")
    client = TestClient(app)

    for route in ("/ui/v5", "/ui/legacy"):
        response = client.get(route)

        assert response.status_code == 200
        assert V5_ADAPTER_PATH not in response.text


def test_v6_can_be_disabled_by_env(monkeypatch):
    monkeypatch.setenv("JUSTLS_UI_V6_ENABLED", "0")
    client = TestClient(app)

    root = client.get("/")
    response = client.get("/ui/v6")

    assert root.status_code == 200
    assert root.json()["ui_v6"] is None
    assert response.status_code == 404


def test_v5_operational_adapter_static_asset_available():
    client = TestClient(app)

    response = client.get(V5_ADAPTER_PATH)

    assert response.status_code == 200
    assert "Phase 2.6 operational status adapter" in response.text
    assert "STATUS_URL" in response.text
    assert "statusRefreshInFlight" in response.text


def test_command_runtime_static_asset_available():
    client = TestClient(app)

    response = client.get("/ui-assets/v6/command_runtime.js")

    assert response.status_code == 200
    assert "COMMAND_TIMEOUT_MS" in response.text
    assert "commandInFlight" in response.text
    assert "X-Request-ID" in response.text
    assert "postJsonWithTimeout" in response.text
    assert "stopImmediatePropagation" in response.text
    assert "phase2d6:command-result" in response.text


def test_job_alignment_static_asset_available():
    client = TestClient(app)

    response = client.get("/ui-assets/v6/job_alignment.js")

    assert response.status_code == 200
    assert "latest_job" in response.text
    assert "phase2d6:status-full" in response.text
    assert "phase2d6:command-result" in response.text
    assert "data-phase2d6-job-panel" in response.text
    assert "job.alignment" in response.text
    assert "installStatusFetchTap" not in response.text
    assert "window.fetch =" not in response.text
