from fastapi.testclient import TestClient

from justls.ics.app.main import app


def test_v7_1_all_runtime_modules_inject_against_single_durable_skeletons(monkeypatch):
    monkeypatch.setenv("JUSTLS_UI_V7_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("JUSTLS_UI_V7_INSTRUMENT_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("JUSTLS_UI_V7_PRESET_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("JUSTLS_UI_V7_OBSERVE_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("JUSTLS_UI_V7_OBSERVE_GUARD_ENABLED", "1")
    client = TestClient(app)

    response = client.get("/ui/v7")

    assert response.status_code == 200
    html = response.text
    assert html.count('id="v7-runtime-status"') == 1
    assert html.count('id="v7-raw-status-preview"') == 1
    assert html.count('id="v7-setup-readiness"') == 1
    assert html.count('id="v7-instrument-controls"') == 1
    assert html.count('id="v7-observe-controls"') == 1
    assert html.count('id="v7-presets-runtime"') == 1
    assert 'data-page-panel="instrument"' in html
    assert 'data-bind="v7.instrument.current_preset"' in html
    assert 'data-bind="v7.instrument.channel.B.enabled"' in html
    assert 'data-bind="v7.instrument.channel.G.enabled"' in html
    assert 'data-bind="v7.instrument.channel.R.enabled"' in html
    assert 'data-bind="v7.message.text"' in html
    assert "/ui-assets/v7/runtime_status.js" in html
    assert "/ui-assets/v7/instrument_runtime.js" in html
    assert "/ui-assets/v7/preset_runtime.js" in html
    assert "/ui-assets/v7/observe_runtime.js" in html
    assert "/ui-assets/v7/observe_guard.js" in html


def test_v7_runtime_status_asset_targets_v7_1_instrument_and_diagnostics_skeletons():
    client = TestClient(app)

    response = client.get("/ui-assets/v7/runtime_status.js")

    assert response.status_code == 200
    js = response.text
    assert "__JUSTLS_V7_RUNTIME_STATUS__" in js
    assert "v7-runtime-status" in js
    assert "v7-setup-readiness" in js
    assert "v7-raw-status-preview" in js
    assert "v7.instrument.current_preset" in js
    assert "v7.instrument.bgr_readiness" in js
    assert "v7.instrument.channel.B.enabled" in js
    assert "v7.instrument.channel.G.enabled" in js
    assert "v7.instrument.channel.R.enabled" in js
    assert "v7.message.text" in js


def test_v7_runtime_status_asset_tracks_feedback_rail_telemetry():
    client = TestClient(app)

    response = client.get("/ui-assets/v7/runtime_status.js")

    assert response.status_code == 200
    js = response.text
    assert "lastRequestId" in js
    assert "lastRttMs" in js
    assert "lastOkAt" in js
    assert "connectionState" in js
    assert "requestIdFrom" in js
    assert "X-Request-ID" in js
    assert "x-request-id" in js
    assert "performance.now" in js
    assert "data-severity" in js
    assert "data-connection" in js
    assert "data-request-id" in js
    assert "v7.message.severity" in js
    assert "v7.connection.rtt_ms" in js
    assert "v7.connection.last_ok_at" in js
    assert "v7.request_id" in js


def test_v7_instrument_runtime_asset_targets_existing_instrument_api_surface():
    client = TestClient(app)

    response = client.get("/ui-assets/v7/instrument_runtime.js")

    assert response.status_code == 200
    js = response.text
    assert "__JUSTLS_V7_INSTRUMENT_RUNTIME__" in js
    assert "SLIT_ENDPOINT" in js
    assert "SLIT_ANGLE_ENDPOINT" in js
    assert "CALIBRATION_STATUS_ENDPOINT" in js
    assert "CALIBRATION_MODE_ENDPOINT" in js
    assert "CALIBRATION_LAMP_ENDPOINT" in js
    assert "DETECTOR_CONFIG_ENDPOINT" in js
    assert "/api/v1/slit" in js
    assert "/api/v1/slit_angle" in js
    assert "/api/v1/calibration/status" in js
    assert "/api/v1/calibration/mode" in js
    assert "/api/v1/calibration/lamp" in js
    assert "/api/v1/detector/config" in js
    assert "v7.instrument.request_id" in js
    assert "v7.instrument.last_command" in js
    assert "v7.instrument.last_error" in js
    assert "Blue Channel" not in js
    assert "Red Channel" not in js


def test_v7_instrument_runtime_preserves_p0_slit_unit_contract():
    client = TestClient(app)

    response = client.get("/ui-assets/v7/instrument_runtime.js")

    assert response.status_code == 200
    js = response.text
    assert "SLIT_UM_PER_ARCSEC = 128.34" in js
    assert "COMMON_SLIT_WIDTH_ARCSEC = [1.0, 1.5, 2.0, 3.0]" in js
    assert "instrument-slit-width-arcsec" in js
    assert "instrument-slit-width-um" in js
    assert "umFromArcsec" in js
    assert "arcsecFromUm" in js
    assert 'data-arcsec="1.0"' in js
    assert 'data-arcsec="1.5"' in js
    assert 'data-arcsec="2.0"' in js
    assert 'data-arcsec="3.0"' in js
    assert 'data-arcsec="0.1"' not in js
    assert "0.1 arcsec" not in js


def test_v7_preset_runtime_asset_targets_existing_presets_skeleton():
    client = TestClient(app)

    response = client.get("/ui-assets/v7/preset_runtime.js")

    assert response.status_code == 200
    js = response.text
    assert "__JUSTLS_V7_PRESET_RUNTIME__" in js
    assert 'document.getElementById("v7-presets-runtime")' in js
    assert 'data-bind="v7.presets.catalog"' in js
    assert 'data-bind="v7.presets.preview"' in js
    assert 'data-role="v7-preset-confirmation"' in js
    assert 'data-action="apply-previewed-preset"' in js
    assert "/api/v1/presets" in js
    assert "/api/v1/presets/preview" in js
    assert "/api/v1/presets/apply" in js


def test_v7_observe_runtime_and_guard_assets_target_existing_observe_skeleton():
    client = TestClient(app)

    runtime_response = client.get("/ui-assets/v7/observe_runtime.js")
    guard_response = client.get("/ui-assets/v7/observe_guard.js")

    assert runtime_response.status_code == 200
    assert guard_response.status_code == 200
    runtime_js = runtime_response.text
    guard_js = guard_response.text
    assert "__JUSTLS_V7_OBSERVE_RUNTIME__" in runtime_js
    assert 'document.getElementById("v7-observe-controls")' in runtime_js
    assert 'data-role="obs-exp-time"' in runtime_js
    assert 'data-role="obs-frame-type"' in runtime_js
    assert 'data-role="obs-operator-note"' in runtime_js
    assert 'data-role="obs-abort-confirm"' in runtime_js
    assert '["obs-arm", arm]' in runtime_js
    assert '["obs-start", () => postCommand("start", START_ENDPOINT)]' in runtime_js
    assert '["obs-finish", () => postCommand("finish", FINISH_ENDPOINT)]' in runtime_js
    assert '["obs-stop-readout", () => postCommand("stop_readout", STOP_READOUT_ENDPOINT)]' in runtime_js
    assert '["obs-abort-discard", abortDiscard]' in runtime_js
    assert "FINISH_ENDPOINT" in runtime_js
    assert "/api/v1/observation/finish" in runtime_js
    assert "v7.observe.request_id" in runtime_js
    assert "v7.observe.latest_job" in runtime_js
    assert "v7.observe.last_error" in runtime_js
    assert "requestIdFrom" in runtime_js
    assert "isCommandFeedback" in runtime_js
    assert "commandFeedbackSummary" in runtime_js
    assert "renderCommandFeedback" in runtime_js
    assert "runtime.lastStatus.armed_exposure || null" in runtime_js
    assert "armed_exposure || runtime.lastStatus.last_exposure" not in runtime_js
    assert "blocked_components" in runtime_js
    assert "blocked_reason" in runtime_js
    assert "validation_issues" in runtime_js
    assert "__JUSTLS_V7_OBSERVE_GUARD__" in guard_js
    assert 'document.getElementById("v7-observe-controls")' in guard_js
    assert 'data-role="obs-abort-confirm"' in guard_js
    assert "obs-arm" in guard_js
    assert "obs-start" in guard_js
    assert "obs-finish" in guard_js
    assert "obs-stop_readout" not in guard_js
    assert "obs-stop-readout" in guard_js
    assert "obs-abort-discard" in guard_js


def test_v7_sequence_runtime_targets_audited_sequence_api_and_panel():
    client = TestClient(app)

    response = client.get("/ui-assets/v7/sequence_runtime.js")

    assert response.status_code == 200
    js = response.text
    assert "__JUSTLS_V7_SEQUENCE_RUNTIME__" in js
    assert 'data-role="v7-observe-sequence-panel"' in js
    assert "/api/v1/observation/sequence/preview" in js
    assert "/api/v1/observation/sequence/load" in js
    assert "/api/v1/observation/sequence/start" in js
    assert "/api/v1/observation/sequence/finish_step" in js
    assert "/api/v1/observation/sequence/pause" in js
    assert "/api/v1/observation/sequence/resume" in js
    assert "/api/v1/observation/sequence/abort" in js
    assert "/api/v1/observation/sequence/retry_current_step" in js
    assert "/api/v1/observation/sequence/mark_failed" in js
    assert "x-request-id" in js
    assert "step_results" in js
    assert "previewPlan" in js
    assert "readPlanForLoad" in js
    assert 'data-role="sequence-abort-confirm"' in js
    assert 'data-role="sequence-mark-failed-confirm"' in js
    assert "recovery_required" in js
    assert "justls:v7-sequence-state" in js
    assert "justls:v7-setup-refresh" in js
    assert "latest_job" in js
    assert "save_requested" in js
    assert "sequenceLocked" in js
    assert 'setMode("sequence")' in js
    assert "v7.sequence.reservation" in js

    setup = client.get("/ui-assets/v7/setup_runtime.js")
    assert setup.status_code == 200
    assert 'window.addEventListener("justls:v7-setup-refresh", loadContext)' in setup.text


def test_v7_camera_runtime_only_polls_slit_preview_and_refreshes_completed_science_frames():
    js = TestClient(app).get("/ui-assets/v7/camera_runtime.js").text

    assert 'START_ENDPOINT = "/api/v1/cameras/slit/preview/start"' in js
    assert 'STOP_ENDPOINT = "/api/v1/cameras/slit/preview/stop"' in js
    assert 'SLIT_FRAME_ENDPOINT = "/camera/slit/latest.jpg"' in js
    assert 'data-role="slit-preview-enabled"' in js
    assert 'data-role="science-channel-image"' in js
    assert "querySelectorAll" in js
    assert 'data-role="science-latest-image"' not in js
    assert "justls:v7-observe-state" in js
    assert 'img[src^="/camera/"]' not in js


def test_v7_observe_runtime_refreshes_after_sequence_commands_and_guard_owns_direct_controls():
    client = TestClient(app)

    observe = client.get("/ui-assets/v7/observe_runtime.js")
    guard = client.get("/ui-assets/v7/observe_guard.js")

    assert observe.status_code == 200
    assert guard.status_code == 200
    assert 'button[data-action^="obs-"]' in observe.text
    assert "const firstEnable" in observe.text
    assert 'window.addEventListener("justls:v7-local-refresh", refreshStatus)' in observe.text
    assert 'window.addEventListener("justls:v7-sequence-state", handleSequenceState)' in guard.text
    assert "runtime.sequenceActive" in guard.text


def test_v7_served_observe_shell_exposes_h3_finish_and_structured_result_fields():
    client = TestClient(app)

    response = client.get("/ui/v7")

    assert response.status_code == 200
    html = response.text
    assert 'data-action="obs-finish"' in html
    assert 'data-bind="v7.observe.request_id"' in html
    assert 'data-bind="v7.observe.latest_job"' in html
    assert 'data-bind="v7.observe.last_error"' in html
