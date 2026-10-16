// v7 observe button guard. Default-on with the operator workflow runtime.
// This frontend-only guard does not call backend APIs.

(function () {
  "use strict";

  const GLOBAL_KEY = "__JUSTLS_V7_OBSERVE_GUARD__";

  const runtime = window[GLOBAL_KEY] || {
    started: false,
    observer: null,
    retryTimer: null,
    lastAllowed: null,
    sequenceActive: false,
  };
  window[GLOBAL_KEY] = runtime;

  function text(value, fallback) {
    if (value === null || value === undefined || value === "") return fallback;
    return String(value);
  }

  function panel() {
    return document.getElementById("v7-observe-controls");
  }

  function currentState() {
    const node = document.querySelector('[data-bind="v7.observe.state"]');
    return text(node && node.textContent, "unknown").toLowerCase();
  }

  function armedLabel() {
    const node = document.querySelector('[data-bind="v7.observe.armed"]');
    return text(node && node.textContent, "not armed").toLowerCase();
  }

  function allowed() {
    if (runtime.sequenceActive) {
      return {
        "obs-arm": false,
        "obs-start": false,
        "obs-finish": false,
        "obs-stop-readout": false,
        "obs-abort-discard": false,
      };
    }
    const name = currentState();
    const armed = armedLabel() !== "not armed" || name.includes("armed");
    const active = name.includes("expos") || name.includes("integrat") || name.includes("running");
    const reading = name.includes("readout") || name.includes("reading");
    // "discarded"/"aborted" must count as ready: after an abort the detector is
    // idle again and the very next thing the operator does is re-arm. Treating
    // these as non-ready would lock the panel permanently after one abort.
    const ready =
      name === "unknown" ||
      name.includes("idle") ||
      name.includes("ready") ||
      name.includes("complete") ||
      name.includes("finish") ||
      name.includes("discard") ||
      name.includes("abort") ||
      name.includes("error") ||
      name.includes("fail");
    return {
      "obs-arm": ready && !active && !reading,
      "obs-start": armed && !active && !reading,
      "obs-finish": active,
      "obs-stop-readout": armed || active || reading,
      // The backend rejects a save when there is nothing to save, so the guard
      // only has to keep it out of the way during acquisition.
      "obs-save-last": !active && !reading,
      "obs-abort-discard": armed || active || reading,
    };
  }

  function setDisabled(button, value) {
    if (button && button.disabled !== value) button.disabled = value;
  }

  function refresh() {
    const host = panel();
    if (!host) return;
    const rules = allowed();
    const confirmed = Boolean(host.querySelector('[data-role="obs-abort-confirm"]:checked'));
    Object.entries(rules).forEach(([action, isAllowed]) => {
      const button = host.querySelector(`[data-action="${action}"]`);
      const finalAllowed = action === "obs-abort-discard" ? isAllowed && confirmed : isAllowed;
      setDisabled(button, !finalAllowed);
      if (button) button.setAttribute("data-guard-available", finalAllowed ? "true" : "false");
    });
    runtime.lastAllowed = rules;
  }

  function bindCheckbox(host) {
    const checkbox = host.querySelector('[data-role="obs-abort-confirm"]');
    if (!checkbox || checkbox.dataset.guardBound) return;
    checkbox.dataset.guardBound = "true";
    checkbox.addEventListener("change", refresh);
  }

  function handleSequenceState(event) {
    const snapshot = event && event.detail;
    runtime.sequenceActive = Boolean(snapshot) && !["completed", "aborted", "failed"].includes(snapshot.state);
    refresh();
  }

  function start() {
    const host = panel();
    if (!host) {
      if (!runtime.retryTimer) {
        runtime.retryTimer = window.setTimeout(() => {
          runtime.retryTimer = null;
          start();
        }, 250);
      }
      return;
    }

    bindCheckbox(host);

    if (runtime.started) {
      refresh();
      return;
    }

    runtime.started = true;
    window.addEventListener("justls:v7-observe-state", refresh);
    window.addEventListener("justls:v7-sequence-state", handleSequenceState);

    // Keep a narrow observer as a fallback for skeleton replacement only. The
    // observe runtime dispatches justls:v7-observe-state after status updates,
    // so this observer should not be the primary state propagation path.
    runtime.observer = new MutationObserver(() => window.setTimeout(refresh, 0));
    runtime.observer.observe(host, { childList: true, subtree: false });
    refresh();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
