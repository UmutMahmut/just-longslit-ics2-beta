// v7 opt-in runtime status adapter.
// Default /ui/v7 remains static. This script is injected only when
// JUSTLS_UI_V7_RUNTIME_ENABLED=1.

(function () {
  "use strict";

  const GLOBAL_KEY = "__JUSTLS_V7_RUNTIME_STATUS__";
  const STATUS_ENDPOINT = "/api/v1/status/full";
  const POLL_MS = 2000;
  const RAW_MAX_CHARS = 12000;

  const runtime = window[GLOBAL_KEY] || {
    started: false,
    intervalId: null,
    refreshInFlight: false,
    lastOkAt: null,
    lastError: null,
    lastRequestId: null,
    lastRttMs: null,
    connectionState: "static",
    refreshCount: 0,
  };
  window[GLOBAL_KEY] = runtime;

  function text(value, fallback) {
    if (value === null || value === undefined || value === "") return fallback;
    return String(value);
  }

  function setNodeText(node, value, fallback) {
    if (!node) return;
    const next = text(value, fallback);
    if (node.textContent !== next) node.textContent = next;
  }

  function setText(selector, value, fallback) {
    document.querySelectorAll(selector).forEach((node) => setNodeText(node, value, fallback));
  }

  function setTopStatusText(id, value, fallback) {
    setNodeText(document.getElementById(id), value, fallback);
  }

  function panel(id, title, pageSelector) {
    const existing = document.getElementById(id);
    if (existing) return existing;

    const host = pageSelector ? document.querySelector(pageSelector) : document.querySelector(".workspace");
    if (!host) return null;

    const section = document.createElement("section");
    section.id = id;
    section.className = "panel";
    section.setAttribute("data-role", id);
    section.setAttribute("data-phase", "2.8-runtime-opt-in");
    section.innerHTML = `<h2>${title}</h2><div class="panel-body"></div>`;
    host.insertBefore(section, host.firstChild);
    return section;
  }

  function preparePanelBody(section, html) {
    if (!section) return null;
    const body = section.querySelector(".panel-body");
    if (!body) return null;
    if (body.dataset.ready) return body;
    if (body.querySelector("[data-bind]")) {
      body.dataset.ready = "true";
      return body;
    }
    body.dataset.ready = "true";
    body.innerHTML = html;
    return body;
  }

  function ensureRuntimePanel() {
    const section = panel("v7-runtime-status", "Runtime Status · /api/v1/status/full", '[data-page-panel="diagnostics"]');
    preparePanelBody(section, `
        <dl class="kv">
          <dt>Connection</dt><dd><code data-bind="v7.connection">connecting</code></dd>
          <dt>Run Mode</dt><dd><code data-bind="v7.run_mode">unknown</code></dd>
          <dt>Operational</dt><dd><code data-bind="v7.operational">unknown</code></dd>
          <dt>Exposure</dt><dd><code data-bind="v7.exposure_state">unknown</code></dd>
          <dt>Detector Profile</dt><dd><code data-bind="v7.detector_profile">unknown</code></dd>
          <dt>Latest Job</dt><dd><code data-bind="v7.latest_job">not available</code></dd>
          <dt>X-Request-ID</dt><dd><code data-bind="v7.request_id">not available</code></dd>
          <dt>RTT</dt><dd><code data-bind="v7.connection.rtt_ms">not measured</code></dd>
          <dt>Last OK</dt><dd><code data-bind="v7.connection.last_ok_at">not available</code></dd>
          <dt>Runtime Polls</dt><dd><code data-bind="v7.runtime_status.refresh_count">0</code></dd>
        </dl>`);
    return section;
  }

  function ensureSetupPanel() {
    const section = panel("v7-setup-readiness", "Setup Readiness · Current Context", '[data-page-panel="setup"]');
    preparePanelBody(section, `
        <dl class="kv">
          <dt>Run Mode</dt><dd><code data-bind="v7.setup.run_mode">unknown</code></dd>
          <dt>Operational</dt><dd><code data-bind="v7.setup.operational">unknown</code></dd>
          <dt>Observation State</dt><dd><code data-bind="v7.setup.observation_state">unknown</code></dd>
          <dt>Detector Profile</dt><dd><code data-bind="v7.setup.detector_profile">unknown</code></dd>
        </dl>`);
    return section;
  }

  function ensureRawPreview() {
    const section = panel("v7-raw-status-preview", "Raw Status Preview · /api/v1/status/full", '[data-page-panel="diagnostics"]');
    preparePanelBody(section, `<pre data-bind="v7.raw_status_preview">waiting for status/full...</pre>`);
    return section;
  }

  function latestJobLabel(data) {
    const job = data && data.latest_job;
    if (!job) return "not available";
    return [job.status, job.subsystem, job.action, job.job_id].filter(Boolean).join(" · ");
  }

  function operationalLabel(operational) {
    return operational.level || operational.state || operational.summary || "unknown";
  }

  function exposureLabel(observation) {
    return observation.state || observation.observation_state || "unknown";
  }

  function booleanLabel(value, fallback) {
    if (value === true) return "enabled";
    if (value === false) return "disabled";
    return fallback;
  }

  function channelObject(detector, channel) {
    const channels = detector.channels || detector.channel_state || detector.channel_states || {};
    return channels[channel] || channels[channel.toLowerCase()] || {};
  }

  function channelEnabledLabel(detector, channel) {
    return booleanLabel(channelObject(detector, channel).enabled, "placeholder");
  }

  function roleValue(detector, channel, fallback) {
    const roles = detector.channel_roles || detector.role_mapping || detector.roles || {};
    return text(roles[channel] || roles[channel.toLowerCase()], fallback);
  }

  function requestIdFrom(response) {
    return response.headers.get("X-Request-ID") || response.headers.get("x-request-id") || null;
  }

  function rttLabel() {
    return runtime.lastRttMs === null || runtime.lastRttMs === undefined ? "not measured" : `${runtime.lastRttMs} ms`;
  }

  function connectionLabel() {
    const parts = [runtime.connectionState || "unknown"];
    if (runtime.lastRttMs !== null && runtime.lastRttMs !== undefined) parts.push(rttLabel());
    if (runtime.lastOkAt) parts.push(`last OK ${runtime.lastOkAt}`);
    return parts.join(" · ");
  }

  function severityForState() {
    if (runtime.connectionState === "connected") return "success";
    if (runtime.connectionState === "degraded") return "warning";
    if (runtime.connectionState === "error") return "error";
    return "info";
  }

  function bindTopStatusCards(data, operational, observation) {
    setTopStatusText("run-mode", data.run_mode, "unknown");
    setTopStatusText("operational-level", operationalLabel(operational), "unknown");
    setTopStatusText("exposure-state", exposureLabel(observation), "unknown");
  }

  function bindSetup(data, operational, observation, detector) {
    setText('[data-bind="v7.setup.run_mode"]', data.run_mode, "unknown");
    setText('[data-bind="v7.setup.operational"]', operationalLabel(operational), "unknown");
    setText('[data-bind="v7.setup.observation_state"]', exposureLabel(observation), "unknown");
    setText('[data-bind="v7.setup.detector_profile"]', detector.profile_name, "unknown");
  }

  function bindInstrument(data, detector) {
    const calibration = data.calibration || data.calibration_status || {};
    const slit = data.slit || data.slit_status || {};
    const bEnabled = channelEnabledLabel(detector, "B");
    const gEnabled = channelEnabledLabel(detector, "G");
    const rEnabled = channelEnabledLabel(detector, "R");

    setText('[data-bind="v7.instrument.current_preset"]', data.current_preset || data.active_preset, "unknown");
    setText('[data-bind="v7.instrument.mode"]', calibration.mode || calibration.state, "unknown");
    setText('[data-bind="v7.instrument.slit_width"]', slit.width_arcsec || slit.width || slit.slit_width, "not wired");
    setText('[data-bind="v7.instrument.slit_angle"]', slit.angle_deg || slit.angle || slit.slit_angle, "not wired");
    setText('[data-bind="v7.instrument.detector_profile"]', detector.profile_name, "unknown");
    setText('[data-bind="v7.instrument.bgr_readiness"]', `B: ${bEnabled} · G: ${gEnabled} · R: ${rEnabled}`, "placeholder");
    setText('[data-bind="v7.instrument.slit.width_current"]', slit.width_arcsec || slit.width || slit.slit_width, "not wired");
    setText('[data-bind="v7.instrument.slit.angle_current"]', slit.angle_deg || slit.angle || slit.slit_angle, "not wired");
    setText('[data-bind="v7.instrument.calibration.mode"]', calibration.mode || calibration.state, "unknown");
    setText('[data-bind="v7.instrument.calibration.flat"]', calibration.flat_lamp || calibration.flat || "off", "off");
    setText('[data-bind="v7.instrument.calibration.arc"]', calibration.arc_lamp || calibration.lamp || "not wired", "not wired");
    setText('[data-bind="v7.instrument.detector.profile"]', detector.profile_name, "unknown");
    setText('[data-bind="v7.instrument.detector.save_enabled"]', booleanLabel(detector.save_enabled, "unknown"), "unknown");
    setText('[data-bind="v7.instrument.detector.trigger_mode"]', detector.trigger_mode, "unknown");
    setText('[data-bind="v7.instrument.detector.readout_mode"]', detector.readout_mode, "unknown");
    setText('[data-bind="v7.instrument.channel.B.enabled"]', bEnabled, "placeholder");
    setText('[data-bind="v7.instrument.channel.G.enabled"]', gEnabled, "placeholder");
    setText('[data-bind="v7.instrument.channel.R.enabled"]', rEnabled, "placeholder");
    setText('[data-bind="v7.instrument.channel.B.role"]', roleValue(detector, "B", "science_b"), "science_b");
    setText('[data-bind="v7.instrument.channel.G.role"]', roleValue(detector, "G", "science_g"), "science_g");
    setText('[data-bind="v7.instrument.channel.R.role"]', roleValue(detector, "R", "science_r"), "science_r");
  }

  function bindConnectionDiagnostics() {
    setText('[data-bind="v7.connection"]', connectionLabel(), "unknown");
    setText('[data-bind="v7.connection.state"]', runtime.connectionState, "unknown");
    setText('[data-bind="v7.connection.rtt_ms"]', rttLabel(), "not measured");
    setText('[data-bind="v7.connection.last_ok_at"]', runtime.lastOkAt || "not available", "not available");
    setText('[data-bind="v7.request_id"]', runtime.lastRequestId || "not available", "not available");
    setText('[data-bind="v7.last_error"]', runtime.lastError || "none", "none");
  }

  function bindDiagnostics(data) {
    setText('[data-bind="v7.run_mode"]', data.run_mode, "unknown");
    setText('[data-bind="v7.runtime_status.refresh_count"]', runtime.refreshCount, "0");
    setText('[data-bind="v7.latest_job"]', latestJobLabel(data), "not available");
    const observation = data.observation || {};
    const record = observation.latest_exposure_record || (observation.observation_meta && observation.observation_meta.exposure_record) || null;
    const sequence = data.observation_sequence || null;
    setText('[data-bind="v7.diagnostics.data_provenance"]', record ? `${record.simulated ? "SIMULATED" : "REAL"} - ${record.data_product_state || "unknown"}` : "no exposure record", "no exposure record");
    setText('[data-bind="v7.diagnostics.latest_fits"]', record && record.primary_data_product ? `${record.primary_data_product.state}: ${record.primary_data_product.uri || "no URI"}` : "not created", "not created");
    setText('[data-bind="v7.diagnostics.latest_quicklook"]', record && record.quicklook ? `${record.quicklook.state}: ${record.quicklook.uri || "no URI"}` : "not created", "not created");
    setText('[data-bind="v7.diagnostics.sequence"]', sequence ? `${sequence.state} - step ${Math.min(sequence.current_index + 1, sequence.plan.exposures.length)}/${sequence.plan.exposures.length}` : "not loaded", "not loaded");
    bindConnectionDiagnostics();
    let raw = JSON.stringify(data, null, 2);
    if (raw.length > RAW_MAX_CHARS) raw = `${raw.slice(0, RAW_MAX_CHARS)}\n... truncated ...`;
    setText('[data-bind="v7.raw_status_preview"]', raw, raw);
  }

  function bindMessage(message, phase, severity) {
    const resolvedSeverity = severity || severityForState();
    setText('[data-bind="v7.message.text"]', message, message);
    setText('[data-bind="v7.message.phase"]', phase, phase);
    setText('[data-bind="v7.message.severity"]', resolvedSeverity, resolvedSeverity);
    setText('[data-bind="v7.message.connection"]', runtime.connectionState || "unknown", "unknown");
    setText('[data-bind="v7.message.rtt_ms"]', rttLabel(), "not measured");
    setText('[data-bind="v7.message.last_ok_at"]', runtime.lastOkAt || "not available", "not available");
    setText('[data-bind="v7.message.request_id"]', runtime.lastRequestId || "not available", "not available");
    setText('[data-bind="v7.message.poll_count"]', runtime.refreshCount, "0");
    setText('[data-bind="v7.message.freshness"]', runtime.lastOkAt ? "fresh" : "not available", "not available");
    document.querySelectorAll('[data-role="v7-message-rail"]').forEach((rail) => {
      rail.setAttribute("data-severity", resolvedSeverity);
      rail.setAttribute("data-connection", runtime.connectionState || "unknown");
      if (runtime.lastRequestId) rail.setAttribute("data-request-id", runtime.lastRequestId);
      if (runtime.lastRttMs !== null && runtime.lastRttMs !== undefined) rail.setAttribute("data-rtt-ms", String(runtime.lastRttMs));
    });
  }

  function bind(data) {
    ensureRuntimePanel();
    ensureSetupPanel();
    ensureRawPreview();
    const observation = data.observation || {};
    const operational = data.operational_status || {};
    const detector = data.detector_config || {};
    bindTopStatusCards(data, operational, observation);
    setText('[data-bind="v7.operational"]', operationalLabel(operational), "unknown");
    setText('[data-bind="v7.exposure_state"]', exposureLabel(observation), "unknown");
    setText('[data-bind="v7.detector_profile"]', detector.profile_name, "unknown");
    bindSetup(data, operational, observation, detector);
    bindInstrument(data, detector);
    bindDiagnostics(data);
    bindMessage(`Runtime status connected · ${rttLabel()} · request ${runtime.lastRequestId || "not available"}`, "Phase 2.9-F", "success");
  }

  async function refresh() {
    if (runtime.refreshInFlight) return;
    runtime.refreshInFlight = true;
    const startedAt = typeof performance !== "undefined" && performance.now ? performance.now() : Date.now();
    try {
      const response = await fetch(STATUS_ENDPOINT, { cache: "no-store", headers: { Accept: "application/json" } });
      const finishedAt = typeof performance !== "undefined" && performance.now ? performance.now() : Date.now();
      runtime.lastRttMs = Math.max(0, Math.round(finishedAt - startedAt));
      runtime.lastRequestId = requestIdFrom(response) || runtime.lastRequestId;
      const data = await response.json();
      runtime.refreshCount += 1;
      if (response.ok) {
        runtime.connectionState = "connected";
        runtime.lastOkAt = new Date().toISOString();
        runtime.lastError = null;
        bind(data);
      } else {
        runtime.connectionState = "degraded";
        runtime.lastError = `HTTP ${response.status}`;
        bindConnectionDiagnostics();
        bindMessage(`Runtime status degraded · HTTP ${response.status} · ${rttLabel()}`, "Diagnostics", "warning");
      }
    } catch (error) {
      const finishedAt = typeof performance !== "undefined" && performance.now ? performance.now() : Date.now();
      runtime.lastRttMs = Math.max(0, Math.round(finishedAt - startedAt));
      runtime.connectionState = "error";
      runtime.lastError = text(error && error.message, "fetch failed");
      bindConnectionDiagnostics();
      bindMessage(`Runtime status fetch failed: ${runtime.lastError}`, "Diagnostics", "error");
    } finally {
      runtime.refreshInFlight = false;
    }
  }

  function start() {
    ensureRuntimePanel();
    ensureSetupPanel();
    ensureRawPreview();
    bindConnectionDiagnostics();
    bindMessage("Runtime status initializing...", "Phase 2.9-F", "info");
    window.addEventListener("justls:v7-local-refresh", refresh);
    if (runtime.started) {
      refresh();
      return;
    }
    runtime.started = true;
    refresh();
    runtime.intervalId = window.setInterval(refresh, POLL_MS);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
