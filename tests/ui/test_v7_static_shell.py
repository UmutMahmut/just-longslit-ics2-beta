from fastapi.testclient import TestClient

from justls.ics.app.main import app


def test_v7_static_shell_is_available_and_preserves_live_preview():
    client = TestClient(app)

    response = client.get("/ui/v7")

    assert response.status_code == 200
    assert "v7.1 Operator Console Prototype" in response.text
    assert "Slit / Guide Camera · Continuous Preview" in response.text
    assert "Instrument / Configure" in response.text


def test_v7_static_setup_page_is_action_oriented_readiness_workspace():
    client = TestClient(app)

    response = client.get("/ui/v7")

    assert response.status_code == 200
    html = response.text
    assert 'data-role="setup-page"' in html
    assert 'data-role="setup-overview"' in html
    assert 'data-role="setup-session-context"' in html
    assert 'data-role="session-input"' in html
    assert 'id="v7-setup-readiness"' in html
    assert 'data-role="setup-readiness"' in html
    assert 'data-role="setup-next-steps"' in html

    assert 'data-page-shortcut="instrument"' in html
    assert 'data-page-shortcut="presets"' in html
    assert 'data-page-shortcut="observe"' in html
    assert 'data-page-shortcut="diagnostics"' in html

    assert "Configure Instrument" in html
    assert "Review Presets" in html
    assert "Go to Observe" in html
    assert "Readiness Checklist" in html

    assert 'data-bind="v7.setup.run_mode"' in html
    assert 'data-bind="v7.setup.operational"' in html
    assert 'data-bind="v7.setup.observation_state"' in html
    assert 'data-bind="v7.setup.detector_profile"' in html
    assert 'data-bind="v7.data.next_frame_token"' in html
    assert 'data-bind="v7.data.directory"' in html

    assert 'data-phase="2.9-A-persisted-context"' in html
    assert 'data-bind="v7.setup.persistence_status"' in html
    assert 'data-bind="v7.setup.save_status"' in html
    assert 'data-action="setup-save-context"' in html
    assert 'data-action="setup-reload-context"' in html
    assert 'data-field="next_frame_index"' in html
    assert 'data-field="data_directory"' in html
    assert 'data-bind="v7.data.file_stem"' in html
    assert 'data-bind="v7.data.fits_filename"' in html

    assert "Session backend pending" not in html
    assert "Not saved to backend" not in html
    assert "Backend save pending" not in html
    client = TestClient(app)

    response = client.get("/ui/v7")

    assert response.status_code == 200
    html = response.text
    assert 'data-role="setup-page"' in html
    assert 'data-role="setup-overview"' in html
    assert 'data-role="setup-session-context"' in html
    assert 'data-role="session-input"' in html
    assert 'id="v7-setup-readiness"' in html
    assert 'data-role="setup-readiness"' in html
    assert 'data-role="setup-next-steps"' in html

    assert 'data-page-shortcut="instrument"' in html
    assert 'data-page-shortcut="presets"' in html
    assert 'data-page-shortcut="observe"' in html
    assert 'data-page-shortcut="diagnostics"' in html

    assert "Configure Instrument" in html
    assert "Review Presets" in html
    assert "Go to Observe" in html
    assert "Readiness Checklist" in html

    assert 'data-bind="v7.setup.run_mode"' in html
    assert 'data-bind="v7.setup.operational"' in html
    assert 'data-bind="v7.setup.observation_state"' in html
    assert 'data-bind="v7.setup.detector_profile"' in html
    assert 'data-bind="v7.data.next_frame_token"' in html
    assert 'data-bind="v7.data.directory"' in html



def test_v7_static_presets_page_has_single_runtime_enhanceable_skeleton():
    client = TestClient(app)

    response = client.get("/ui/v7")

    assert response.status_code == 200
    assert response.text.count('id="v7-presets-runtime"') == 1
    assert 'data-role="v7-presets-panel"' in response.text
    assert 'data-phase="static-fallback"' in response.text
    assert 'data-bind="v7.presets.status"' in response.text
    assert 'data-bind="v7.presets.catalog"' in response.text
    assert 'data-bind="v7.presets.preview"' in response.text
    assert 'data-role="v7-preset-confirmation"' in response.text
    assert 'data-action="apply-previewed-preset"' in response.text
    assert "Presets · Catalog / Preview / Guarded Apply" in response.text
    assert "<h2>Preset List</h2>" not in response.text
    assert "<h2>Preview / Apply</h2>" not in response.text


def test_v7_static_observe_page_has_single_runtime_enhanceable_skeleton():
    client = TestClient(app)

    response = client.get("/ui/v7")

    assert response.status_code == 200
    assert response.text.count('id="v7-observe-controls"') == 1
    assert 'data-role="v7-observe-panel"' in response.text
    assert 'data-bind="v7.observe.state"' in response.text
    assert 'data-bind="v7.observe.armed"' in response.text
    assert 'data-bind="v7.observe.last_command"' in response.text
    assert 'data-bind="v7.observe.runtime_state"' in response.text
    assert 'data-bind="v7.observe.result"' in response.text
    assert 'data-role="obs-exp-time"' in response.text
    assert 'data-role="obs-frame-type"' in response.text
    assert '<option value="bias">bias</option>' in response.text
    assert '<option value="dark">dark</option>' in response.text
    assert 'data-role="obs-operator-note"' in response.text
    assert 'data-role="obs-abort-confirm"' in response.text
    assert 'data-action="obs-arm"' in response.text
    assert 'data-action="obs-start"' in response.text
    assert 'data-action="obs-stop-readout"' in response.text
    assert 'data-action="obs-abort-discard"' in response.text
    assert "Science Acquisition Control" in response.text
    assert 'data-role="v7-observe-sequence-panel"' in response.text
    assert 'data-bind="v7.observe.record.fits"' in response.text
    assert 'data-role="sequence-abort-confirm"' in response.text
    assert 'data-role="sequence-mark-failed-confirm"' in response.text
    assert 'data-action="sequence-retry-current-step"' in response.text
    assert 'data-action="sequence-mark-failed"' in response.text
    assert 'data-bind="v7.sequence.persistence"' in response.text
    assert 'data-bind="v7.sequence.recovery"' in response.text
    assert 'data-bind="v7.sequence.reservation"' in response.text
    assert 'data-bind="v7.sequence.latest_job"' in response.text
    assert 'data-bind="v7.sequence.last_error"' in response.text
    assert "does not schedule timer-based completion" in response.text
    assert "Phase 3.0-B Lite operator workflow" in response.text
    assert "Durable sequence recovery active" in response.text
    assert "Buttons are static until Phase 2.8-F binding" not in response.text


def test_v7_observe_shell_preserves_compact_slit_over_bgr_camera_layout():
    html = TestClient(app).get("/ui/v7").text

    assert 'data-action="observe-mode-single"' in html
    assert 'data-action="observe-mode-sequence"' in html
    assert 'data-observe-mode-panel="single"' in html
    assert 'data-observe-mode-panel="sequence" hidden' in html
    assert 'data-role="observe-save-products"' in html
    assert 'data-role="observe-save-products" checked' not in html
    assert 'data-role="slit-preview-enabled" checked' in html
    assert 'class="panel observe-camera-panel"' in html
    assert 'class="live-preview slit-preview"' in html
    assert "--observe-slit-height:" in html
    assert "--observe-bgr-height:" in html
    assert "justify-content: space-between" in html
    assert "height: var(--observe-slit-height)" in html
    assert "height: var(--observe-bgr-height)" in html
    assert ".observe-camera-stack { justify-content: flex-start; }" in html
    assert html.count('data-role="science-channel-image"') == 3
    assert 'data-ics-camera-src="/camera/b/latest.jpg"' in html
    assert 'data-ics-camera-src="/camera/g/latest.jpg"' in html
    assert 'data-ics-camera-src="/camera/r/latest.jpg"' in html
    assert "Beta: one shared science-camera source feeds B/G/R" in html
    assert "B/G/R layout remains ready for three independent science cameras" in html
    assert 'data-role="science-latest-image"' not in html
    assert "the science acquisition path has no separate Preview lifecycle." in html

def test_v7_default_shell_exposes_unified_command_feedback_static_bindings():
    client = TestClient(app)

    response = client.get("/ui")

    assert response.status_code == 200
    assert "v7.1 Operator Console Prototype" in response.text
    assert 'data-role="diagnostics-command-feedback"' in response.text
    assert "last_command / request_id / latest_job / last_error / result_summary / raw_json" in response.text

    for prefix in ("instrument", "observe", "presets"):
        assert f'data-bind="v7.{prefix}.last_command"' in response.text
        assert f'data-bind="v7.{prefix}.request_id"' in response.text
        assert f'data-bind="v7.{prefix}.latest_job"' in response.text
        assert f'data-bind="v7.{prefix}.last_error"' in response.text
        assert f'data-bind="v7.{prefix}.result_summary"' in response.text

    assert 'data-bind="v7.setup.request_id"' in response.text
    assert 'data-bind="v7.setup.result_summary"' in response.text
    assert 'data-bind="v7.sequence.request_id"' in response.text
    assert 'data-bind="v7.sequence.latest_job"' in response.text
    assert 'data-bind="v7.sequence.last_error"' in response.text
    assert 'data-bind="v7.sequence.summary"' in response.text
    assert 'data-bind="v7.diagnostics.data_provenance"' in response.text
    assert 'data-bind="v7.diagnostics.latest_fits"' in response.text
