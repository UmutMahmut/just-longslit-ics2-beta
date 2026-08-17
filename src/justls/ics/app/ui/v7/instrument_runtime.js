// v7 opt-in Instrument runtime adapter.
// Injected only when JUSTLS_UI_V7_RUNTIME_ENABLED=1 and
// JUSTLS_UI_V7_INSTRUMENT_RUNTIME_ENABLED=1.

(function () {
  "use strict";

  const GLOBAL_KEY = "__JUSTLS_V7_INSTRUMENT_RUNTIME__";
  const SLIT_ENDPOINT = "/api/v1/slit";
  const SLIT_ANGLE_ENDPOINT = "/api/v1/slit_angle";
  const CALIBRATION_STATUS_ENDPOINT = "/api/v1/calibration/status";
  const CALIBRATION_MODE_ENDPOINT = "/api/v1/calibration/mode";
  const CALIBRATION_LAMP_ENDPOINT = "/api/v1/calibration/lamp";
  const DETECTOR_CONFIG_ENDPOINT = "/api/v1/detector/config";

  const SLIT_UM_PER_ARCSEC = 128.34;
  const COMMON_SLIT_WIDTH_ARCSEC = [1.0, 1.5, 2.0, 3.0];

  const runtime = window[GLOBAL_KEY] || {
    started: false,
    busy: false,
    lastCommand: null,
    lastResult: null,
    lastError: null,
    lastRequestId: null,
  };
  window[GLOBAL_KEY] = runtime;

  function text(value, fallback) {
    if (value === null || value === undefined || value === "") return fallback;
    return String(value);
  }

  function panel() {
    return document.getElementById("v7-instrument-controls");
  }

  function setText(node, value) {
    if (!node) return;
    const next = text(value, "");
    if (node.textContent !== next) node.textContent = next;
  }

  function bind(name) {
    const host = panel();
    return host ? host.querySelector(`[data-bind="${name}"]`) || document.querySelector(`[data-bind="${name}"]`) : document.querySelector(`[data-bind="${name}"]`);
  }

  function byRole(role) {
    const host = panel();
    return host && host.querySelector(`[data-role="${role}"]`);
  }

  function requestIdFrom(response) {
    return response.headers.get("x-request-id") || response.headers.get("X-Request-ID") || runtime.lastRequestId;
  }

  function umFromArcsec(arcsec) {
    return arcsec * SLIT_UM_PER_ARCSEC;
  }

  function arcsecFromUm(um) {
    return um / SLIT_UM_PER_ARCSEC;
  }

  function formatNumber(value, digits) {
    if (!Number.isFinite(value)) return "";
    return Number(value.toFixed(digits)).toString();
  }

  function latestJobLabel(payload) {
    const job = payload && payload.latest_job;
    if (!job) return "not available";
    return [job.status, job.subsystem, job.action, job.job_id].filter(Boolean).join(" · ");
  }

  function ensurePanelLayout() {
    const host = panel();
    if (!host || host.querySelector('[data-role="instrument-slit-width-arcsec"]')) return host;

    host.innerHTML = `
      <h2>Instrument Controls · Slit / Calibration / Detector</h2>
      <div class="panel-body grid">
        <div class="grid grid-3">
          <section class="panel compact-panel" data-role="instrument-slit-controls">
            <h3>Slit</h3>
            <div class="panel-body">
              <div class="field-grid">
                <label>Width (arcsec)<input type="number" min="0.001" step="0.001" value="1.0" data-role="instrument-slit-width-arcsec" /></label>
                <label>Width (um)<input type="number" min="0.001" step="0.001" value="128.34" data-role="instrument-slit-width-um" /></label>
                <label>Angle (deg)<input type="number" min="-90" max="90" step="0.001" value="0" data-role="instrument-slit-angle-deg" /></label>
                <button class="btn primary" type="button" data-action="instrument-set-slit-width" disabled>Set Width</button>
                <button class="btn" type="button" data-action="instrument-set-slit-angle" disabled>Set Angle</button>
              </div>
              <dl class="kv compact-kv" style="margin-top: 8px;">
                <dt>Current Width</dt><dd><code data-bind="v7.instrument.slit.width_current">not connected</code></dd>
                <dt>Current Angle</dt><dd><code data-bind="v7.instrument.slit.angle_current">not connected</code></dd>
                <dt>Conversion</dt><dd><code>1 arcsec = <span data-bind="v7.instrument.slit.conversion_um_per_arcsec">128.34</span> um</code></dd>
              </dl>
              <div class="badge-row" data-role="instrument-slit-shortcuts" aria-label="common slit width shortcuts" style="margin-top: 8px;">
                <button class="btn" type="button" data-role="instrument-slit-shortcut" data-arcsec="1.0" disabled>1.0"</button>
                <button class="btn" type="button" data-role="instrument-slit-shortcut" data-arcsec="1.5" disabled>1.5"</button>
                <button class="btn" type="button" data-role="instrument-slit-shortcut" data-arcsec="2.0" disabled>2.0"</button>
                <button class="btn" type="button" data-role="instrument-slit-shortcut" data-arcsec="3.0" disabled>3.0"</button>
              </div>
            </div>
          </section>

          <section class="panel compact-panel" data-role="instrument-calibration-controls">
            <h3>Calibration</h3>
            <div class="panel-body">
              <div class="field-grid">
                <label>Mode<select data-role="instrument-calibration-mode"><option value="science">science</option><option value="calibration">calibration</option></select></label>
                <label>Lamp<select data-role="instrument-calibration-lamp"><option value="flat">flat</option><option value="arc_hgar">arc_hgar</option><option value="arc_ne">arc_ne</option></select></label>
                <button class="btn" type="button" data-action="instrument-set-calibration-mode" disabled>Set Mode</button>
                <button class="btn" type="button" data-action="instrument-set-calibration-lamp" disabled>Set Lamp</button>
                <label><input type="checkbox" data-role="instrument-calibration-lamp-enabled" /> Enable lamp</label>
                <button class="btn" type="button" data-action="instrument-use-calibration-frame-defaults" disabled>Use Frame-Type Defaults</button>
                <button class="btn" type="button" data-action="instrument-refresh-calibration" disabled>Refresh</button>
              </div>
              <p style="margin: 8px 0 0; color: var(--muted); font-size: 12px; line-height: 1.45;">
                Mode/Lamp must match the intended frame type. Science frames require science mode and lamps off; flat frames require calibration mode with the flat lamp; arc frames require calibration mode with an Hg(Ar) or Ne arc lamp. Dark/bias are future detector-only frames and keep lamps off.
              </p>
              <dl class="kv compact-kv" style="margin-top: 8px;">
                <dt>Mode</dt><dd><code data-bind="v7.instrument.calibration.mode">science</code></dd>
                <dt>Active Lamp</dt><dd><code data-bind="v7.instrument.calibration.active_lamp">none</code></dd>
                <dt>Lamp Enabled</dt><dd><code data-bind="v7.instrument.calibration.lamp_enabled">false</code></dd>
                <dt>Mirror / Path</dt><dd><code data-bind="v7.instrument.calibration.mirror_inserted">out</code></dd>
                <dt>Observe Frame</dt><dd><code data-bind="v7.instrument.calibration.frame_type_context">science</code></dd>
                <dt>Expected for Frame</dt><dd><code data-bind="v7.instrument.calibration.expected_for_frame">science mode + lamps off</code></dd>
                <dt>Compatibility</dt><dd><code data-bind="v7.instrument.calibration.compatibility">status not loaded</code></dd>
              </dl>
              <div class="badge-row" style="margin-top: 8px;">
                <span class="badge live">flat</span>
                <span class="badge live">Hg(Ar)</span>
                <span class="badge live">Ne</span>
                <span class="badge future">frame-type advisory</span>
                <span class="badge future">preview validation pending</span>
              </div>
            </div>
          </section>

          <section class="panel compact-panel" data-role="instrument-detector-visibility">
            <h3>Detector</h3>
            <div class="panel-body">
              <button class="btn" type="button" data-action="instrument-refresh-detector-config" disabled>Refresh Detector Config</button>
              <dl class="kv compact-kv" style="margin-top: 8px;">
                <dt>Profile</dt><dd><code data-bind="v7.instrument.detector.profile">default</code></dd>
                <dt>Save</dt><dd><code data-bind="v7.instrument.detector.save_enabled">unknown</code></dd>
                <dt>Trigger</dt><dd><code data-bind="v7.instrument.detector.trigger_mode">software</code></dd>
                <dt>Readout</dt><dd><code data-bind="v7.instrument.detector.readout_mode">normal</code></dd>
                <dt>B/G/R Hardware</dt><dd><code>read-only summary</code></dd>
              </dl>
            </div>
          </section>
        </div>

        <section class="panel compact-panel" data-role="bgr-channel-summary">
          <h3>B/G/R Channel Summary</h3>
          <div class="panel-body">
            <table class="table" aria-label="BGR channel summary">
              <thead>
                <tr><th>Channel</th><th>Enabled</th><th>Role</th><th>Coverage</th><th>Status</th></tr>
              </thead>
              <tbody>
                <tr data-channel="B">
                  <td><strong>B Channel</strong></td>
                  <td><code data-bind="v7.instrument.channel.B.enabled">pending</code></td>
                  <td><code data-bind="v7.instrument.channel.B.role">science_b</code></td>
                  <td>365–573 nm</td>
                  <td><span class="badge future">read-only</span></td>
                </tr>
                <tr data-channel="G">
                  <td><strong>G Channel</strong></td>
                  <td><code data-bind="v7.instrument.channel.G.enabled">pending</code></td>
                  <td><code data-bind="v7.instrument.channel.G.role">science_g</code></td>
                  <td>546–772 nm</td>
                  <td><span class="badge future">read-only</span></td>
                </tr>
                <tr data-channel="R">
                  <td><strong>R Channel</strong></td>
                  <td><code data-bind="v7.instrument.channel.R.enabled">pending</code></td>
                  <td><code data-bind="v7.instrument.channel.R.role">science_r</code></td>
                  <td>747–985 nm</td>
                  <td><span class="badge future">read-only</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="panel compact-panel" data-role="instrument-command-summary">
          <h3>Command Summary</h3>
          <div class="panel-body">
            <dl class="kv compact-kv">
              <dt>Last Command</dt><dd><code data-bind="v7.instrument.last_command">none</code></dd>
              <dt>Request ID</dt><dd><code data-bind="v7.instrument.request_id">not available</code></dd>
              <dt>Latest Job</dt><dd><code data-bind="v7.instrument.latest_job">not available</code></dd>
              <dt>Last Error</dt><dd><code data-bind="v7.instrument.last_error">none</code></dd>
              <dt>Runtime State</dt><dd><code data-bind="v7.instrument.runtime_state">static fallback</code></dd>
              <dt>Summary</dt><dd><code data-bind="v7.instrument.result_summary">no command yet</code></dd>
            </dl>
          </div>
        </section>

        <details class="dev-note" data-role="instrument-boundary-note">
          <summary>Implementation boundary</summary>
          <p>Routine slit and calibration controls belong here. Low-level drive recovery, power operations, and protected hardware maintenance belong to Engineer. Raw payload inspection belongs to Diagnostics.</p>
        </details>

        <details class="dev-note" data-role="instrument-raw-debug">
          <summary>Raw Result JSON · Diagnostics Detail</summary>
          <pre data-bind="v7.instrument.result">Instrument runtime is opt-in. Raw command result JSON is kept here for diagnostics.</pre>
        </details>
      </div>`;
    return host;
  }

  function setRuntimeState(value) {
    setText(bind("v7.instrument.runtime_state"), value);
  }

  function setBusy(value) {
    runtime.busy = value;
    const host = panel();
    if (host) {
      host.querySelectorAll("button[data-action], button[data-role='instrument-slit-shortcut']").forEach((button) => {
        button.disabled = value;
      });
      host.setAttribute("data-runtime-busy", value ? "true" : "false");
    }
    setRuntimeState(value ? "command in flight" : "ready");
  }

  function resultSummary(command, payload) {
    if (!payload || typeof payload !== "object") return `${command}: done`;
    if (command === "set_slit_width") {
      const widthUm = payload.width_um || payload.slit_width_um || payload.width;
      if (Number.isFinite(Number(widthUm))) return `set_slit_width: ${formatNumber(arcsecFromUm(Number(widthUm)), 3)} arcsec / ${formatNumber(Number(widthUm), 3)} um`;
    }
    if (command === "set_slit_angle") return `set_slit_angle: ${payload.angle_deg || payload.slit_angle_deg || payload.angle || "accepted"} deg`;
    if (command === "set_calibration_mode") return `set_calibration_mode: ${payload.mode || payload.calibration_mode || "accepted"}`;
    if (command === "set_calibration_lamp") return `set_calibration_lamp: ${payload.lamp || payload.active_lamp || "accepted"}`;
    if (command === "refresh_detector_config") return `refresh_detector_config: ${payload.profile_name || "profile visible"}`;
    if (command === "refresh_calibration") return `refresh_calibration: ${payload.mode || payload.calibration_mode || "status visible"}`;
    return `${command}: done`;
  }

  function renderResult(command, payload) {
    runtime.lastCommand = command;
    runtime.lastResult = payload;
    runtime.lastError = null;
    setText(bind("v7.instrument.last_command"), command);
    setText(bind("v7.instrument.request_id"), runtime.lastRequestId || "not available");
    setText(bind("v7.instrument.latest_job"), latestJobLabel(payload));
    setText(bind("v7.instrument.last_error"), "none");
    setText(bind("v7.instrument.result_summary"), resultSummary(command, payload));
    setText(bind("v7.instrument.result"), JSON.stringify({ command, request_id: runtime.lastRequestId, payload }, null, 2));
    window.dispatchEvent(new CustomEvent("justls:v7-local-refresh", { detail: { source: "instrument", command } }));
  }

  function renderError(command, error) {
    runtime.lastCommand = command;
    runtime.lastError = text(error, "failed");
    setText(bind("v7.instrument.last_command"), command || "none");
    setText(bind("v7.instrument.request_id"), runtime.lastRequestId || "not available");
    setText(bind("v7.instrument.latest_job"), latestJobLabel(runtime.lastResult));
    setText(bind("v7.instrument.last_error"), runtime.lastError);
    setText(bind("v7.instrument.result_summary"), `${command || "command"}: ${runtime.lastError}`);
    setText(bind("v7.instrument.result"), JSON.stringify({ command, request_id: runtime.lastRequestId, error: runtime.lastError }, null, 2));
  }

  function updateSlitFieldsFromUm(widthUm) {
    const value = Number(widthUm);
    if (!Number.isFinite(value) || value <= 0) return;
    const arcsec = arcsecFromUm(value);
    const arcInput = byRole("instrument-slit-width-arcsec");
    const umInput = byRole("instrument-slit-width-um");
    if (arcInput) arcInput.value = formatNumber(arcsec, 3);
    if (umInput) umInput.value = formatNumber(value, 3);
    setText(document.querySelector('[data-bind="v7.instrument.slit.width_current"]'), `${formatNumber(arcsec, 3)} arcsec / ${formatNumber(value, 3)} um`);
  }

  function observeFrameType() {
    const select = document.querySelector('[data-role="obs-frame-type"]');
    return select && select.value ? select.value : "unknown";
  }

  function calibrationRequirementForFrameType(frameType, selectedLamp) {
    const arcLamp = selectedLamp === "arc_ne" ? "arc_ne" : "arc_hgar";
    if (frameType === "science") {
      return {
        enforce: true,
        mode: "science",
        lampEnabled: false,
        mirrorInserted: false,
        label: "science mode + lamps off",
      };
    }
    if (frameType === "flat") {
      return {
        enforce: true,
        mode: "calibration",
        lampEnabled: true,
        lamp: "flat",
        defaultLamp: "flat",
        mirrorInserted: true,
        label: "calibration mode + flat lamp",
      };
    }
    if (frameType === "arc") {
      return {
        enforce: true,
        mode: "calibration",
        lampEnabled: true,
        acceptedLamps: ["arc_hgar", "arc_ne"],
        defaultLamp: arcLamp,
        mirrorInserted: true,
        label: "calibration mode + Hg(Ar)/Ne arc lamp",
      };
    }
    if (frameType === "dark" || frameType === "bias") {
      return {
        enforce: true,
        mode: "science",
        lampEnabled: false,
        mirrorInserted: false,
        label: "detector-only frame + lamps off",
      };
    }
    if (frameType === "test") {
      return {
        enforce: false,
        label: "test frame: manually verify Mode/Lamp",
      };
    }
    return {
      enforce: false,
      label: "unknown frame type: manually verify Mode/Lamp",
    };
  }

  function lampMatchesRequirement(requirement, activeLamp, lampEnabled) {
    if (!requirement.enforce) return true;
    if (requirement.lampEnabled === false) return !lampEnabled;
    if (!lampEnabled) return false;
    if (requirement.lamp) return activeLamp === requirement.lamp;
    if (requirement.acceptedLamps) return requirement.acceptedLamps.includes(activeLamp);
    return true;
  }

  function calibrationCompatibilityLabel(status) {
    if (!status) return "status not loaded";
    const frameType = observeFrameType();
    const selectedLamp = byRole("instrument-calibration-lamp");
    const requirement = calibrationRequirementForFrameType(frameType, selectedLamp && selectedLamp.value);

    if (!requirement.enforce) return requirement.label;

    const failures = [];
    if (requirement.mode && status.mode !== requirement.mode) {
      failures.push(`mode should be ${requirement.mode}`);
    }
    if (!lampMatchesRequirement(requirement, status.activeLamp, status.lampEnabled)) {
      if (requirement.lampEnabled === false) failures.push("lamp should be off");
      else if (requirement.lamp) failures.push(`lamp should be ${requirement.lamp}`);
      else if (requirement.acceptedLamps) failures.push(`lamp should be ${requirement.acceptedLamps.join(" or ")}`);
    }
    if (requirement.mirrorInserted !== undefined && status.mirrorInserted !== requirement.mirrorInserted) {
      failures.push(requirement.mirrorInserted ? "mirror/path should be inserted" : "mirror/path should be out");
    }

    return failures.length ? `mismatch: ${failures.join("; ")}` : "ok";
  }

  function renderCalibrationFrameGuidance() {
    const frameType = observeFrameType();
    const lampSelect = byRole("instrument-calibration-lamp");
    const requirement = calibrationRequirementForFrameType(frameType, lampSelect && lampSelect.value);
    setText(document.querySelector('[data-bind="v7.instrument.calibration.frame_type_context"]'), frameType);
    setText(document.querySelector('[data-bind="v7.instrument.calibration.expected_for_frame"]'), requirement.label);
    setText(document.querySelector('[data-bind="v7.instrument.calibration.compatibility"]'), calibrationCompatibilityLabel(runtime.calibrationStatus));
  }

  function applyCalibrationDefaultsForFrameType() {
    const modeSelect = byRole("instrument-calibration-mode");
    const lampSelect = byRole("instrument-calibration-lamp");
    const enabledInput = byRole("instrument-calibration-lamp-enabled");
    if (!modeSelect || !lampSelect || !enabledInput) return;

    const requirement = calibrationRequirementForFrameType(observeFrameType(), lampSelect.value);
    if (!requirement.enforce) {
      renderCalibrationFrameGuidance();
      return;
    }

    if (requirement.mode) modeSelect.value = requirement.mode;
    enabledInput.checked = Boolean(requirement.lampEnabled);
    if (requirement.defaultLamp) lampSelect.value = requirement.defaultLamp;
    syncCalibrationControlState("frame_defaults");
    renderCalibrationFrameGuidance();
  }

  function updateCalibrationFields(payload) {
    if (!payload || typeof payload !== "object") return;
    const mode = payload.mode || payload.calibration_mode || "unknown";
    const activeLamp = payload.active_lamp || payload.lamp || payload.selected_lamp || null;
    const lampEnabled = payload.lamp_enabled === undefined ? Boolean(activeLamp) : Boolean(payload.lamp_enabled);
    const mirrorInserted = payload.mirror_inserted === undefined ? mode === "calibration" : Boolean(payload.mirror_inserted);

    runtime.calibrationStatus = {
      mode,
      activeLamp,
      lampEnabled,
      mirrorInserted,
    };

    setText(document.querySelector('[data-bind="v7.instrument.calibration.mode"]'), mode);
    setText(document.querySelector('[data-bind="v7.instrument.calibration.active_lamp"]'), lampEnabled && activeLamp ? activeLamp : "none");
    setText(document.querySelector('[data-bind="v7.instrument.calibration.lamp_enabled"]'), String(lampEnabled));
    setText(document.querySelector('[data-bind="v7.instrument.calibration.mirror_inserted"]'), mirrorInserted ? "inserted" : "out");

    const modeSelect = byRole("instrument-calibration-mode");
    const lampSelect = byRole("instrument-calibration-lamp");
    const enabledInput = byRole("instrument-calibration-lamp-enabled");
    if (modeSelect && (mode === "science" || mode === "calibration")) modeSelect.value = mode;
    if (lampSelect && activeLamp) lampSelect.value = activeLamp;
    if (enabledInput) enabledInput.checked = lampEnabled;

    renderCalibrationFrameGuidance();
  }

  function syncCalibrationControlState(trigger) {
    const modeSelect = byRole("instrument-calibration-mode");
    const lampSelect = byRole("instrument-calibration-lamp");
    const enabledInput = byRole("instrument-calibration-lamp-enabled");
    if (!modeSelect || !enabledInput) return;

    if (trigger === "mode" && modeSelect.value === "science") {
      enabledInput.checked = false;
      renderCalibrationFrameGuidance();
      return;
    }

    if ((trigger === "lamp_enable" || trigger === "lamp_select") && enabledInput.checked) {
      modeSelect.value = "calibration";
      renderCalibrationFrameGuidance();
      return;
    }

    if (trigger === "frame_defaults") {
      renderCalibrationFrameGuidance();
      return;
    }

    if (modeSelect.value === "science") enabledInput.checked = false;
    if (enabledInput.checked) modeSelect.value = "calibration";
    renderCalibrationFrameGuidance();
  }

  function bindObservationFrameTypeContext() {
    const select = document.querySelector('[data-role="obs-frame-type"]');
    if (!select || select.dataset.calibrationContextBound) return;
    select.dataset.calibrationContextBound = "true";
    select.addEventListener("change", renderCalibrationFrameGuidance);
  }

  function updateDetectorFields(payload) {
    if (!payload || typeof payload !== "object") return;
    setText(document.querySelector('[data-bind="v7.instrument.detector.profile"]'), payload.profile_name || "unknown");
    setText(document.querySelector('[data-bind="v7.instrument.detector.save_enabled"]'), payload.save_enabled === undefined ? "unknown" : String(payload.save_enabled));
    setText(document.querySelector('[data-bind="v7.instrument.detector.trigger_mode"]'), payload.trigger_mode || "unknown");
    setText(document.querySelector('[data-bind="v7.instrument.detector.readout_mode"]'), payload.readout_mode || "unknown");
    const channels = payload.channels || payload.channel_state || {};
    ["B", "G", "R"].forEach((channel) => {
      const data = channels[channel] || channels[channel.toLowerCase()] || {};
      setText(document.querySelector(`[data-bind="v7.instrument.channel.${channel}.enabled"]`), data.enabled === undefined ? "visible" : String(data.enabled));
      setText(document.querySelector(`[data-bind="v7.instrument.channel.${channel}.role"]`), data.role || `science_${channel.toLowerCase()}`);
    });
  }

  async function fetchJson(endpoint, options) {
    const response = await fetch(endpoint, options);
    runtime.lastRequestId = requestIdFrom(response);
    const payload = await response.json();
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${JSON.stringify(payload)}`);
    return payload;
  }

  async function postJson(command, endpoint, body) {
    if (runtime.busy) return;
    setBusy(true);
    try {
      const payload = await fetchJson(endpoint, {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify(body),
      });
      if (command === "set_slit_width") updateSlitFieldsFromUm(body.width_um);
      if (command === "set_calibration_mode" || command === "set_calibration_lamp") updateCalibrationFields(payload);
      renderResult(command, payload);
    } catch (error) {
      renderError(command, error && error.message);
    } finally {
      setBusy(false);
    }
  }

  async function getJson(command, endpoint, onPayload) {
    if (runtime.busy) return;
    setBusy(true);
    try {
      const payload = await fetchJson(endpoint, { cache: "no-store", headers: { Accept: "application/json" } });
      if (onPayload) onPayload(payload);
      renderResult(command, payload);
    } catch (error) {
      renderError(command, error && error.message);
    } finally {
      setBusy(false);
    }
  }

  function readNumber(role, label) {
    const input = byRole(role);
    const value = Number(input && input.value);
    if (!Number.isFinite(value)) throw new Error(`${label} must be a number.`);
    return value;
  }

  function readSlitWidthUm() {
    const arcInput = byRole("instrument-slit-width-arcsec");
    const umInput = byRole("instrument-slit-width-um");
    const arcsec = Number(arcInput && arcInput.value);
    if (Number.isFinite(arcsec) && arcsec > 0) {
      const widthUm = umFromArcsec(arcsec);
      if (umInput) umInput.value = formatNumber(widthUm, 3);
      return widthUm;
    }
    const widthUm = Number(umInput && umInput.value);
    if (!Number.isFinite(widthUm) || widthUm <= 0) throw new Error("Slit width must be greater than zero.");
    if (arcInput) arcInput.value = formatNumber(arcsecFromUm(widthUm), 3);
    return widthUm;
  }

  function action(name) {
    const host = panel();
    return host && host.querySelector(`[data-action="${name}"]`);
  }

  function bindButton(name, handler) {
    const button = action(name);
    if (!button || button.dataset.bound) return;
    button.dataset.bound = "true";
    button.disabled = false;
    button.addEventListener("click", handler);
  }

  function bindSlitUnitSync() {
    const arcInput = byRole("instrument-slit-width-arcsec");
    const umInput = byRole("instrument-slit-width-um");
    if (arcInput && !arcInput.dataset.bound) {
      arcInput.dataset.bound = "true";
      arcInput.addEventListener("input", () => {
        const arcsec = Number(arcInput.value);
        if (Number.isFinite(arcsec) && arcsec > 0 && umInput) umInput.value = formatNumber(umFromArcsec(arcsec), 3);
      });
    }
    if (umInput && !umInput.dataset.bound) {
      umInput.dataset.bound = "true";
      umInput.addEventListener("input", () => {
        const widthUm = Number(umInput.value);
        if (Number.isFinite(widthUm) && widthUm > 0 && arcInput) arcInput.value = formatNumber(arcsecFromUm(widthUm), 3);
      });
    }
    setText(bind("v7.instrument.slit.conversion_um_per_arcsec"), SLIT_UM_PER_ARCSEC);
  }

  function bindSlitShortcuts() {
    const host = panel();
    if (!host) return;
    host.querySelectorAll('[data-role="instrument-slit-shortcut"]').forEach((button) => {
      if (button.dataset.bound) return;
      button.dataset.bound = "true";
      button.disabled = false;
      button.addEventListener("click", () => {
        const arcsec = Number(button.dataset.arcsec);
        if (!Number.isFinite(arcsec) || !COMMON_SLIT_WIDTH_ARCSEC.includes(arcsec)) return;
        updateSlitFieldsFromUm(umFromArcsec(arcsec));
      });
    });
  }

  function bindEvents() {
    bindSlitUnitSync();
    bindSlitShortcuts();
    bindObservationFrameTypeContext();

    const modeSelect = byRole("instrument-calibration-mode");
    const lampSelect = byRole("instrument-calibration-lamp");
    const enabledInput = byRole("instrument-calibration-lamp-enabled");

    if (modeSelect && !modeSelect.dataset.couplingBound) {
      modeSelect.dataset.couplingBound = "true";
      modeSelect.addEventListener("change", () => syncCalibrationControlState("mode"));
    }
    if (lampSelect && !lampSelect.dataset.couplingBound) {
      lampSelect.dataset.couplingBound = "true";
      lampSelect.addEventListener("change", () => syncCalibrationControlState("lamp_select"));
    }
    if (enabledInput && !enabledInput.dataset.couplingBound) {
      enabledInput.dataset.couplingBound = "true";
      enabledInput.addEventListener("change", () => syncCalibrationControlState("lamp_enable"));
    }

    bindButton("instrument-set-slit-width", () => {
      try {
        postJson("set_slit_width", SLIT_ENDPOINT, { width_um: readSlitWidthUm() });
      } catch (error) {
        renderError("set_slit_width", error && error.message);
      }
    });
    bindButton("instrument-set-slit-angle", () => {
      try {
        postJson("set_slit_angle", SLIT_ANGLE_ENDPOINT, { angle_deg: readNumber("instrument-slit-angle-deg", "Slit angle") });
      } catch (error) {
        renderError("set_slit_angle", error && error.message);
      }
    });
    bindButton("instrument-set-calibration-mode", () => {
      const select = byRole("instrument-calibration-mode");
      syncCalibrationControlState("mode");
      postJson("set_calibration_mode", CALIBRATION_MODE_ENDPOINT, { mode: select ? select.value : "science" });
    });
    bindButton("instrument-set-calibration-lamp", () => {
      const select = byRole("instrument-calibration-lamp");
      const enabled = byRole("instrument-calibration-lamp-enabled");
      syncCalibrationControlState("lamp_enable");
      postJson("set_calibration_lamp", CALIBRATION_LAMP_ENDPOINT, { lamp: select ? select.value : "flat", enabled: Boolean(enabled && enabled.checked) });
    });
    bindButton("instrument-use-calibration-frame-defaults", applyCalibrationDefaultsForFrameType);
    bindButton("instrument-refresh-calibration", () => getJson("refresh_calibration", CALIBRATION_STATUS_ENDPOINT, updateCalibrationFields));
    bindButton("instrument-refresh-detector-config", () => getJson("refresh_detector_config", DETECTOR_CONFIG_ENDPOINT, updateDetectorFields));
    renderCalibrationFrameGuidance();
  }

  function start() {
    const host = ensurePanelLayout();
    if (!host) return;
    host.setAttribute("data-runtime", "enabled");
    bindEvents();
    setRuntimeState("ready");
    updateSlitFieldsFromUm(SLIT_UM_PER_ARCSEC);
    getJson("refresh_calibration", CALIBRATION_STATUS_ENDPOINT, updateCalibrationFields);
    getJson("refresh_detector_config", DETECTOR_CONFIG_ENDPOINT, updateDetectorFields);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
