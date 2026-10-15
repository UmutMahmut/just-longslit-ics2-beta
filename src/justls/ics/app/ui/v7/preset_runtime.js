// v7 preset runtime adapter. Default-on during Phase 2.9-F.

(function () {
  "use strict";

  const GLOBAL_KEY = "__JUSTLS_V7_PRESET_RUNTIME__";
  const PRESETS_ENDPOINT = "/api/v1/presets";
  const PREVIEW_ENDPOINT = "/api/v1/presets/preview";
  const APPLY_ENDPOINT = "/api/v1/presets/apply";

  const runtime = window[GLOBAL_KEY] || {
    started: false,
    catalogLoading: false,
    previewInFlight: false,
    applying: false,
    items: [],
    preview: null,
    lastPreview: null,
    lastApplyResult: null,
    lastError: null,
    catalogLoadedAt: null,
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

  function setDisabled(button, value) {
    if (button && button.disabled !== value) button.disabled = value;
  }

  function page() {
    return document.querySelector('[data-page-panel="presets"]');
  }

  function createFallbackPanel() {
    const host = page();
    if (!host) return null;

    const panel = document.createElement("section");
    panel.id = "v7-presets-runtime";
    panel.className = "panel";
    panel.setAttribute("data-role", "v7-presets-panel");
    panel.setAttribute("data-origin", "runtime-created-presets-skeleton");
    panel.setAttribute("data-phase", "2.8-runtime-opt-in");
    panel.innerHTML = `
      <h2>Presets · Catalog / Preview / Guarded Apply</h2>
      <div class="panel-body">
        <div class="badge demo" data-bind="v7.presets.status">loading preset catalog...</div>
        <dl class="kv">
          <dt>Catalog Loaded</dt><dd><code data-bind="v7.presets.catalog_loaded_at">not loaded</code></dd>
          <dt>Runtime State</dt><dd><code data-bind="v7.presets.runtime_state">idle</code></dd>
          <dt>Last Error</dt><dd><code data-bind="v7.presets.last_error">none</code></dd>
        </dl>
        <table class="table" style="margin-top: 10px;">
          <thead><tr><th>Name</th><th>Category</th><th>Risk</th><th>Confirm</th><th>Action</th></tr></thead>
          <tbody data-bind="v7.presets.catalog"></tbody>
        </table>
        <h3>Preview Result</h3>
        <pre data-bind="v7.presets.preview">Select Preview for a preset.</pre>
        <h3>Guarded Apply</h3>
        <div data-role="v7-preset-confirmation" hidden>
          <label><input type="checkbox" data-role="confirm-risk-checkbox" /> I understand this preset requires confirmation.</label>
          <input data-role="confirm-preset-name" placeholder="Type exact preset name" />
        </div>
        <button class="btn primary" type="button" data-action="apply-previewed-preset" disabled>Apply Previewed Preset</button>
        <pre data-bind="v7.presets.apply_result">No apply request sent.</pre>
      </div>`;

    // The normal v7 shell owns #v7-presets-runtime. This fallback is only for a
    // future or alternate shell missing that durable skeleton. In that case,
    // replace the Presets page content with a single runtime-created panel so
    // the operator never sees competing Presets UIs.
    host.replaceChildren(panel);
    return panel;
  }

  function bindPanelEvents(panel) {
    const applyButton = panel.querySelector('[data-action="apply-previewed-preset"]');
    if (applyButton && !applyButton.dataset.bound) {
      applyButton.dataset.bound = "true";
      applyButton.addEventListener("click", applyPreviewedPreset);
    }

    panel.querySelectorAll('[data-role="confirm-risk-checkbox"], [data-role="confirm-preset-name"]').forEach((node) => {
      if (node.dataset.bound) return;
      node.dataset.bound = "true";
      node.addEventListener("input", refreshApplyGuard);
      node.addEventListener("change", refreshApplyGuard);
    });
  }

  function enhancePanel(panel) {
    panel.setAttribute("data-runtime", "enabled");
    panel.setAttribute("data-phase", "2.8-runtime-opt-in");
    bindPanelEvents(panel);
    return panel;
  }

  function ensurePanel() {
    const existing = document.getElementById("v7-presets-runtime");
    const panel = existing || createFallbackPanel();
    return panel ? enhancePanel(panel) : null;
  }

  function bind(name) {
    const panel = ensurePanel();
    return panel ? panel.querySelector(`[data-bind="${name}"]`) : null;
  }

  function runtimeStateLabel() {
    if (runtime.catalogLoading) return "loading catalog";
    if (runtime.previewInFlight) return "loading preview";
    if (runtime.applying) return "applying preset";
    return runtime.started ? "ready" : "idle";
  }

  function refreshRuntimeState() {
    setText(bind("v7.presets.catalog_loaded_at"), runtime.catalogLoadedAt || "not loaded");
    setText(bind("v7.presets.runtime_state"), runtimeStateLabel());
    setText(bind("v7.presets.last_error"), runtime.lastError || "none");
    setText(bind("v7.presets.last_command"), runtime.lastCommand || "none");
    setText(bind("v7.presets.request_id"), runtime.lastRequestId || "not available");
    const job = runtime.lastApplyResult && (runtime.lastApplyResult.latest_job || runtime.lastApplyResult.job_id);
    setText(bind("v7.presets.latest_job"), job ? (typeof job === "string" ? job : [job.status, job.job_id].filter(Boolean).join(" - ")) : "not available");
    const summary = runtime.lastError
      ? `${runtime.lastCommand || "preset"}: ${runtime.lastError}`
      : runtime.lastCommand
        ? `${runtime.lastCommand}: succeeded`
        : "ready";
    setText(bind("v7.presets.result_summary"), summary);
  }

  function requestIdFrom(response) {
    return response.headers.get("x-request-id") || response.headers.get("X-Request-ID") || runtime.lastRequestId;
  }

  function errorMessage(payload, response) {
    const detail = payload && payload.detail;
    if (detail && detail.message) return `${detail.code || "error"}: ${detail.message}`;
    return `HTTP ${response.status}`;
  }

  function renderCatalog() {
    const body = bind("v7.presets.catalog");
    if (!body) return;

    body.innerHTML = "";
    runtime.items.forEach((item) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td><code>${item.name}</code></td>
        <td>${item.category || "unknown"}</td>
        <td>${item.risk_level || "unknown"}</td>
        <td>${item.requires_confirmation ? "yes" : "no"}</td>
        <td><button class="btn" type="button" data-preset-name="${item.name}">Preview</button></td>`;
      const button = row.querySelector("button");
      button.addEventListener("click", () => previewPreset(item.name));
      body.appendChild(row);
    });
  }

  function setCatalogButtonsDisabled(value) {
    const panel = ensurePanel();
    if (!panel) return;
    panel.querySelectorAll("button[data-preset-name]").forEach((button) => {
      setDisabled(button, value);
    });
  }

  async function fetchCatalog() {
    if (runtime.catalogLoading) return;
    if (runtime.catalogLoadedAt && runtime.items.length > 0) {
      renderCatalog();
      refreshRuntimeState();
      return;
    }

    runtime.catalogLoading = true;
    runtime.lastError = null;
    refreshRuntimeState();
    setText(bind("v7.presets.status"), `loading ${PRESETS_ENDPOINT}...`);
    try {
      const response = await fetch(PRESETS_ENDPOINT, { cache: "no-store", headers: { Accept: "application/json" } });
      runtime.lastRequestId = requestIdFrom(response);
      const payload = await response.json();
      if (!response.ok) throw new Error(errorMessage(payload, response));
      runtime.items = Array.isArray(payload.items) ? payload.items : [];
      runtime.catalogLoadedAt = new Date().toISOString();
      renderCatalog();
      setText(bind("v7.presets.status"), `loaded ${runtime.items.length} presets`);
    } catch (error) {
      runtime.lastError = text(error && error.message, "failed");
      setText(bind("v7.presets.status"), `catalog error: ${runtime.lastError}`);
    } finally {
      runtime.catalogLoading = false;
      refreshRuntimeState();
    }
  }

  async function previewPreset(name) {
    if (runtime.previewInFlight || runtime.applying) return;

    runtime.previewInFlight = true;
    runtime.lastError = null;
    runtime.lastCommand = "preview_preset";
    setCatalogButtonsDisabled(true);
    refreshRuntimeState();
    setText(bind("v7.presets.status"), `previewing ${name}...`);
    try {
      const response = await fetch(PREVIEW_ENDPOINT, {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ name, confirmed: false }),
      });
      runtime.lastRequestId = requestIdFrom(response);
      const payload = await response.json();
      if (!response.ok) throw new Error(errorMessage(payload, response));
      runtime.preview = payload;
      runtime.lastPreview = payload;
      setText(bind("v7.presets.preview"), JSON.stringify(payload, null, 2));
      setText(bind("v7.presets.status"), response.ok ? `preview loaded for ${name}` : `preview error ${response.status}`);
    } catch (error) {
      runtime.preview = null;
      runtime.lastError = text(error && error.message, "failed");
      setText(bind("v7.presets.preview"), JSON.stringify({ preset: name, error: runtime.lastError }, null, 2));
    } finally {
      runtime.previewInFlight = false;
      setCatalogButtonsDisabled(false);
      refreshApplyGuard();
      refreshRuntimeState();
    }
  }

  function confirmationOk(panel) {
    if (!runtime.preview || !runtime.preview.requires_confirmation) return true;
    const checkbox = panel.querySelector('[data-role="confirm-risk-checkbox"]');
    const input = panel.querySelector('[data-role="confirm-preset-name"]');
    return Boolean(checkbox && checkbox.checked && input && input.value === runtime.preview.preset);
  }

  function refreshApplyGuard() {
    const panel = ensurePanel();
    if (!panel) return;
    const confirmBlock = panel.querySelector('[data-role="v7-preset-confirmation"]');
    const button = panel.querySelector('[data-action="apply-previewed-preset"]');
    const blocked = Boolean(runtime.preview && runtime.preview.blocked);
    const hasPreview = Boolean(runtime.preview && runtime.preview.preset);
    const needsConfirm = Boolean(runtime.preview && runtime.preview.requires_confirmation);
    if (confirmBlock) confirmBlock.hidden = !needsConfirm;
    if (button) {
      setDisabled(button, runtime.applying || runtime.previewInFlight || !hasPreview || blocked || !confirmationOk(panel));
      setText(button, runtime.applying ? "Applying..." : "Apply Previewed Preset");
    }
  }

  async function applyPreviewedPreset() {
    const panel = ensurePanel();
    if (!panel || !runtime.preview || !runtime.preview.preset || !confirmationOk(panel)) return;
    if (runtime.applying || runtime.previewInFlight) return;

    runtime.applying = true;
    runtime.lastError = null;
    runtime.lastCommand = "apply_preset";
    refreshApplyGuard();
    refreshRuntimeState();
    setText(bind("v7.presets.apply_result"), "sending guarded apply request...");
    try {
      const response = await fetch(APPLY_ENDPOINT, {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ name: runtime.preview.preset, confirmed: Boolean(runtime.preview.requires_confirmation) }),
      });
      runtime.lastRequestId = requestIdFrom(response);
      const payload = await response.json();
      if (!response.ok) throw new Error(errorMessage(payload, response));
      runtime.lastApplyResult = payload;
      setText(bind("v7.presets.apply_result"), JSON.stringify(payload, null, 2));
    } catch (error) {
      runtime.lastError = text(error && error.message, "failed");
      runtime.lastApplyResult = { error: runtime.lastError };
      setText(bind("v7.presets.apply_result"), JSON.stringify(runtime.lastApplyResult, null, 2));
    } finally {
      runtime.applying = false;
      refreshApplyGuard();
      refreshRuntimeState();
    }
  }

  function start() {
    ensurePanel();
    refreshRuntimeState();

    if (runtime.started) {
      renderCatalog();
      refreshApplyGuard();
      return;
    }

    runtime.started = true;
    fetchCatalog();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
