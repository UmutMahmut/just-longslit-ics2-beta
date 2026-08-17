// v7 setup runtime adapter. Default-on during Phase 2.9-F.

(function () {
  "use strict";

  const GLOBAL_KEY = "__JUSTLS_V7_SETUP_RUNTIME__";
  const SETUP_CONTEXT_ENDPOINT = "/api/v1/setup/context";
  const SETUP_CONTEXT_RELOAD_ENDPOINT = "/api/v1/setup/context/reload";

  const SETUP_FIELDS = [
    "observers",
    "project_id",
    "pi_name",
    "support_operator",
    "root_name",
    "date_prefix",
    "comment",
    "next_frame_index",
    "data_directory",
  ];

  const runtime = window[GLOBAL_KEY] || {
    started: false,
    loading: false,
    saving: false,
    reloading: false,
    context: null,
    lastError: null,
    lastRequestId: null,
    lastCommand: null,
  };
  window[GLOBAL_KEY] = runtime;

  function text(value, fallback) {
    if (value === null || value === undefined || value === "") return fallback;
    return String(value);
  }

  function setText(node, value) {
    if (!node) return;
    const next = text(value, "");
    if (node.textContent !== next) node.textContent = next;
  }

  function setupPage() {
    return document.querySelector('[data-page-panel="setup"]');
  }

  function bind(name) {
    const page = setupPage();
    return page ? page.querySelector(`[data-bind="${name}"]`) : null;
  }

  function input(field) {
    const page = setupPage();
    return page ? page.querySelector(`[data-role="session-input"][data-field="${field}"]`) : null;
  }

  function action(name) {
    const page = setupPage();
    return page ? page.querySelector(`[data-action="${name}"]`) : null;
  }

  function setDisabled(node, value) {
    if (node && node.disabled !== value) node.disabled = value;
  }

  function setStatus(message) {
    setText(bind("v7.setup.save_status"), message);
    setText(bind("v7.setup.last_command"), runtime.lastCommand || "none");
    setText(bind("v7.setup.request_id"), runtime.lastRequestId || "not available");
    setText(bind("v7.setup.last_error"), runtime.lastError || "none");
    setText(bind("v7.setup.result_summary"), message);
  }

  function requestIdFrom(response) {
    return response.headers.get("x-request-id") || response.headers.get("X-Request-ID") || runtime.lastRequestId;
  }

  function applyContext(context) {
    runtime.context = context || {};

    SETUP_FIELDS.forEach((field) => {
      const node = input(field);
      if (!node) return;
      node.value = text(runtime.context[field], field === "date_prefix" ? "AUTO" : "");
    });

    setText(bind("v7.data.next_frame_token"), text(runtime.context.next_frame_token, "AUTO-0001"));
    setText(bind("v7.data.directory"), text(runtime.context.data_directory, "not configured"));
    setText(bind("v7.data.file_stem"), text(runtime.context.file_stem, "not available"));
    setText(bind("v7.data.fits_filename"), text(runtime.context.fits_filename, "not available"));
    setText(bind("v7.setup.persistence_status"), "Persisted backend context");
  }

  function collectPayload() {
    const payload = {};
    SETUP_FIELDS.forEach((field) => {
      const node = input(field);
      if (!node) return;
      if (field === "next_frame_index") {
        payload[field] = Number(node.value || 1);
      } else {
        payload[field] = node.value || "";
      }
    });
    return payload;
  }

  async function loadContext() {
    if (runtime.loading) return;
    runtime.loading = true;
    runtime.lastError = null;
    runtime.lastCommand = "load_setup_context";
    setStatus("Loading setup context...");
    try {
      const response = await fetch(SETUP_CONTEXT_ENDPOINT, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      runtime.lastRequestId = requestIdFrom(response);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ? payload.detail.message : `GET failed ${response.status}`);
      applyContext(payload);
      setStatus("Loaded from backend");
    } catch (error) {
      runtime.lastError = text(error && error.message, "failed");
      setStatus(`Load failed: ${runtime.lastError}`);
    } finally {
      runtime.loading = false;
      refreshButtons();
    }
  }

  async function saveContext() {
    if (runtime.saving) return;
    runtime.saving = true;
    runtime.lastError = null;
    runtime.lastCommand = "save_setup_context";
    refreshButtons();
    setStatus("Saving setup context...");
    try {
      const response = await fetch(SETUP_CONTEXT_ENDPOINT, {
        method: "PUT",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify(collectPayload()),
      });
      runtime.lastRequestId = requestIdFrom(response);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ? payload.detail.message : `PUT failed ${response.status}`);
      applyContext(payload);
      setStatus("Saved to backend");
    } catch (error) {
      runtime.lastError = text(error && error.message, "failed");
      setStatus(`Save failed: ${runtime.lastError}`);
    } finally {
      runtime.saving = false;
      refreshButtons();
    }
  }

  async function reloadContext() {
    if (runtime.reloading) return;
    runtime.reloading = true;
    runtime.lastError = null;
    runtime.lastCommand = "reload_setup_context";
    refreshButtons();
    setStatus("Reloading setup context...");
    try {
      const response = await fetch(SETUP_CONTEXT_RELOAD_ENDPOINT, {
        method: "POST",
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      runtime.lastRequestId = requestIdFrom(response);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ? payload.detail.message : `reload failed ${response.status}`);
      applyContext(payload);
      setStatus("Reloaded from backend");
    } catch (error) {
      runtime.lastError = text(error && error.message, "failed");
      setStatus(`Reload failed: ${runtime.lastError}`);
    } finally {
      runtime.reloading = false;
      refreshButtons();
    }
  }

  function refreshButtons() {
    const busy = runtime.loading || runtime.saving || runtime.reloading;
    setDisabled(action("setup-save-context"), busy);
    setDisabled(action("setup-reload-context"), busy);
  }

  function bindEvents() {
    const saveButton = action("setup-save-context");
    if (saveButton && !saveButton.dataset.bound) {
      saveButton.dataset.bound = "true";
      saveButton.addEventListener("click", saveContext);
    }

    const reloadButton = action("setup-reload-context");
    if (reloadButton && !reloadButton.dataset.bound) {
      reloadButton.dataset.bound = "true";
      reloadButton.addEventListener("click", reloadContext);
    }

    SETUP_FIELDS.forEach((field) => {
      const node = input(field);
      if (!node || node.dataset.bound) return;
      node.dataset.bound = "true";
      node.addEventListener("input", () => setStatus("Unsaved local edits"));
      node.addEventListener("change", () => setStatus("Unsaved local edits"));
    });
  }

  function start() {
    if (runtime.started) return;
    runtime.started = true;
    const page = setupPage();
    if (!page) return;
    page.setAttribute("data-runtime", "enabled");
    bindEvents();
    refreshButtons();
    loadContext();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
