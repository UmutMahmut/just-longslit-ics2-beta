// v6 command runtime adapter.
// Moved from ui/phase2d6_command_runtime.js to keep UI assets organized by shell version.

(function () {
  "use strict";

  const COMMAND_TIMEOUT_MS = 3000;
  let commandInFlight = false;

  function setText(selector, value) {
    const el = typeof selector === "string" ? document.querySelector(selector) : selector;
    if (el) el.textContent = value == null ? "—" : String(value);
  }

  function emitCommandResult(detail) {
    window.__phase2d6LastCommandResult = detail;
    window.dispatchEvent(new CustomEvent("phase2d6:command-result", { detail }));
  }

  function ensureCommandPanel() {
    let panel = document.querySelector("[data-phase2d6-command-panel]");
    if (panel) return panel;

    const rail = document.querySelector(".message-rail");
    panel = document.createElement("div");
    panel.setAttribute("data-phase2d6-command-panel", "true");
    panel.innerHTML = `
      <span class="mini-badge">Command: <code data-bind="command.status">idle</code></span>
      <span class="mini-badge">Action: <code data-bind="command.last_action">—</code></span>
      <span class="mini-badge">Request ID: <code data-bind="command.request_id">—</code></span>
    `;
    panel.style.display = "flex";
    panel.style.flexWrap = "wrap";
    panel.style.gap = "8px";
    panel.style.margin = "10px 18px";

    if (rail && rail.parentElement) {
      rail.parentElement.insertBefore(panel, rail.nextSibling);
    } else {
      document.body.prepend(panel);
    }
    return panel;
  }

  function setRail(level, message) {
    const rail = document.querySelector(".message-rail");
    if (!rail) return;
    rail.setAttribute("data-level", level);
    const body = rail.querySelector(".rail-body-text") || rail.querySelector(".rail-body");
    if (body) body.textContent = message;
  }

  function markDebugPayload(payload) {
    const debug = document.querySelector("[data-bind='debug.status']");
    if (!debug) return;
    debug.dataset.phase2d6CommandOutput = "true";
    debug.textContent = JSON.stringify(payload, null, 2);
  }

  function commandName(button) {
    return (
      button.getAttribute("data-command") ||
      button.getAttribute("data-risk") ||
      button.textContent ||
      "command"
    ).trim();
  }

  function buildClientRequestId(command) {
    const cleanCommand = command.replace(/[^a-z0-9_.-]+/gi, "-").toLowerCase();
    const randomPart = Math.random().toString(16).slice(2, 10);
    return `ui-${cleanCommand}-${Date.now()}-${randomPart}`;
  }

  function bodyFor(button) {
    const command = (button.getAttribute("data-command") || "").trim();
    if (command === "observation.arm") {
      return {
        exp_time_s: Number(document.getElementById("exp-time")?.value || 0),
        frame_type: document.getElementById("frame-type")?.value || "science",
        operator_note: document.getElementById("operator-note")?.value || null,
      };
    }
    if (button.dataset.presetName) {
      return {
        name: button.dataset.presetName,
        confirmed: true,
      };
    }
    if (button.dataset.calibrationMode) return { mode: button.dataset.calibrationMode };
    return null;
  }

  function requireConfirmation(button) {
    const command = button.getAttribute("data-command") || "";
    if (button.dataset.presetName) {
      return window.confirm(`Apply preset ${button.dataset.presetName}?`);
    }
    if (command === "observation.abort_discard") {
      return window.confirm("Confirm abort and discard?");
    }
    if (command === "observation.stop_readout") {
      return window.confirm("Confirm stop and readout?");
    }
    return true;
  }

  async function postJsonWithTimeout(path, body, requestId) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), COMMAND_TIMEOUT_MS);
    try {
      const response = await fetch(path, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-Request-ID": requestId,
        },
        body: body == null ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
      const data = await response.json().catch(() => ({}));
      const responseRequestId = response.headers.get("X-Request-ID") || requestId;
      if (!response.ok) {
        const message = data?.detail?.message || `Command failed: ${response.status}`;
        const error = new Error(message);
        error.status = response.status;
        error.payload = data;
        error.requestId = responseRequestId;
        throw error;
      }
      return { data, requestId: responseRequestId, status: response.status };
    } finally {
      window.clearTimeout(timeoutId);
    }
  }

  function refreshSoon() {
    window.setTimeout(() => {
      const button = document.querySelector('[data-command="status.refresh"]');
      if (button) button.click();
    }, 150);
  }

  function setCommandStatus(status, command, requestId) {
    ensureCommandPanel();
    setText("[data-bind='command.status']", status);
    setText("[data-bind='command.last_action']", command || "—");
    setText("[data-bind='command.request_id']", requestId || "—");
  }

  async function handleCommandClick(event) {
    const button = event.target.closest("button[data-api-path]");
    if (!button || button.disabled) return;

    event.preventDefault();
    event.stopImmediatePropagation();

    const command = commandName(button);
    if (commandInFlight) {
      setRail("warning", "Another command is already in progress; wait for it to finish.");
      return;
    }
    if (!requireConfirmation(button)) return;

    const requestId = buildClientRequestId(command);
    commandInFlight = true;
    setCommandStatus("running", command, requestId);
    setRail("info", `Running ${command}...`);

    try {
      const result = await postJsonWithTimeout(button.dataset.apiPath, bodyFor(button), requestId);
      const payload = {
        command,
        request_id: result.requestId,
        status: result.status,
        result: result.data,
      };
      setCommandStatus("succeeded", command, result.requestId);
      setRail("success", `${command} completed.`);
      markDebugPayload(payload);
      emitCommandResult({ ...payload, outcome: "succeeded" });
      refreshSoon();
    } catch (err) {
      const timedOut = err.name === "AbortError";
      const visibleMessage = timedOut
        ? `${command} timed out after ${(COMMAND_TIMEOUT_MS / 1000).toFixed(1)} s.`
        : err.message || `${command} failed.`;
      const payload = {
        command,
        request_id: err.requestId || requestId,
        error: visibleMessage,
        status: err.status || null,
        detail: err.payload || null,
      };
      setCommandStatus(timedOut ? "timeout" : "failed", command, err.requestId || requestId);
      setRail("error", visibleMessage);
      markDebugPayload(payload);
      emitCommandResult({ ...payload, outcome: timedOut ? "timeout" : "failed" });
    } finally {
      commandInFlight = false;
    }
  }

  function start() {
    ensureCommandPanel();
    document.addEventListener("click", handleCommandClick, true);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
