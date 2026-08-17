from fastapi.testclient import TestClient

from justls.ics.app.main import app


def test_v7_static_shell_contains_instrument_configure_page():
    client = TestClient(app)

    response = client.get("/ui/v7")

    assert response.status_code == 200
    html = response.text
    assert "Instrument / Configure" in html
    assert 'data-page="instrument"' in html
    assert 'data-page-panel="instrument"' in html
    assert 'data-role="instrument-overview"' in html
    assert 'id="v7-instrument-controls"' in html
    assert 'data-role="v7-instrument-controls"' in html
    assert 'data-role="instrument-slit-controls"' in html
    assert 'data-role="instrument-calibration-controls"' in html
    assert "Mode/Lamp must match the intended frame type" in html
    assert "Science frames require science mode and lamps off" in html
    assert "flat frames require calibration mode with the flat lamp" in html
    assert "arc frames require calibration mode with an Hg(Ar) or Ne arc lamp" in html
    assert 'data-action="instrument-use-calibration-frame-defaults"' in html
    assert 'data-bind="v7.instrument.calibration.active_lamp"' in html
    assert 'data-bind="v7.instrument.calibration.lamp_enabled"' in html
    assert 'data-bind="v7.instrument.calibration.mirror_inserted"' in html
    assert 'data-bind="v7.instrument.calibration.frame_type_context"' in html
    assert 'data-bind="v7.instrument.calibration.expected_for_frame"' in html
    assert 'data-bind="v7.instrument.calibration.compatibility"' in html
    assert 'data-role="instrument-detector-visibility"' in html
    assert 'data-role="bgr-channel-summary"' in html
    assert 'data-role="instrument-command-summary"' in html
    assert 'data-role="instrument-boundary-note"' in html
    assert 'data-role="instrument-raw-debug"' in html


def test_v7_static_shell_preserves_stable_runtime_binding_ids():
    client = TestClient(app)

    response = client.get("/ui/v7")

    assert response.status_code == 200
    html = response.text
    assert 'id="run-mode"' in html
    assert 'id="operational-level"' in html
    assert 'id="exposure-state"' in html
    assert 'id="local-time"' in html
    assert 'id="v7-observe-controls"' in html
    assert 'id="v7-presets-runtime"' in html


def test_v7_static_shell_exposes_operator_feedback_rail_fields():
    client = TestClient(app)

    response = client.get("/ui/v7")

    assert response.status_code == 200
    html = response.text
    assert 'data-role="v7-message-rail"' in html
    assert "Operator Feedback" in html
    assert 'data-severity="info"' in html
    assert 'data-connection="static"' in html
    assert 'data-bind="v7.message.text"' in html
    assert 'data-bind="v7.message.phase"' in html
    assert 'data-bind="v7.message.severity"' in html
    assert 'data-bind="v7.message.connection"' in html
    assert 'data-bind="v7.message.rtt_ms"' in html
    assert 'data-bind="v7.message.last_ok_at"' in html
    assert 'data-bind="v7.message.request_id"' in html
    assert 'data-bind="v7.message.poll_count"' in html
    assert 'data-bind="v7.message.freshness"' in html


def test_v7_static_shell_models_just_as_bgr_not_mods_blue_red():
    client = TestClient(app)

    response = client.get("/ui/v7")

    assert response.status_code == 200
    html = response.text
    assert "B Channel" in html
    assert "G Channel" in html
    assert "R Channel" in html
    assert 'data-channel="B"' in html
    assert 'data-channel="G"' in html
    assert 'data-channel="R"' in html


def test_v7_static_shell_keeps_unwired_hardware_honest():
    client = TestClient(app)

    response = client.get("/ui/v7")

    assert response.status_code == 200
    html = response.text
    assert "Runtime enabled by default" in html
    assert "read-only summary" in html
    assert "not connected" in html or "no command yet" in html
