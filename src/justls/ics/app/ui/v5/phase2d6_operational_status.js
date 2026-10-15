// Phase 2.6 operational status adapter for the stable v5 /ui shell.
//
// This file is intentionally kept under ui/v5/ because it serves the default
// ui_alpha_skeleton_v5.html route, not the v7 operator console.

(function () {
  "use strict";

  const STATUS_URL = "/api/v1/status/full";
  const POLL_INTERVAL_MS = 1500;
  const STATUS_TIMEOUT_MS = 1200;
  const LEVEL_TO_RAIL = {
    ok: "success",
    busy: "info",
    warning: "warning",
    error: "error",
  };

  let statusRefreshInFlight = false;

  function byBind(name) {
    return document.querySelector(`[data-bind="${name}"]`);
  }

  function byState(name) {
    return document.querySelector(`[data-state="${name}"]`);
  }

  function setText(selector, value) {
    const el = typeof selector === "string" ? document.querySelector(selector) : selector;
    if (el) el.textContent = value == null ? "—" : String(value);
  }

  function bind(name, value) {
    setText(byBind(name), value);
  }

  function normalizeLevel(level) {
    return level === "ok" || level === "busy" || level === "warning" || level === "error" ? level : "warning";
  }

  function ensureOperationalPanel() {
    let panel = document.querySelector("[data-phase2d6-operational-panel]");
    if (panel) return panel;

    const rail = document.querySelector(".message-rail");
    panel = document.createElement("div");
    panel.setAttribute("data-phase2d6-operational-panel", "true");
    panel.innerHTML = `
      <span class="mini-badge" data-phase2d6-level>Operational: pending</span>
      <span class="mini-badge" data-phase2d6-exposure>Exposure: unknown</span>
      <span class="mini-badge" data-phase2d6-control>Control: unknown</span>
    `;
    panel.style.display = "flex";
    panel.style.flexWrap = "wrap";
    panel.style.gap = "8px";
    panel.style.margin = "10px 18px";

    if (rail && rail.parentElement) rail.parentElement.insertBefore(panel, rail.nextSibling);
    else document.body.prepend(panel);
    return panel;
  }

  function updateRail(operational) {
    const level = normalizeLevel(operational.level);
    const railLevel = LEVEL_TO_RAIL[level] || "info";
    const rail = document.querySelector(".message-rail");
    if (!rail) return;
    rail.setAttribute("data-level", railLevel);
    const body = rail.querySelector(".rail-body-text") || rail.querySelector(".rail-body");
    if (body) body.textContent = operational.summary || "Operational status updated.";
  }

  function setDegradedRail(message) {
    const rail = document.querySelector(".message-rail");
    if (!rail) return;
    rail.setAttribute("data-level", "warning");
    const body = rail.querySelector(".rail-body-text") || rail.querySelector(".rail-body");
    if (body) body.textContent = message || "Operational status refresh degraded.";
  }

  function updateConnectionBlock(data, responseTimeMs, requestId) {
    const operational = data.operational_status || {};
    const level = normalizeLevel(operational.level);
    const dot = byState("conn.dot");
    const state = byBind("conn.state");

    if (dot) {
      dot.classList.remove("ok", "warn", "err", "info");
      dot.classList.add(level === "ok" ? "ok" : level === "busy" ? "info" : level === "warning" ? "warn" : "err");
    }
    if (state) state.textContent = level === "ok" ? "Ready" : level.toUpperCase();

    bind("conn.rtt", `${Math.round(responseTimeMs)} ms`);
    bind("conn.last_ok", new Date().toLocaleTimeString());
    bind("conn.poll", `${(POLL_INTERVAL_MS / 1000).toFixed(1)} s`);
    if (operational.stale_threshold_s != null) bind("conn.staleThreshold", `${operational.stale_threshold_s.toFixed(1)} s`);
    if (requestId) {
      const panel = ensureOperationalPanel();
      panel.dataset.lastRequestId = requestId;
      panel.title = `Last X-Request-ID: ${requestId}`;
    }
  }

  function updateOperationalPanel(data) {
    const operational = data.operational_status || {};
    const panel = ensureOperationalPanel();
    setText(panel.querySelector("[data-phase2d6-level]"), `Operational: ${normalizeLevel(operational.level).toUpperCase()}`);
    setText(panel.querySelector("[data-phase2d6-exposure]"), `Exposure: ${operational.exposure_state || "unknown"}`);
    setText(panel.querySelector("[data-phase2d6-control]"), `Control: ${operational.control_state || "unknown"}`);
  }

  function updateStatusFullFields(data) {
    const state = data.state || {};
    const detectorConfig = data.detector_config || {};
    const calibration = data.calibration || {};
    const observation = data.observation || {};

    bind("runtime.mode", data.run_mode || data.hal || "unknown");
    bind("api.base", window.location.origin || "same-origin");
    bind("state.slit_width_um", state.slit_width_um == null ? "—" : `${state.slit_width_um} µm`);
    bind("state.slit_angle_deg", state.slit_angle_deg == null ? "—" : `${state.slit_angle_deg}°`);
    bind("state.lamp_on", state.lamp_on ? "on" : "off");
    bind("detector.profile", detectorConfig.profile_name || "—");
    bind("calibration.mode", calibration.mode || "—");
    bind("observation.state", observation.state || "—");

    const debugEl = byBind("debug.status");
    if (debugEl && !debugEl.dataset.phase2d6CommandOutput) {
      debugEl.textContent = JSON.stringify(
        {
          operational_status: data.operational_status,
          observation: data.observation,
          detector_config: data.detector_config,
          timestamp_utc: data.timestamp_utc,
        },
        null,
        2,
      );
    }
  }

  async function fetchStatusWithTimeout() {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), STATUS_TIMEOUT_MS);
    try {
      return await fetch(STATUS_URL, {
        cache: "no-store",
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });
    } finally {
      window.clearTimeout(timeoutId);
    }
  }

  async function refreshOperationalStatus() {
    if (statusRefreshInFlight) return;
    statusRefreshInFlight = true;
    const t0 = performance.now();
    try {
      const response = await fetchStatusWithTimeout();
      const requestId = response.headers.get("X-Request-ID") || "";
      const data = await response.json();
      const responseTimeMs = performance.now() - t0;
      if (!response.ok) throw new Error(data?.detail?.message || `Status refresh failed: ${response.status}`);
      updateRail(data.operational_status || {});
      updateConnectionBlock(data, responseTimeMs, requestId);
      updateOperationalPanel(data);
      updateStatusFullFields(data);
    } finally {
      statusRefreshInFlight = false;
    }
  }

  function start() {
    ensureOperationalPanel();
    refreshOperationalStatus().catch((err) => {
      setDegradedRail(err.name === "AbortError" ? "Operational status refresh timed out." : err.message);
    });
    window.setInterval(() => {
      refreshOperationalStatus().catch((err) => {
        setDegradedRail(err.name === "AbortError" ? "Operational status refresh timed out." : err.message);
      });
    }, POLL_INTERVAL_MS);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
