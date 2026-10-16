from fastapi.testclient import TestClient

from justls.ics.app.main import app


def test_v7_runtime_static_assets_are_served_from_v7_directory():
    client = TestClient(app)

    assets = {
        "status": client.get("/ui-assets/v7/runtime_status.js"),
        "presets": client.get("/ui-assets/v7/preset_runtime.js"),
        "observe": client.get("/ui-assets/v7/observe_runtime.js"),
        "sequence": client.get("/ui-assets/v7/sequence_runtime.js"),
        "guard": client.get("/ui-assets/v7/observe_guard.js"),
    }

    for response in assets.values():
        assert response.status_code == 200

    assert "/api/v1/status/full" in assets["status"].text
    assert "/api/v1/presets" in assets["presets"].text
    assert "/api/v1/presets/preview" in assets["presets"].text
    assert "/api/v1/presets/apply" in assets["presets"].text
    assert "/api/v1/observation/status" in assets["observe"].text
    assert "/api/v1/observation/arm" in assets["observe"].text
    assert "/api/v1/observation/start" in assets["observe"].text
    assert "/api/v1/observation/stop_readout" in assets["observe"].text
    assert "/api/v1/observation/sequence/preview" in assets["sequence"].text
    assert "/api/v1/observation/sequence/finish_step" in assets["sequence"].text


def test_v5_operational_adapter_is_served_from_v5_directory():
    client = TestClient(app)

    adapter = client.get("/ui-assets/v5/phase2d6_operational_status.js")

    assert adapter.status_code == 200
    assert "/api/v1/status/full" in adapter.text
    assert "Phase 2.6 operational status adapter" in adapter.text


def test_v7_runtime_assets_have_expected_panel_markers():
    client = TestClient(app)

    status = client.get("/ui-assets/v7/runtime_status.js")
    presets = client.get("/ui-assets/v7/preset_runtime.js")
    observe = client.get("/ui-assets/v7/observe_runtime.js")
    guard = client.get("/ui-assets/v7/observe_guard.js")

    assert status.status_code == 200
    assert presets.status_code == 200
    assert observe.status_code == 200
    assert guard.status_code == 200

    assert "v7-runtime-status" in status.text
    assert "v7-setup-readiness" in status.text
    assert "v7-raw-status-preview" in status.text
    assert "v7-presets-runtime" in presets.text
    assert "Guarded Apply" in presets.text
    assert "v7-observe-controls" in observe.text
    assert "3.0-transition-camera-roles" in observe.text
    assert "data-guard-available" in guard.text
    assert "fetch(" not in guard.text
    assert "new XMLHttpRequest" not in guard.text
    # A discarded/aborted exposure leaves the detector idle; the guard must let
    # the operator arm again, otherwise one abort locks the panel forever.
    assert 'name.includes("discard")' in guard.text
    assert 'name.includes("abort")' in guard.text


def test_v7_status_runtime_is_singleton_safe():
    client = TestClient(app)

    status = client.get("/ui-assets/v7/runtime_status.js")

    assert status.status_code == 200
    assert "__JUSTLS_V7_RUNTIME_STATUS__" in status.text
    assert "runtime.started" in status.text
    assert "runtime.intervalId" in status.text
    assert "runtime.refreshInFlight" in status.text
    assert "window.setInterval(refresh, POLL_MS)" in status.text
    assert "v7.runtime_status.refresh_count" in status.text


def test_v7_status_runtime_binds_top_cards_and_diagnostics():
    client = TestClient(app)

    status = client.get("/ui-assets/v7/runtime_status.js")

    assert status.status_code == 200
    assert "setTopStatusText" in status.text
    assert "bindTopStatusCards" in status.text
    assert 'document.getElementById(id)' in status.text
    assert 'setTopStatusText("run-mode"' in status.text
    assert 'setTopStatusText("operational-level"' in status.text
    assert 'setTopStatusText("exposure-state"' in status.text
    assert 'panel("v7-runtime-status", "Runtime Status · /api/v1/status/full", \'[data-page-panel="diagnostics"]\')' in status.text
    assert 'panel("v7-raw-status-preview", "Raw Status Preview · /api/v1/status/full", \'[data-page-panel="diagnostics"]\')' in status.text


def test_v7_preset_runtime_is_singleton_safe_and_inflight_guarded():
    client = TestClient(app)

    presets = client.get("/ui-assets/v7/preset_runtime.js")

    assert presets.status_code == 200
    assert "__JUSTLS_V7_PRESET_RUNTIME__" in presets.text
    assert "runtime.started" in presets.text
    assert "runtime.catalogLoading" in presets.text
    assert "runtime.previewInFlight" in presets.text
    assert "runtime.applying" in presets.text
    assert "runtime.lastPreview" in presets.text
    assert "runtime.lastApplyResult" in presets.text
    assert "runtime.lastError" in presets.text
    assert "if (runtime.started)" in presets.text
    assert "if (runtime.catalogLoading) return" in presets.text
    assert "if (runtime.previewInFlight || runtime.applying) return" in presets.text
    assert "if (runtime.applying || runtime.previewInFlight) return" in presets.text
    assert "dataset.bound" in presets.text
    assert "v7.presets.runtime_state" in presets.text
    assert "v7.presets.last_error" in presets.text


def test_v7_preset_runtime_creates_single_fallback_panel_when_skeleton_is_missing():
    client = TestClient(app)

    presets = client.get("/ui-assets/v7/preset_runtime.js")

    assert presets.status_code == 200
    assert "runtime-created-presets-skeleton" in presets.text
    assert "replaceChildren(panel)" in presets.text
    assert "competing Presets UIs" in presets.text
    assert "createFallbackPanel" in presets.text
    assert "enhancePanel" in presets.text


def test_v7_observe_runtime_is_singleton_safe_and_skeleton_aware():
    client = TestClient(app)

    observe = client.get("/ui-assets/v7/observe_runtime.js")

    assert observe.status_code == 200
    assert "__JUSTLS_V7_OBSERVE_RUNTIME__" in observe.text
    assert "runtime.started" in observe.text
    assert "runtime.busy" in observe.text
    assert "runtime.statusLoading" in observe.text
    assert "runtime.lastStatus" in observe.text
    assert "runtime.lastCommand" in observe.text
    assert "runtime.lastResult" in observe.text
    assert "runtime.lastError" in observe.text
    assert "runtime-created-observe-skeleton" not in observe.text
    assert "createFallbackPanel" not in observe.text
    assert "enhancePanel" in observe.text
    assert "dataset.bound" in observe.text
    assert "justls:v7-observe-state" in observe.text
    assert "v7.observe.runtime_state" in observe.text
    assert "isCommandFeedback" in observe.text
    assert "commandFeedbackSummary" in observe.text
    assert "renderCommandFeedback" in observe.text
    assert "blocked_components" in observe.text
    assert "blocked_reason" in observe.text


def test_v7_observe_guard_is_singleton_safe_and_narrowly_observed():
    client = TestClient(app)

    guard = client.get("/ui-assets/v7/observe_guard.js")

    assert guard.status_code == 200
    assert "__JUSTLS_V7_OBSERVE_GUARD__" in guard.text
    assert "runtime.started" in guard.text
    assert "runtime.observer" in guard.text
    assert "runtime.retryTimer" in guard.text
    assert "runtime.lastAllowed" in guard.text
    assert "dataset.guardBound" in guard.text
    assert "justls:v7-observe-state" in guard.text
    assert "observer.observe(host, { childList: true, subtree: false })" in guard.text
    assert "subtree: true" not in guard.text
    assert "fetch(" not in guard.text
    assert "new XMLHttpRequest" not in guard.text
