(function () {
  "use strict";

  const STATUS_ENDPOINT = "/api/v1/cameras/status";
  const START_ENDPOINT = "/api/v1/cameras/slit/preview/start";
  const STOP_ENDPOINT = "/api/v1/cameras/slit/preview/stop";
  const SLIT_FRAME_ENDPOINT = "/camera/slit/latest.jpg";
  const runtime = {
    slitEnabled: true,
    timer: null,
    localFrames: 0,
    latestScienceExpId: null,
  };

  function setBinding(name, value) {
    document.querySelectorAll(`[data-bind="${name}"]`).forEach((node) => {
      node.textContent = value;
    });
  }

  function slitImage() {
    return document.querySelector('[data-role="slit-preview-image"]');
  }

  function slitToggle() {
    return document.querySelector('[data-role="slit-preview-enabled"]');
  }

  function scheduleSlitFrames() {
    if (runtime.timer) window.clearInterval(runtime.timer);
    runtime.timer = null;
    if (!runtime.slitEnabled) return;
    refreshSlitFrame();
    runtime.timer = window.setInterval(refreshSlitFrame, 1500);
  }

  function refreshSlitFrame() {
    if (!runtime.slitEnabled) return;
    const image = slitImage();
    if (!image) return;
    image.src = `${SLIT_FRAME_ENDPOINT}?frame=${Date.now()}`;
  }

  function renderSlitStatus(status) {
    runtime.slitEnabled = Boolean(status && status.preview_enabled);
    runtime.localFrames = Number(status && status.sequence || 0);
    const toggle = slitToggle();
    if (toggle) toggle.checked = runtime.slitEnabled;
    setBinding("v7.camera.slit.state", status && status.state || "unavailable");
    setBinding("v7.camera.slit.sequence", status && status.sequence !== undefined ? status.sequence : "not available");
    scheduleSlitFrames();
  }

  async function setSlitPreview(enabled) {
    const toggle = slitToggle();
    if (toggle) toggle.disabled = true;
    try {
      const response = await fetch(enabled ? START_ENDPOINT : STOP_ENDPOINT, {
        method: "POST",
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      const status = await response.json();
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      renderSlitStatus(status);
    } catch (error) {
      setBinding("v7.camera.slit.state", `unavailable: ${error && error.message || "request failed"}`);
    } finally {
      if (toggle) toggle.disabled = false;
    }
  }

  async function loadCameraStatus() {
    try {
      const response = await fetch(STATUS_ENDPOINT, { headers: { Accept: "application/json" }, cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      renderSlitStatus(payload.slit_camera);
    } catch (error) {
      setBinding("v7.camera.slit.state", `unavailable: ${error && error.message || "request failed"}`);
    }
  }

  function refreshScienceFrame(status) {
    const last = status && status.last_exposure;
    const expId = last && last.exp_id;
    if (!expId || expId === runtime.latestScienceExpId || last.discarded) return;
    runtime.latestScienceExpId = expId;
    document.querySelectorAll('[data-role="science-channel-image"]').forEach((image) => {
      const base = image.dataset.icsCameraSrc;
      image.src = `${base}?exp=${encodeURIComponent(expId)}&frame=${Date.now()}`;
      image.style.display = "";
    });
  }

  function start() {
    const toggle = slitToggle();
    if (toggle && !toggle.dataset.bound) {
      toggle.dataset.bound = "true";
      toggle.addEventListener("change", () => setSlitPreview(toggle.checked));
    }
    const image = slitImage();
    if (image) {
      image.addEventListener("load", () => {
        runtime.localFrames += 1;
        setBinding("v7.camera.slit.sequence", runtime.localFrames);
      });
      image.addEventListener("error", () => setBinding("v7.camera.slit.state", runtime.slitEnabled ? "unavailable" : "stopped"));
    }
    document.querySelectorAll('[data-role="science-channel-image"]').forEach((image) => {
      image.addEventListener("error", () => { image.style.display = "none"; });
    });
    window.addEventListener("justls:v7-observe-state", (event) => refreshScienceFrame(event.detail));
    loadCameraStatus();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
