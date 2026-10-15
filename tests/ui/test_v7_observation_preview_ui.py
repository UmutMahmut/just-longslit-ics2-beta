import re

from fastapi.testclient import TestClient

from justls.ics.app.main import app


def test_v7_observe_static_shell_exposes_preview_panel() -> None:
    client = TestClient(app)

    response = client.get("/ui/v7")

    assert response.status_code == 200
    html = response.text

    assert "Readiness / Validation" in html
    assert 'data-role="v7-observe-preview-raw"' in html
    assert 'data-role="v7-observe-command-raw"' in html
    assert "Raw Readiness JSON" in html
    assert "Raw Command JSON" in html
    assert 'data-action="obs-preview"' in html
    assert 'data-role="v7-observe-preview-panel"' in html
    assert 'data-bind="v7.observe.preview.blocked"' in html
    assert 'data-bind="v7.observe.preview.single_exposure_compatible"' in html
    assert 'data-bind="v7.observe.preview.detector_state"' in html
    assert 'data-bind="v7.observe.preview.calibration_state"' in html
    assert 'data-bind="v7.observe.preview.issues"' in html
    assert "Check Readiness" in html
    # The exposure is read out automatically when its timer expires; Preview
    # readiness stays an advisory, independent lifecycle check.
    assert "read out automatically when the timer expires" in html


def test_v7_observe_runtime_asset_binds_preview_endpoint_and_current_api_shape() -> None:
    client = TestClient(app)

    response = client.get("/ui-assets/v7/observe_runtime.js")

    assert response.status_code == 200
    js = response.text

    assert 'PREVIEW_ENDPOINT = "/api/v1/observation/preview"' in js
    assert '["obs-preview", previewObservation]' in js
    assert "function readPreviewPayload()" in js
    assert "async function previewObservation()" in js
    assert "function renderPreview(payload)" in js
    assert "function setPanelButtonsDisabled(panel, disabled)" in js
    assert "setPanelButtonsDisabled(panel, false)" in js
    assert "setPanelButtonsDisabled(panel, value)" in js
    assert "save_requested" in js
    assert "single_exposure_compatible" in js
    assert "validation_issues" in js
    assert "readiness.detector" in js
    assert "readiness.calibration" in js
    assert "readiness.slit" in js
    assert "readiness.tcs" in js

    assert "function isCommandFeedback(payload)" in js
    assert "function commandFeedbackSummary(command, feedback)" in js
    assert "function renderCommandFeedback(command, feedback)" in js
    assert "blocked_components" in js
    assert "blocked_reason" in js
    assert "interlock_blocked" not in js

    # Do not regress to the older reference-branch response shape.
    assert "execution_compatible" not in js
    assert re.search(r"\bpayload\.valid\b", js) is None


def test_v7_observe_runtime_preview_payload_keeps_operator_note_top_level() -> None:
    client = TestClient(app)

    response = client.get("/ui-assets/v7/observe_runtime.js")

    assert response.status_code == 200
    js = response.text

    assert "operator_note: arm.operator_note" in js
    assert "exposures: [" in js
    assert "frame_type: arm.frame_type" in js
    assert "exp_time_s: arm.exp_time_s" in js
