(function () {
  'use strict';
  const host = document.querySelector('[data-role="camera-acquisition-settings"]');
  if (!host) return;
  async function build(role) {
    const form = document.createElement('form');
    form.dataset.cameraSettings = role;
    const title = document.createElement('h4'); title.textContent = role === 'science' ? 'Science camera' : 'Slit / guide camera'; form.append(title);
    const summary = document.createElement('p'); summary.textContent = 'Loading camera settings…'; form.append(summary); host.append(form);
    let baseline;
    async function load() {
      const response = await fetch(`/api/v1/cameras/${role}/settings`, {cache: 'no-store', signal: AbortSignal.timeout(15000)});
      const data = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(data.detail || data));
      baseline = data; return data;
    }
    function render(data) {
      form.querySelectorAll('label, button').forEach(node => node.remove());
      summary.textContent = `${data.device_id} · ${data.pixel_format} · ROI dimensions are binned output pixels. Changes apply to subsequent captures and reset on service restart.`;
      const fields = ['gain', 'offset', 'binning', 'width', 'height'];
      if (role === 'slit') fields.push('preview_exposure_ms');
      if (data.limits.cooling) fields.push('cooler_target_c', 'cooler_enabled');
      for (const name of fields) {
        const label = document.createElement('label'); label.textContent = name.replaceAll('_', ' ') + ' ';
        const input = document.createElement(name === 'binning' ? 'select' : 'input'); input.name = name;
        if (name === 'binning') for (const bin of data.limits.binning) { const option = document.createElement('option'); option.value = bin; option.textContent = bin; input.append(option); }
        else if (name === 'cooler_enabled') { input.type = 'checkbox'; input.checked = Boolean(data[name]); }
        else {
          input.type = 'number'; input.step = name === 'preview_exposure_ms' ? '0.001' : '1';
          const limit = data.limits[name];
          if (limit) { input.min = limit.min; input.max = limit.max; }
          if (name === 'width' || name === 'height') input.min = 16;
        }
        if (name !== 'cooler_enabled') input.value = data[name] ?? '';
        label.append(input); form.append(label);
      }
      const apply = document.createElement('button'); apply.type = 'submit'; apply.className = 'btn'; apply.textContent = 'Apply Camera Settings'; form.append(apply);
      const reload = document.createElement('button'); reload.type = 'button'; reload.className = 'btn'; reload.textContent = 'Read Settings'; reload.onclick = () => refresh(); form.append(reload);
    }
    async function refresh() {
      try { render(await load()); }
      catch (error) {
        summary.textContent = error.message;
        if (!form.querySelector('button')) {
          const retry = document.createElement('button'); retry.type = 'button'; retry.className = 'btn';
          retry.textContent = 'Read Settings'; retry.onclick = refresh; form.append(retry);
        }
      }
    }
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const changes = {};
      for (const input of form.querySelectorAll('input, select')) {
        if (input.type !== 'checkbox' && !input.value.trim()) continue;
        const value = input.type === 'checkbox' ? input.checked : Number(input.value);
        if (value !== baseline[input.name]) changes[input.name] = value;
      }
      form.querySelectorAll('input, select, button').forEach(control => control.disabled = true);
      try {
        const response = await fetch(`/api/v1/cameras/${role}/settings`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(changes), signal:AbortSignal.timeout(20000)});
        const data = await response.json();
        if (!response.ok) throw new Error(JSON.stringify(data.detail || data));
        baseline = data; render(data); summary.textContent = 'Applied. ' + summary.textContent;
      } catch (error) { summary.textContent = error.message; }
      finally { form.querySelectorAll('input, select, button').forEach(control => control.disabled = false); }
    });
    await refresh();
  }
  build('science'); build('slit');
  window.addEventListener('justls:v7-cameras-reloaded', () => window.location.reload());
})();
