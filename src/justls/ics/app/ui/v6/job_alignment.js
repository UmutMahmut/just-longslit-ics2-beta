// v6 job alignment adapter.
// Moved from ui/phase2d6_job_alignment.js to keep UI assets organized by shell version.

(function () {
  "use strict";

  function setText(selector, value) {
    const el = typeof selector === "string" ? document.querySelector(selector) : selector;
    if (el) el.textContent = value == null || value === "" ? "—" : String(value);
  }

  function ensureJobPanel() {
    let panel = document.querySelector("[data-phase2d6-job-panel]");
    if (panel) return panel;

    const commandPanel = document.querySelector("[data-phase2d6-command-panel]");
    const rail = document.querySelector(".message-rail");
    panel = document.createElement("div");
    panel.setAttribute("data-phase2d6-job-panel", "true");
    panel.innerHTML = `
      <span class="mini-badge">Latest Job: <code data-bind="job.status">none</code></span>
      <span class="mini-badge">Subsystem: <code data-bind="job.subsystem">—</code></span>
      <span class="mini-badge">Action: <code data-bind="job.action">—</code></span>
      <span class="mini-badge">Job ID: <code data-bind="job.id">—</code></span>
      <span class="mini-badge">Error: <code data-bind="job.error">—</code></span>
      <span class="mini-badge">Alignment: <code data-bind="job.alignment">waiting</code></span>
    `;
    panel.style.display = "flex";
    panel.style.flexWrap = "wrap";
    panel.style.gap = "8px";
    panel.style.margin = "10px 18px";

    if (commandPanel && commandPanel.parentElement) {
      commandPanel.parentElement.insertBefore(panel, commandPanel.nextSibling);
    } else if (rail && rail.parentElement) {
      rail.parentElement.insertBefore(panel, rail.nextSibling);
    } else {
      document.body.prepend(panel);
    }
    return panel;
  }

  function latestJobFromStatus(data) {
    return data?.operational_status?.latest_job || null;
  }

  function jobRequest(job) {
    return job?.request || job?.command || {};
  }

  function jobError(job) {
    const error = job?.error;
    if (!error) return "—";
    if (typeof error === "string") return error;
    return error.code || error.message || "error";
  }

  function commandResultAlignment(commandResult, latestJob) {
    if (!commandResult && !latestJob) return "waiting";
    if (commandResult && !latestJob) return "command-only";
    if (!commandResult && latestJob) return "status-only";

    const command = commandResult.command || "";
    const request = jobRequest(latestJob);
    const jobCommand = [request.subsystem, request.action].filter(Boolean).join(".");
    if (!command || !jobCommand) return "available";
    return command.includes(jobCommand) || jobCommand.includes(command.split(".").slice(-1)[0])
      ? "aligned"
      : "check";
  }

  function updateJobPanel(data) {
    const panel = ensureJobPanel();
    const latestJob = latestJobFromStatus(data);
    const lastCommand = window.__phase2d6LastCommandResult || null;

    if (!latestJob) {
      setText(panel.querySelector("[data-bind='job.status']"), "none");
      setText(panel.querySelector("[data-bind='job.subsystem']"), "—");
      setText(panel.querySelector("[data-bind='job.action']"), "—");
      setText(panel.querySelector("[data-bind='job.id']"), "—");
      setText(panel.querySelector("[data-bind='job.error']"), "—");
      setText(panel.querySelector("[data-bind='job.alignment']"), commandResultAlignment(lastCommand, null));
      return;
    }

    const request = jobRequest(latestJob);
    setText(panel.querySelector("[data-bind='job.status']"), latestJob.status || "unknown");
    setText(panel.querySelector("[data-bind='job.subsystem']"), request.subsystem || latestJob.subsystem || "—");
    setText(panel.querySelector("[data-bind='job.action']"), request.action || latestJob.action || "—");
    setText(panel.querySelector("[data-bind='job.id']"), latestJob.job_id || latestJob.id || "—");
    setText(panel.querySelector("[data-bind='job.error']"), jobError(latestJob));
    setText(panel.querySelector("[data-bind='job.alignment']"), commandResultAlignment(lastCommand, latestJob));
  }

  function updateDebugWithJob(data) {
    const debug = document.querySelector("[data-bind='debug.status']");
    if (!debug || debug.dataset.phase2d6CommandOutput) return;
    debug.textContent = JSON.stringify(
      {
        latest_job: latestJobFromStatus(data),
        command_result: window.__phase2d6LastCommandResult || null,
        operational_status: data?.operational_status || null,
        timestamp_utc: data?.timestamp_utc || null,
      },
      null,
      2,
    );
  }

  function installListeners() {
    window.addEventListener("phase2d6:status-full", (event) => {
      const data = event.detail?.data || {};
      window.__phase2d6StatusFull = data;
      updateJobPanel(data);
      updateDebugWithJob(data);
    });

    window.addEventListener("phase2d6:command-result", (event) => {
      window.__phase2d6LastCommandResult = event.detail || null;
      if (window.__phase2d6StatusFull) {
        updateJobPanel(window.__phase2d6StatusFull);
      }
    });
  }

  function start() {
    ensureJobPanel();
    installListeners();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
