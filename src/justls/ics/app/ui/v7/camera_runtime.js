(function () {
  "use strict";

  const STATUS_ENDPOINT = "/api/v1/cameras/status";
  const START_ENDPOINT = "/api/v1/cameras/slit/preview/start";
  const STOP_ENDPOINT = "/api/v1/cameras/slit/preview/stop";
  const RELOAD_ENDPOINT = "/api/v1/cameras/reload";
  const SLIT_FRAME_ENDPOINT = "/camera/slit/latest.jpg";
  const HOTPLUG_REFRESH_MS = 10000;
  const runtime = {
    slitEnabled: true,
    timer: null,
    hotplugTimer: null,
    localFrames: 0,
    latestScienceExpId: null,
    lastHotplugRender: null,
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

  function hotplugBadge() {
    return document.querySelector('[data-bind="v7.camera.hot_plug.status"]');
  }

  function reloadButton() {
    return document.querySelector('[data-role="v7-reload-cameras"]');
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

  function renderSafeModeBanner(service) {
    const banner = document.querySelector('[data-role="v7.safe_mode_banner"]');
    if (!banner) return;
    if (service && service.force_sim) {
      banner.hidden = false;
      const detail = document.querySelector('[data-bind="v7.safe_mode_detail"]');
      if (detail && service.message) detail.textContent = service.message;
    } else {
      banner.hidden = true;
    }
  }

  function renderHotPlug(hotPlug) {
    const badge = hotplugBadge();
    if (!badge) return;
    runtime.lastHotplugRender = hotPlug;
    if (!hotPlug) {
      badge.textContent = "USB monitor: unavailable";
      badge.className = "badge idle";
      return;
    }
    if (hotPlug.last_error) {
      badge.textContent = `USB monitor: error · ${hotPlug.last_error}`;
      badge.className = "badge error";
      return;
    }
    if (!hotPlug.enabled) {
      badge.textContent = "USB monitor: not running";
      badge.className = "badge idle";
      return;
    }
    const count = hotPlug.last_count === null || hotPlug.last_count === undefined
      ? "?"
      : String(hotPlug.last_count);
    if (hotPlug.last_change_at) {
      badge.textContent = `USB changed at ${hotPlug.last_change_at} (${count} cameras)`;
      badge.className = "badge warn";
    } else {
      badge.textContent = `USB monitor: OK · ${count} cameras · last ${hotPlug.last_check_at || "—"}`;
      badge.className = "badge live";
    }
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

  async function reloadCameras() {
    // A reload releases every camera handle and re-binds. During the brief
    // window any in-flight exposure is aborted; we confirm with the operator
    // so an accidental click cannot trash a sequence.
    const button = reloadButton();
    const accepted = window.confirm(
      "Reload Cameras will release every camera handle and re-bind to the SDK. " +
      "Any in-flight exposure will be discarded. Continue?"
    );
    if (!accepted) return;
    if (button) {
      button.disabled = true;
      const previous = button.textContent;
      button.textContent = "Reloading…";
      try {
        const response = await fetch(RELOAD_ENDPOINT, {
          method: "POST",
          headers: { Accept: "application/json" },
          cache: "no-store",
        });
        if (!response.ok) {
          const detail = await response.text();
          throw new Error(`HTTP ${response.status} · ${detail.slice(0, 120)}`);
        }
        await loadCameraStatus({ force: true });
        button.textContent = "Reloaded ✓";
        window.setTimeout(() => { button.textContent = previous; }, 3000);
      } catch (error) {
        button.textContent = "Reload failed";
        window.setTimeout(() => { button.textContent = previous; }, 3000);
        window.alert(`Reload failed: ${error && error.message || error}`);
      } finally {
        if (button) button.disabled = false;
      }
    }
  }

  async function loadCameraStatus(options) {
    const opts = options || {};
    try {
      const response = await fetch(STATUS_ENDPOINT, { headers: { Accept: "application/json" }, cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      renderSlitStatus(payload.slit_camera);
      renderSafeModeBanner(payload.service);
      renderHotPlug(payload.hot_plug);
    } catch (error) {
      setBinding("v7.camera.slit.state", `unavailable: ${error && error.message || "request failed"}`);
      if (opts.force) {
        // When the operator explicitly asks for a reload, surface the
        // failure in the badge so it is not silently swallowed.
        renderHotPlug({ enabled: false, last_error: `status fetch failed: ${error.message}` });
      }
    }
  }

  function scheduleHotPlugRefresh() {
    if (runtime.hotplugTimer) window.clearInterval(runtime.hotplugTimer);
    runtime.hotplugTimer = window.setInterval(() => loadCameraStatus(), HOTPLUG_REFRESH_MS);
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
    const button = reloadButton();
    if (button && !button.dataset.bound) {
      button.dataset.bound = "true";
      button.addEventListener("click", reloadCameras);
    }
    window.addEventListener("justls:v7-observe-state", (event) => refreshScienceFrame(event.detail));
    loadCameraStatus();
    scheduleHotPlugRefresh();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
