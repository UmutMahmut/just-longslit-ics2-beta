// v7 observe runtime adapter. Default-on during Phase 2.9-F.

(function () {
  "use strict";

  const GLOBAL_KEY = "__JUSTLS_V7_OBSERVE_RUNTIME__";
  const STATUS_ENDPOINT = "/api/v1/observation/status";
  const PREVIEW_ENDPOINT = "/api/v1/observation/preview";
  const ARM_ENDPOINT = "/api/v1/observation/arm";
  const START_ENDPOINT = "/api/v1/observation/start";
  const FINISH_ENDPOINT = "/api/v1/observation/finish";
  const STOP_READOUT_ENDPOINT = "/api/v1/observation/stop_readout";
  const ABORT_DISCARD_ENDPOINT = "/api/v1/observation/abort_discard";

  const runtime = window[GLOBAL_KEY] || {
    started: false,
    busy: false,
    statusLoading: false,
    lastStatus: null,
    lastPreview: null,
    lastCommand: null,
    lastResult: null,
    lastError: null,
    lastRequestId: null,
    localRefreshBound: false,
  };
  window[GLOBAL_KEY] = runtime;

  function text(value, fallback) {
    if (value === null || value === undefined || value === "") return fallback;
    return String(value);
  }

  function page() {
    return document.querySelector('[data-page-panel="observe"]');
  }

  function setText(node, value) {
    if (!node) return;
    const next = text(value, "");
    if (node.textContent !== next) node.textContent = next;
  }

  function createFallbackPanel() {
    const host = page();
    if (!host) return null;

    const panel = document.createElement("section");
    panel.id = "v7-observe-controls";
    panel.className = "panel";
    panel.setAttribute("data-role", "v7-observe-panel");
    panel.setAttribute("data-origin", "runtime-created-observe-skeleton");
    panel.setAttribute("data-phase", "2.9-F-operator-workflow");
    panel.innerHTML = `
      <h2>Observe - Exposure and Sequence Control</h2>
      <div class="panel-body grid">
        <div class="field-grid">
          <label>Exposure Time (s)<input type="number" min="0.001" step="0.001" value="30" data-role="obs-exp-time" /></label>
          <label>Frame Type<select data-role="obs-frame-type"><option value="science">science</option><option value="flat">flat</option><option value="arc">arc</option><option value="test">test</option></select></label>
          <label style="grid-column: 1 / -1;">Operator Note<textarea data-role="obs-operator-note" placeholder="Optional note"></textarea></label>
        </div>
        <dl class="kv">
          <dt>Status Endpoint</dt><dd><code>${STATUS_ENDPOINT}</code></dd>
          <dt>Observation State</dt><dd><code data-bind="v7.observe.state">unknown</code></dd>
          <dt>Armed Exposure</dt><dd><code data-bind="v7.observe.armed">not armed</code></dd>
          <dt>Last Command</dt><dd><code data-bind="v7.observe.last_command">none</code></dd>
          <dt>Request ID</dt><dd><code data-bind="v7.observe.request_id">not available</code></dd>
          <dt>Latest Job</dt><dd><code data-bind="v7.observe.latest_job">not available</code></dd>
          <dt>Last Error</dt><dd><code data-bind="v7.observe.last_error">none</code></dd>
          <dt>Result Summary</dt><dd><code data-bind="v7.observe.result_summary">no command yet</code></dd>
          <dt>Runtime State</dt><dd><code data-bind="v7.observe.runtime_state">idle</code></dd>
        </dl>
        <div class="badge-row">
          <button class="btn" type="button" data-action="obs-preview">Preview</button>
          <button class="btn primary" type="button" data-action="obs-arm">Arm</button>
          <button class="btn primary" type="button" data-action="obs-start">Start</button>
          <button class="btn" type="button" data-action="obs-finish">Finish</button>
          <button class="btn" type="button" data-action="obs-stop-readout">Stop & Readout</button>
          <button class="btn danger" type="button" data-action="obs-abort-discard">Abort & Discard</button>
        </div>
        <label><input type="checkbox" data-role="obs-abort-confirm" /> Enable abort/discard command</label>
        <p style="margin: 0; color: var(--muted); font-size: 12px;">This baseline does not auto-finish at the requested exposure time. Use Finish or Stop &amp; Readout; timer-driven completion remains deferred.</p>
        <section class="subpanel" data-role="v7-observe-preview-panel">
          <h3>Observation Preview - Readiness / Validation</h3>
          <dl class="kv">
            <dt>Preview Endpoint</dt><dd><code>${PREVIEW_ENDPOINT}</code></dd>
            <dt>Preview</dt><dd><code data-bind="v7.observe.preview.blocked">not checked</code></dd>
            <dt>Execution</dt><dd><code data-bind="v7.observe.preview.single_exposure_compatible">not checked</code></dd>
            <dt>Detector</dt><dd><code data-bind="v7.observe.preview.detector_state">unknown</code></dd>
            <dt>Calibration</dt><dd><code data-bind="v7.observe.preview.calibration_state">not checked</code></dd>
            <dt>Slit</dt><dd><code data-bind="v7.observe.preview.slit_state">unknown</code></dd>
            <dt>TCS</dt><dd><code data-bind="v7.observe.preview.tcs_state">unavailable</code></dd>
            <dt>Setup/Data</dt><dd><code data-bind="v7.observe.preview.setup_context">unknown</code></dd>
            <dt>Issues</dt><dd><code data-bind="v7.observe.preview.issues">not checked</code></dd>
            <dt>Summary</dt><dd><code data-bind="v7.observe.preview.summary">Preview has not been requested.</code></dd>
          </dl>
          <details class="dev-note" data-role="v7-observe-preview-raw">
            <summary>Raw Preview JSON</summary>
            <pre data-bind="v7.observe.preview.raw">No observation preview requested. Preview is side-effect-free and does not arm the detector.</pre>
          </details>
        </section>
        <details class="dev-note" data-role="v7-observe-command-raw">
          <summary>Raw Command JSON</summary>
          <pre data-bind="v7.observe.result">No observation command sent.</pre>
        </details>
        <span class="badge live" data-bind="v7.observe.runtime_notice">Operator runtime initializing</span>
      </div>`;
    host.insertBefore(panel, host.firstChild);
    return panel;
  }

  function bindPanelEvents(panel) {
    const bindings = [
      ["obs-preview", previewObservation],
      ["obs-arm", arm],
      ["obs-start", () => postCommand("start", START_ENDPOINT)],
      ["obs-finish", () => postCommand("finish", FINISH_ENDPOINT)],
      ["obs-stop-readout", () => postCommand("stop_readout", STOP_READOUT_ENDPOINT)],
      ["obs-abort-discard", abortDiscard],
    ];

    bindings.forEach(([action, handler]) => {
      const button = panel.querySelector(`[data-action="${action}"]`);
      if (!button || button.dataset.bound) return;
      button.dataset.bound = "true";
      button.addEventListener("click", handler);
    });
  }

  function setPanelButtonsDisabled(panel, disabled) {
    if (!panel) return;
    panel.querySelectorAll('button[data-action^="obs-"]').forEach((button) => {
      button.disabled = disabled;
    });
  }

  function enhancePanel(panel) {
    const firstEnable = panel.getAttribute("data-runtime") !== "enabled";
    panel.setAttribute("data-runtime", "enabled");
    panel.setAttribute("data-phase", "2.9-F-operator-workflow");
    bindPanelEvents(panel);
    if (firstEnable) setPanelButtonsDisabled(panel, false);
    return panel;
  }

  function ensurePanel() {
    const existing = document.getElementById("v7-observe-controls");
    const panel = existing || createFallbackPanel();
    return panel ? enhancePanel(panel) : null;
  }

  function bind(name) {
    const panel = ensurePanel();
    return panel ? panel.querySelector(`[data-bind="${name}"]`) : null;
  }

  function runtimeStateLabel() {
    if (runtime.busy) return "command in flight";
    if (runtime.statusLoading) return "loading status";
    return runtime.started ? "ready" : "idle";
  }

  function refreshRuntimeState() {
    setText(bind("v7.observe.runtime_state"), runtimeStateLabel());
    setText(bind("v7.observe.runtime_notice"), runtime.started ? "Operator runtime enabled" : "Operator runtime initializing");
    if (!runtime.lastCommand && !runtime.lastError) {
      setText(bind("v7.observe.result_summary"), "no command yet");
    }
  }

  function setBusy(value) {
    runtime.busy = value;
    refreshRuntimeState();
    const panel = ensurePanel();
    if (!panel) return;
    setPanelButtonsDisabled(panel, value);
  }

  function readArmPayload() {
    const panel = ensurePanel();
    const expInput = panel.querySelector('[data-role="obs-exp-time"]');
    const frameInput = panel.querySelector('[data-role="obs-frame-type"]');
    const noteInput = panel.querySelector('[data-role="obs-operator-note"]');

    const expTime = Number(expInput && expInput.value);
    if (!Number.isFinite(expTime) || expTime <= 0) {
      throw new Error("Exposure time must be greater than zero.");
    }

    return {
      exp_time_s: expTime,
      frame_type: frameInput ? frameInput.value : "science",
      operator_note: noteInput && noteInput.value ? noteInput.value : null,
    };
  }

  function readPreviewPayload() {
    const arm = readArmPayload();
    return {
      exposures: [
        {
          frame_type: arm.frame_type,
          exp_time_s: arm.exp_time_s,
        },
      ],
      operator_note: arm.operator_note,
    };
  }

  function requestIdFrom(response) {
    return (
      response.headers.get("x-request-id") ||
      response.headers.get("X-Request-ID") ||
      runtime.lastRequestId
    );
  }

  function latestJobLabel(payload) {
    const job = payload && payload.latest_job;
    if (!job) return "not available";
    return [job.status, job.subsystem, job.action, job.job_id].filter(Boolean).join(" - ");
  }

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function isCommandFeedback(payload) {
    return (
      isObject(payload) &&
      typeof payload.command === "string" &&
      typeof payload.status === "string" &&
      Object.prototype.hasOwnProperty.call(payload, "ok")
    );
  }

  function commandFeedbackPayload(feedback) {
    if (!isCommandFeedback(feedback) || !isObject(feedback.details)) return null;
    return isObject(feedback.details.payload) ? feedback.details.payload : null;
  }

  function errorLabel(error) {
    if (!error) return "none";
    if (!isObject(error)) return text(error, "failed");

    const code = error.code || "error";
    const message = error.message || "command failed";
    return `${code} - ${message}`;
  }

  function listLabel(values, fallback) {
    if (!Array.isArray(values) || values.length === 0) return fallback;
    return values.filter(Boolean).join(", ") || fallback;
  }

  function validationIssueCodes(feedback) {
    const direct = isObject(feedback) && Array.isArray(feedback.validation_issues)
      ? feedback.validation_issues
      : [];
    const preview = isObject(feedback && feedback.preview) && Array.isArray(feedback.preview.validation_issues)
      ? feedback.preview.validation_issues
      : [];
    return direct.concat(preview)
      .map((issue) => issue && issue.code)
      .filter(Boolean);
  }

  function resultSummary(command, payload) {
    if (!command) return "none";
    if (!payload || typeof payload !== "object") return `${command}: done`;

    const state = payload.state || payload.observation_state;
    const last = payload.last_exposure || payload.armed_exposure || {};
    const frame = last.frame_type || payload.frame_type;
    const exp = last.exp_time_s || payload.exp_time_s;

    const parts = [command];
    if (state) parts.push(state);
    if (frame) parts.push(frame);
    if (exp) parts.push(`${exp} s`);
    return parts.join(" - ");
  }

  function commandFeedbackSummary(command, feedback) {
    if (!isCommandFeedback(feedback)) return resultSummary(command, feedback);

    const name = feedback.command || command || "command";
    const payload = commandFeedbackPayload(feedback) || {};
    const state = feedback.observation_state || payload.state || payload.observation_state;

    if (feedback.status === "blocked" || feedback.blocked === true) {
      const parts = [name, "blocked"];
      if (feedback.blocked_reason) parts.push(String(feedback.blocked_reason).replace(/_/g, " "));
      const components = listLabel(feedback.blocked_components, "none");
      if (components !== "none") parts.push(components);
      const issueCodes = listLabel(validationIssueCodes(feedback), "none");
      if (issueCodes !== "none") parts.push(issueCodes);
      return parts.join(" - ");
    }

    if (feedback.status === "failed" || feedback.ok === false) {
      const parts = [name, "failed"];
      if (feedback.error && feedback.error.code) parts.push(feedback.error.code);
      if (feedback.error && feedback.error.message) parts.push(feedback.error.message);
      return parts.join(" - ");
    }

    const last = payload.last_exposure || payload.armed_exposure || {};
    const frame = last.frame_type || payload.frame_type;
    const exp = last.exp_time_s || payload.exp_time_s;
    const parts = [name, feedback.status || "succeeded"];
    if (state) parts.push(state);
    if (frame) parts.push(frame);
    if (exp) parts.push(`${exp} s`);
    return parts.join(" - ");
  }

  function bindStructuredResult(command, payload, error) {
    if (isCommandFeedback(payload)) {
      runtime.lastRequestId = payload.request_id || runtime.lastRequestId;
      setText(bind("v7.observe.last_command"), payload.command || command || "none");
      setText(bind("v7.observe.request_id"), payload.request_id || runtime.lastRequestId || "not available");
      setText(bind("v7.observe.latest_job"), latestJobLabel(payload));
      setText(bind("v7.observe.last_error"), payload.ok === false ? errorLabel(payload.error) : "none");
      setText(bind("v7.observe.result_summary"), commandFeedbackSummary(command, payload));
      return;
    }

    setText(bind("v7.observe.last_command"), command || "none");
    setText(bind("v7.observe.request_id"), runtime.lastRequestId || "not available");
    setText(bind("v7.observe.latest_job"), latestJobLabel(payload));
    setText(bind("v7.observe.last_error"), error ? text(error, "failed") : "none");
    setText(
      bind("v7.observe.result_summary"),
      error
        ? `${command || "command"}: ${text(error, "failed")}`
        : resultSummary(command, payload),
    );
  }

  function yesNo(value) {
    if (value === true) return "yes";
    if (value === false) return "no";
    return "unknown";
  }

  function readinessLabel(item) {
    if (!item || typeof item !== "object") return "unknown";
    const state = item.state || "unknown";
    return item.message ? `${state} - ${item.message}` : state;
  }

  function issueLabel(issues) {
    if (!Array.isArray(issues) || issues.length === 0) return "none";
    return issues
      .map((issue) => {
        const severity = issue && issue.severity ? issue.severity : "issue";
        const code = issue && issue.code ? issue.code : "unknown";
        return `${severity}:${code}`;
      })
      .join(" - ");
  }

  function previewSummary(payload) {
    if (!payload || typeof payload !== "object") return "preview not available";
    const blocked = payload.blocked === true ? "blocked" : "not blocked";
    const compatible =
      payload.single_exposure_compatible === true
        ? "single exposure compatible"
        : "not single exposure compatible";
    const issueCount = Array.isArray(payload.validation_issues)
      ? payload.validation_issues.length
      : 0;
    return `${blocked} - ${compatible} - ${issueCount} issue${issueCount === 1 ? "" : "s"}`;
  }

  function renderPreview(payload) {
    runtime.lastPreview = payload || {};
    const readiness = runtime.lastPreview.readiness || {};

    setText(
      bind("v7.observe.preview.blocked"),
      runtime.lastPreview.blocked === true ? "blocked" : "not blocked",
    );
    setText(
      bind("v7.observe.preview.single_exposure_compatible"),
      yesNo(runtime.lastPreview.single_exposure_compatible),
    );
    setText(bind("v7.observe.preview.detector_state"), readinessLabel(readiness.detector));
    setText(bind("v7.observe.preview.calibration_state"), readinessLabel(readiness.calibration));
    setText(bind("v7.observe.preview.slit_state"), readinessLabel(readiness.slit));
    setText(bind("v7.observe.preview.tcs_state"), readinessLabel(readiness.tcs));
    setText(
      bind("v7.observe.preview.setup_context"),
      runtime.lastPreview.request && runtime.lastPreview.request.setup_context
        ? "available"
        : "not available",
    );
    setText(bind("v7.observe.preview.issues"), issueLabel(runtime.lastPreview.validation_issues));
    setText(bind("v7.observe.preview.summary"), previewSummary(runtime.lastPreview));
    setText(
      bind("v7.observe.preview.raw"),
      JSON.stringify(
        {
          command: "preview",
          request_id: runtime.lastRequestId,
          payload: runtime.lastPreview,
        },
        null,
        2,
      ),
    );
  }

  function renderStatus(payload) {
    runtime.lastStatus = payload || {};
    const armed = runtime.lastStatus.armed_exposure || runtime.lastStatus.last_exposure || null;
    const record = runtime.lastStatus.latest_exposure_record || (runtime.lastStatus.observation_meta && runtime.lastStatus.observation_meta.exposure_record) || null;

    setText(
      bind("v7.observe.state"),
      runtime.lastStatus.state || runtime.lastStatus.observation_state || "unknown",
    );
    setText(
      bind("v7.observe.armed"),
      armed ? `${armed.frame_type || "frame"} - ${armed.exp_time_s || "?"} s` : "not armed",
    );
    setText(bind("v7.observe.record.id"), record ? record.record_id : "not available");
    setText(
      bind("v7.observe.record.provenance"),
      record ? `${record.simulated ? "SIMULATED" : "REAL"} - ${record.data_product_state || "unknown"}` : "not available",
    );
    setText(
      bind("v7.observe.record.fits"),
      record && record.primary_data_product ? `${record.primary_data_product.state}: ${record.primary_data_product.uri || "no URI"}` : "not created",
    );
    setText(
      bind("v7.observe.record.quicklook"),
      record && record.quicklook ? `${record.quicklook.state}: ${record.quicklook.uri || "no URI"}` : "not created",
    );

    window.dispatchEvent(new CustomEvent("justls:v7-observe-state", { detail: runtime.lastStatus }));
  }

  function renderCommandFeedback(command, feedback) {
    const payload = commandFeedbackPayload(feedback);
    if (payload) renderStatus(payload);

    runtime.lastCommand = feedback.command || command;
    runtime.lastResult = feedback;
    runtime.lastError = feedback.ok === false ? errorLabel(feedback.error) : null;
    runtime.lastRequestId = feedback.request_id || runtime.lastRequestId;

    bindStructuredResult(command, feedback, runtime.lastError);
    setText(
      bind("v7.observe.result"),
      JSON.stringify({
        command: feedback.command || command,
        request_id: runtime.lastRequestId,
        feedback,
      }, null, 2),
    );
  }

  function renderResult(command, payload) {
    if (isCommandFeedback(payload)) {
      renderCommandFeedback(command, payload);
      return;
    }

    renderStatus(payload);
    runtime.lastCommand = command;
    runtime.lastResult = payload;
    runtime.lastError = null;
    setText(bind("v7.observe.last_command"), command);
    bindStructuredResult(command, payload, null);
    setText(
      bind("v7.observe.result"),
      JSON.stringify({ command, request_id: runtime.lastRequestId, payload }, null, 2),
    );
  }

  function renderError(command, error) {
    if (isCommandFeedback(error)) {
      renderCommandFeedback(command, error);
      return;
    }

    runtime.lastCommand = command;
    runtime.lastError = text(error, "failed");
    setText(bind("v7.observe.last_command"), command);
    bindStructuredResult(command, runtime.lastResult, runtime.lastError);
    setText(
      bind("v7.observe.result"),
      JSON.stringify({ command, request_id: runtime.lastRequestId, error: runtime.lastError }, null, 2),
    );
  }

  async function refreshStatus() {
    if (runtime.statusLoading) return;

    ensurePanel();
    runtime.statusLoading = true;
    refreshRuntimeState();

    try {
      const response = await fetch(STATUS_ENDPOINT, {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      runtime.lastRequestId = requestIdFrom(response);
      const payload = await response.json();

      if (response.ok) {
        renderStatus(payload);
      } else {
        renderError("status", `HTTP ${response.status}: ${JSON.stringify(payload)}`);
      }
    } catch (error) {
      renderError("status", error && error.message);
    } finally {
      runtime.statusLoading = false;
      refreshRuntimeState();
    }
  }

  async function previewObservation() {
    if (runtime.busy) return;

    setBusy(true);
    try {
      const response = await fetch(PREVIEW_ENDPOINT, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        cache: "no-store",
        body: JSON.stringify(readPreviewPayload()),
      });
      runtime.lastRequestId = requestIdFrom(response);
      const payload = await response.json();

      if (response.ok) {
        renderPreview(payload);
        runtime.lastCommand = "preview";
        runtime.lastResult = payload;
        runtime.lastError = null;
        bindStructuredResult("preview", payload, null);
      } else {
        renderError("preview", `HTTP ${response.status}: ${JSON.stringify(payload)}`);
      }
    } catch (error) {
      renderError("preview", error && error.message);
    } finally {
      setBusy(false);
    }
  }

  async function postCommand(command, endpoint, body) {
    if (runtime.busy) return;

    setBusy(true);
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        cache: "no-store",
        body: body ? JSON.stringify(body) : undefined,
      });
      runtime.lastRequestId = requestIdFrom(response);
      const payload = await response.json();

      if (isCommandFeedback(payload)) {
        renderCommandFeedback(command, payload);
      } else if (response.ok) {
        renderResult(command, payload);
      } else {
        renderError(command, `HTTP ${response.status}: ${JSON.stringify(payload)}`);
      }
    } catch (error) {
      renderError(command, error && error.message);
    } finally {
      setBusy(false);
      refreshStatus();
    }
  }

  async function arm() {
    try {
      await postCommand("arm", ARM_ENDPOINT, readArmPayload());
    } catch (error) {
      renderError("arm", error && error.message);
    }
  }

  async function abortDiscard() {
    const panel = ensurePanel();
    const confirm = panel.querySelector('[data-role="obs-abort-confirm"]');

    if (!confirm || !confirm.checked) {
      renderError("abort_discard", "Explicit checkbox is required.");
      return;
    }

    await postCommand("abort_discard", ABORT_DISCARD_ENDPOINT);
    confirm.checked = false;
  }

  function start() {
    ensurePanel();
    refreshRuntimeState();

    if (!runtime.localRefreshBound) {
      runtime.localRefreshBound = true;
      window.addEventListener("justls:v7-local-refresh", refreshStatus);
    }

    if (runtime.started) {
      refreshStatus();
      return;
    }

    runtime.started = true;
    refreshStatus();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
