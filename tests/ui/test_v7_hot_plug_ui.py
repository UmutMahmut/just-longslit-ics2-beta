"""Sanity check that the v7 HTML exposes the hot-plug UI hooks.

These selectors are the contract between ``camera_runtime.js`` and the
static shell. If a future HTML refactor drops either of them, the JS
silently fails to wire the Reload Cameras button — so the contract is
frozen by this test.
"""

from fastapi.testclient import TestClient

from justls.ics.app.main import app


def test_v7_html_exposes_hot_plug_and_reload_hooks() -> None:
    client = TestClient(app)
    response = client.get("/ui/v7")
    assert response.status_code == 200
    html = response.text

    # The badge that displays the hot-plug monitor summary.
    assert 'data-bind="v7.camera.hot_plug.status"' in html
    # The button the operator clicks to release + rebind.
    assert 'data-action="v7-reload-cameras"' in html
    assert 'data-role="v7-reload-cameras"' in html
    # The container keeps the badge and button side-by-side.
    assert 'data-role="v7-camera-hot-plug"' in html
    # The safe-mode banner is the existing pre-flight signal and must
    # still be there — the reload button is a complement, not a replacement.
    assert 'data-role="v7.safe_mode_banner"' in html


def test_camera_runtime_js_wires_reload_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/ui-assets/v7/camera_runtime.js")
    assert response.status_code == 200
    js = response.text

    # The endpoint and the action binding are both the public contract
    # between the JS and the operator console.
    assert "/api/v1/cameras/reload" in js
    assert "v7-reload-cameras" in js
    # The badge renderer must read the new payload field.
    assert "v7.camera.hot_plug.status" in js
