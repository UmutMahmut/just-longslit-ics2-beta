// v7 multi-exposure sequence runtime. Simulator-first and operator-stepped.

(function () {
  "use strict";

  const GLOBAL_KEY = "__JUSTLS_V7_SEQUENCE_RUNTIME__";
  const ENDPOINTS = {
    preview: "/api/v1/observation/sequence/preview",
    load: "/api/v1/observation/sequence/load",
    status: "/api/v1/observation/sequence/status",
    start: "/api/v1/observation/sequence/start",
    finish_step: "/api/v1/observation/sequence/finish_step",
    stop_readout_step: "/api/v1/observation/sequence/stop_readout_step",
    pause: "/api/v1/observation/sequence/pause",
    resume: "/api/v1/observation/sequence/resume",
    abort: "/api/v1/observation/sequence/abort",
  };

  const runtime = window[GLOBAL_KEY] || {
    started: false,
    busy: false,
    snapshot: null,
    previewPlan: null,
    lastRequestId: null,
    lastCommand: null,
    lastJob: null,
    lastError: null,
  };
  window[GLOBAL_KEY] = runtime;

  function panel() {
    return document.querySelector('[data-role="v7-observe-sequence-panel"]');
  }

  function setText(node, value) {
    if (node) node.textContent = value === null || value === undefined || value === "" ? "not available" : String(value);
  }

  function setBinding(name, value) {
    document.querySelectorAll(`[data-bind="${name}"]`).forEach((node) => setText(node, value));
  }

  function requestIdFrom(response) {
    return response.headers.get("x-request-id") || response.headers.get("X-Request-ID") || runtime.lastRequestId;
  }

  function readPlan() {
    const host = panel();
    const textarea = host && host.querySelector('[data-role="sequence-plan-steps"]');
    const lines = String(textarea && textarea.value || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    if (!lines.length) throw new Error("Add at least one sequence step.");
    const exposures = lines.map((line, index) => {
      const [frameTypeRaw, secondsRaw, ...labelParts] = line.split(",").map((part) => part.trim());
      const frameType = frameTypeRaw || "science";
      const expTime = Number(secondsRaw);
      if (!["science", "flat", "arc", "test"].includes(frameType)) throw new Error(`Step ${index + 1}: unsupported frame type ${frameType}.`);
      if (!Number.isFinite(expTime) || expTime <= 0) throw new Error(`Step ${index + 1}: exposure time must be positive.`);
      return { frame_type: frameType, exp_time_s: expTime, label: labelParts.join(",") || null };
    });
    return { exposures };
  }

  function plansMatch(left, right) {
    if (!left || !right || !Array.isArray(left.exposures) || !Array.isArray(right.exposures)) return false;
    const normalize = (plan) => plan.exposures.map((exposure) => ({
      frame_type: exposure.frame_type,
      exp_time_s: Number(exposure.exp_time_s),
      label: exposure.label || null,
    }));
    return JSON.stringify(normalize(left)) === JSON.stringify(normalize(right));
  }

  function readPlanForLoad() {
    const currentInput = readPlan();
    return plansMatch(runtime.previewPlan, currentInput) ? runtime.previewPlan : currentInput;
  }

  function jobLabel(job) {
    if (!job) return "not available";
    return [job.status, job.job_id].filter(Boolean).join(" - ") || "not available";
  }

  function broadcastSnapshot(snapshot) {
    window.dispatchEvent(new CustomEvent("justls:v7-sequence-state", { detail: snapshot }));
  }

  function snapshotFrom(payload) {
    if (!payload) return null;
    return payload.sequence || (payload.plan && payload.state ? payload : null);
  }

  function render(payload, command) {
    const snapshot = snapshotFrom(payload);
    if (snapshot) runtime.snapshot = snapshot;
    runtime.lastCommand = command;
    runtime.lastJob = payload && payload.latest_job ? payload.latest_job : runtime.lastJob;
    runtime.lastError = payload && payload.error ? `${payload.error.code}: ${payload.error.message}` : null;
    setBinding("v7.sequence.last_command", runtime.lastCommand || "none");
    setBinding("v7.sequence.request_id", runtime.lastRequestId || "not available");
    setBinding("v7.sequence.latest_job", jobLabel(runtime.lastJob));
    setBinding("v7.sequence.last_error", runtime.lastError || "none");
    setBinding("v7.sequence.raw", JSON.stringify({ command, request_id: runtime.lastRequestId, payload }, null, 2));

    if (payload && payload.plan && Array.isArray(payload.steps)) {
      runtime.previewPlan = payload.plan;
      setBinding("v7.sequence.plan_id", payload.plan.plan_id);
      setBinding("v7.sequence.state", payload.blocked ? "blocked preview" : "preview ready");
      setBinding("v7.sequence.progress", `0 / ${payload.steps.length}`);
      setBinding("v7.sequence.current", payload.steps.length ? "step 1 pending" : "not available");
      setBinding("v7.sequence.summary", payload.executable ? `${payload.steps.length} steps ready to load.` : "Plan is blocked; inspect readiness details.");
      refreshButtons();
      return;
    }

    const current = runtime.snapshot;
    if (!current) {
      setBinding("v7.sequence.summary", runtime.lastError || "No plan loaded.");
      refreshButtons();
      broadcastSnapshot(null);
      return;
    }
    const total = current.plan && current.plan.exposures ? current.plan.exposures.length : 0;
    const completed = (current.step_results || []).filter((step) => step.state === "completed").length;
    const exposure = current.current_index < total ? current.plan.exposures[current.current_index] : null;
    setBinding("v7.sequence.plan_id", current.plan.plan_id);
    setBinding("v7.sequence.state", current.state);
    setBinding("v7.sequence.progress", `${completed} / ${total}`);
    setBinding("v7.sequence.current", exposure ? `${current.current_index + 1}: ${exposure.frame_type} ${exposure.exp_time_s} s${current.active_exposure ? " (active)" : ""}` : "complete");
    setBinding("v7.sequence.summary", runtime.lastError || current.message || `${command}: completed`);
    refreshButtons();
    broadcastSnapshot(current);
    window.dispatchEvent(new CustomEvent("justls:v7-local-refresh", { detail: { source: "sequence", command } }));
  }

  function setBusy(value) {
    runtime.busy = value;
    if (value) {
      const host = panel();
      if (host) host.querySelectorAll("button[data-action]").forEach((button) => { button.disabled = true; });
      return;
    }
    refreshButtons();
  }

  function refreshButtons() {
    const host = panel();
    if (!host) return;
    const snapshot = runtime.snapshot;
    const state = snapshot && snapshot.state;
    const active = Boolean(snapshot && snapshot.active_exposure);
    const terminal = ["completed", "aborted", "failed"].includes(state);
    const abortConfirmed = Boolean(host.querySelector('[data-role="sequence-abort-confirm"]:checked'));
    const rules = {
      "sequence-preview": !runtime.busy,
      "sequence-load": !runtime.busy && (!snapshot || terminal),
      "sequence-start": !runtime.busy && !active && ["loaded", "running"].includes(state),
      "sequence-finish-step": !runtime.busy && active,
      "sequence-stop-readout-step": !runtime.busy && active,
      "sequence-pause": !runtime.busy && ["loaded", "running"].includes(state),
      "sequence-resume": !runtime.busy && state === "paused",
      "sequence-abort": !runtime.busy && Boolean(snapshot) && !terminal && abortConfirmed,
    };
    Object.entries(rules).forEach(([name, allowed]) => {
      const button = host.querySelector(`[data-action="${name}"]`);
      if (button) {
        button.disabled = !allowed;
        button.setAttribute("data-sequence-available", allowed ? "true" : "false");
      }
    });
  }

  async function request(command, body) {
    if (runtime.busy) return;
    setBusy(true);
    try {
      const response = await fetch(ENDPOINTS[command], {
        method: command === "status" ? "GET" : "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        cache: "no-store",
        body: body ? JSON.stringify(body) : undefined,
      });
      runtime.lastRequestId = requestIdFrom(response);
      const payload = await response.json();
      render(payload, command);
      return payload;
    } catch (error) {
      runtime.lastError = error && error.message ? error.message : "request failed";
      render({ error: { code: "client_error", message: runtime.lastError } }, command);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function abortSequence() {
    const host = panel();
    const confirm = host && host.querySelector('[data-role="sequence-abort-confirm"]');
    if (!confirm || !confirm.checked) {
      runtime.lastError = "Explicit checkbox is required.";
      render({ error: { code: "confirmation_required", message: runtime.lastError } }, "abort");
      return;
    }
    const payload = await request("abort");
    if (payload && payload.ok) confirm.checked = false;
    refreshButtons();
  }

  function bindEvents() {
    const host = panel();
    if (!host) return;
    const actions = {
      "sequence-preview": () => request("preview", readPlan()),
      "sequence-load": () => request("load", readPlanForLoad()),
      "sequence-start": () => request("start"),
      "sequence-finish-step": () => request("finish_step"),
      "sequence-stop-readout-step": () => request("stop_readout_step"),
      "sequence-pause": () => request("pause"),
      "sequence-resume": () => request("resume"),
      "sequence-abort": abortSequence,
    };
    Object.entries(actions).forEach(([name, handler]) => {
      const button = host.querySelector(`[data-action="${name}"]`);
      if (!button || button.dataset.bound) return;
      button.dataset.bound = "true";
      button.addEventListener("click", () => {
        try { handler(); }
        catch (error) {
          runtime.lastError = error && error.message ? error.message : "invalid plan";
          render({ error: { code: "validation_error", message: runtime.lastError } }, name);
        }
      });
    });
    const abortConfirm = host.querySelector('[data-role="sequence-abort-confirm"]');
    if (abortConfirm && !abortConfirm.dataset.bound) {
      abortConfirm.dataset.bound = "true";
      abortConfirm.addEventListener("change", refreshButtons);
    }
    const planInput = host.querySelector('[data-role="sequence-plan-steps"]');
    if (planInput && !planInput.dataset.previewBound) {
      planInput.dataset.previewBound = "true";
      planInput.addEventListener("input", () => { runtime.previewPlan = null; });
    }
  }

  function start() {
    const host = panel();
    if (!host) return;
    host.setAttribute("data-runtime", "enabled");
    bindEvents();
    refreshButtons();
    if (runtime.started) return;
    runtime.started = true;
    request("status");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
