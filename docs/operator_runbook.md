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
is disabled. Sequence steps are started individually by the operator. ZWO Stop
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
