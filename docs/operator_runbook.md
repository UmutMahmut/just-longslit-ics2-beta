# ICS Beta — operator runbook

This is a short document, not a manual. The intent is to keep the
"how do I get the service running and what do I do when it stops
responding" steps in one place so an operator does not have to
re-derive them from the code or the commit log.

## Starting the service

Pick one of:

```powershell
# 1. The provided PowerShell launcher (recommended). It frees the port,
#    wires the env, and (optionally) opens the browser.
cd C:\Users\UmutMahmut\WorkBuddy\2026-10-08-14-03-39\repo
.\start_ics.ps1

# 2. Manual start. The order matters: SDK path + camera config first,
#    then uvicorn.
cd C:\Users\UmutMahmut\WorkBuddy\2026-10-08-14-03-39\repo
$env:ICS_ZWO_SDK_LIBRARY    = "F:\ASIStudio\ASICamera2.dll"
$env:ICS_BETA_CAMERA_CONFIG = "config\cameras.lhires-dual-zwo.example.json"
& "C:\Users\UmutMahmut\.workbuddy\binaries\python\envs\default\Scripts\python.exe" `
    -m uvicorn justls.ics.app.main:app --host 127.0.0.1 --port 8123
```

Open http://127.0.0.1:8123/ui/v7 in the browser.

If the v7 console shows the red **HARDWARE OFFLINE · SAFE MODE** banner,
the service did not bind to the ZWO SDK. See *Safe Mode* below.

## Safe Mode (USB / SDK stuck)

`ICS_BETA_FORCE_SIM=1` switches every ZWO driver to a simulated
fallback. The service stays usable for software work; no science
frames are real. Use it when:

* the 50 cm host is on the bench and the ZWO cameras are not plugged in;
* the SDK is in a known bad state (force-kill left a USB pipe open);
* the operator wants to validate the UI/sequence without hardware.

Add the env line to your shell, or run the launcher with `-ForceSim`:

```powershell
.\start_ics.ps1 -ForceSim
```

The banner will tell you that you are in safe mode. To return to real
hardware, remove the env line and restart the service.

## Hot-plug monitor + Reload Cameras

When a real ZWO camera is bound, a background monitor asks the SDK
every `ICS_BETA_HOTPLUG_INTERVAL_S` seconds (default 30) how many
cameras it sees. The result is surfaced in two places:

* `/api/v1/cameras/status` — the `hot_plug` block has `last_count`,
  `last_check_at`, `last_change_at`, and `last_error`.
* The v7 console, next to the slit camera preview, shows a colour
  badge (`OK`, `changed at …`, `error …`).

A USB change is **never** auto-rebound. Rebinding releases every
camera handle, which aborts any in-flight exposure. Instead, the
operator clicks **Reload Cameras** in the v7 console (or POSTs to
`/api/v1/cameras/reload`). The endpoint asks for a confirmation
prompt in the UI because the reload is destructive.

## When something goes wrong

1. **The console still shows stale "unavailable" text after a
   restart.** Hard-reload the page (`Ctrl+F5`). The static shell
   keeps the last status text on screen until a fresh `/api/v1/
   cameras/status` comes back; the page-cache is usually the cause.
2. **Arm / Start buttons are grey.** Something else is already
   `running`; the v7 observe guard is doing its job. Check the
   observe command summary on the right side of the page.
3. **The ZWO SDK never comes back (no banner, but cameras/status
   shows `force_sim=false` and a science camera missing).** Stop the
   service, **do not** `taskkill /F` it, restart the host. The
   `start_ics.ps1` script can stop and restart in one go.
4. **The service keeps logging "watchdog timeout".** That is the
   safety net doing its job: the SDK is stuck, we have not crashed
   the worker, the user is still in control. Click *Reload Cameras*
   once the device is healthy.

## Environment variables

See `.env.example` next to the launcher. The list there is the
authoritative reference; the most-used values are:

| Variable | Default | Notes |
| --- | --- | --- |
| `ICS_ZWO_SDK_LIBRARY` | (auto) | Absolute path to `ASICamera2.dll`. |
| `ICS_BETA_CAMERA_CONFIG` | (auto) | Camera profile JSON. |
| `ICS_BETA_FORCE_SIM` | `0` | Set to `1` to enter safe mode. |
| `ICS_BETA_HOTPLUG_INTERVAL_S` | `30` | Hot-plug monitor poll interval. |
| `JUSTLS_SLIT_PREVIEW_AUTOSTART` | `1` | Set to `0` to require a manual preview start. |
| `ICS_BETA_DATA_ROOT` | (auto) | Highest-priority data root; the operator choice in the UI is lower priority. |
