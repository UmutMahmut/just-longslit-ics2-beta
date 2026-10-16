# ICS Beta operator runbook

Install the development environment as described in README. From the repository
root, run the real dual-camera profile with an explicit SDK path:

```powershell
.\start_ics.ps1 -SdkLibrary "C:\vendor\ASICamera2.dll" -NoBrowser
```

Use `-Python` if the interpreter is not in .venv or PATH. `-Config` selects a
profile and `-Port` selects the port (default 8123). The launcher refuses an
occupied port; stop its owner gracefully or select another port. Ctrl-C stops
the server and releases the cameras. Use one server process, without --reload
or multiple workers, for real hardware.

Open `http://127.0.0.1:8123/ui/v7`. ASIStudio capture applications should be closed
before ICS opens the cameras. The ASI294/ASI678 example is local deployment
configuration, not a requirement for future ICS cameras.

## Explicit simulation

```powershell
.\start_ics.ps1 -ForceSim -NoBrowser
```

Simulation is explicit. A missing configured real science camera instead blocks
Arm and reports science_camera_error in `/api/v1/cameras/status`. A missing
guide camera degrades the preview without pretending that a real frame exists.

## Acquisition and recovery

Each exposure completes/readouts automatically unless JUSTLS_AUTO_READOUT_ENABLED
is disabled. New UI plans default to Auto advance: click Start Step once to run
the remaining rows. Uncheck before loading for individual starts. This choice
is frozen in the loaded plan. Pause waits for the current frame; Resume
continues automatically in auto mode. Existing saved plans and API requests
without auto_advance retain manual stepping. A restart never starts a plan
automatically. Use manual stepping when changing physical lamps/illumination
between rows. ZWO Stop
& Readout is unsupported and preserves the integration; wait or Abort/discard.
Premature Finish is rejected without cancelling automatic completion.

The hotplug badge reports Windows PnP presence, not SDK health. It never rebinds
automatically. Reload Cameras is allowed only when no exposure or non-terminal
sequence owns the detector. Finish/Abort the exposure, and complete/abort the
sequence or acknowledge recovery, before reload.

A native SDK timeout or access violation quarantines that DLL for the remaining
process lifetime. Stop the service gracefully, verify USB/power and competing
camera applications, and restart. If device state remains stale, reconnect USB
with the service stopped. Reload cannot clear a quarantined native session.
Never assume a timed-out call has been cancelled.

Interrupted sequences require explicit recovery; do not edit their JSON while
the server is running. Review any possibly published FITS before retrying.
Acquisition failures expose failed jobs and recovery_required rather than
silently repeating a capture. SDK/storage details and request/job IDs are in
the API feedback and Diagnostics.

For repeatable bench acceptance (writes engineering frames):

```powershell
.\.venv\Scripts\python.exe tools/hardware_acceptance.py --hardware --dll "C:\vendor\ASICamera2.dll"
```

Inspect the resulting report.json and FITS beneath var/hardware-acceptance.
This does not certify on-sky observing or physical cable-loss behavior.

## Browser retest of the manual-feedback repairs

Restart with the same launcher command, then Ctrl-F5 the browser. The current
local repair branch is runnable in place; no branch switch is needed to test it.

1. Single: select Bias, enter 0 s, Arm and Start. It should automatically save
   when saving is selected. FITS records EXPREQ=0 and EXPTIME=camera minimum
   (32 us on this ASI294).
2. Prepare physical Flat illumination, select Flat and acquire; prepare the
   physical comparison lamp/optical path and acquire Arc separately. No
   simulated lamp command is required in the manual Lhires profile. Block
   light physically for Bias/Dark; this camera has no mechanical shutter.
3. Leave Auto advance checked, load the usual test 1/2/3-second sequence,
   and click Start Step once. All three rows should complete, with the guide
   image continuing to update. Repeat with Auto advance unchecked: each row
   should wait for Start Step. In auto mode, Pause during a longer exposure
   should finish that frame and wait; Resume should continue the remaining rows.
   Abort should stop without starting another row.
4. Expand/collapse Camera acquisition settings and Raw Command JSON. The left
   guide/science preview panel should keep its height and spacing. Change gain/offset, Apply,
   and acquire a frame. Read Settings shows effective values. Binning changes
   resize the current ROI unless width/height are explicitly edited. Values are
   SDK-bounded and reset on restart; RAW16 and ROI origin are not editable here.
5. While an exposure or loaded/non-terminal sequence owns the detector, applying
   camera settings should be rejected without changing them.

Persistent diagnostic log: `var/logs/ics-beta.log` (UTC timestamps, rotating
5 MB files). For a new failure, preserve the log and report the operation and
approximate time before restarting/reloading cameras:

```powershell
Get-Content .\var\logs\ics-beta.log -Tail 120
```
