# Project Status

## Current scope and priority

ICS Beta is the attended observing/development test platform for a small
spectrograph on the 50 cm telescope. It is distinct from the eventual JUST ICS.
Slit width/angle and lamps are manually operated on the beta instrument;
simulator adapters may remain. These two cameras are replaceable deployment
resources. Broader manual/simulated-state UX, capability abstraction, spectral
viewing, installation packaging, sustained endurance and on-sky acceptance are
explicitly deferred by the operator for this integration milestone.

## Source provenance

- Prior local/remote main: `24e52c0` (322 passing tests).
- Remote snapshot: `stable/2026-10-15`, root commit
  `ea84385412e667be02efecd079e5b12c049a0c79` (399 passing tests).
- The snapshot has no common Git ancestor with main. Tree comparison against
  main: 67 files, 5,259 insertions and 90 deletions; it already contains the
  old main source baseline plus the new hardware/workflow changes.
- Repairs are developed and verified on `codex/stable-repair` before integration.
  Integration preserves main's history and transplants the verified resulting
  tree, citing the snapshot rather than forcing an unrelated-history merge.
- Verified integration source commit: `f3f30bc`, descended from the former main.
  The integration tree was checked equal to repaired snapshot `91db132`.
  Source history is retained under archive tags `archive/stable-2026-10-15`
  and `archive/stable-repair-2026-10-16` when retiring the old branches.

## Verified repairs

- Readout tasks moved from request-local services into Runtime. Single and
  sequence commands share one scheduler, a transition lock and invalidation
  generations. Late callbacks cannot complete a replacement exposure or step.
- Shutdown cancels tasks before hardware release; released runtimes reject
  stale commands. Singleton construction/replacement is serialized.
- Reload rejects armed/exposing/readout ownership, loaded/running/paused or
  recovery sequences, and unreadable durable sequence state. A failed rebuild
  leaves no released singleton to be accidentally reused.
- Native SDK calls share a serialized bounded gate per real DLL. On timeout or
  native access violation, that gate is quarantined; even cleanup/rebind cannot
  overlap the unresolved call. Restart the service to recover. This is bounded
  waiting and quarantine, not cancellation of a blocked native call.
- Serial discovery is cached for binding both roles before acquisition. The
  Windows hotplug monitor reads PnP presence rather than repeatedly enumerating
  the live camera SDK. OS presence is advisory and does not prove SDK health.
- Missing real science hardware blocks capture instead of silently falling back
  to simulation. Explicit ForceSim remains available for software development.
- SDK/storage errors are audited as failed jobs; detector state becomes failed.
  Sequence acquisition failures require durable operator recovery and forbid
  automatic retry, avoiding duplicate data after uncertain readout/publication.
- Premature real Finish is rejected while preserving the pending timer. ZWO
  retained early readout is explicitly unsupported; its rejection preserves the
  exposure. Abort/discard remains supported. Simulator early readout is retained.
- Launcher refuses occupied ports, does not force-kill processes, avoids the
  read-only PowerShell PID variable, and removes fixed interpreter/SDK paths.
- Automatic SDK path lookup imports sys correctly; initial hotplug errors are
  retained and monitor stop no longer falsely discards a live thread handle.

## Validation on 2026-10-16

Automated suite: **423 passed** in the local Python 3.13 environment. Regressions
cover cross-request cancellation, stale callbacks, sequence equivalents,
concurrent Finish, active reload rejection, stale runtime/reload requests,
failed rebuild, native timeout/quarantine, no live SDK re-enumeration, missing
real camera, native/storage errors, durable recovery and occupied-port startup.

Hardware identity (Windows and direct ZWO SDK):

| Role | Camera | Serial |
| --- | --- | --- |
| science | ASI294MC Pro | 28344F041D010900 |
| slit/guide | ASI678MC | 2813CF0520010900 |

The earlier zero-camera result was obtained in restricted execution and did
not establish a hardware fault. Normal host execution discovered and opened
both cameras. During the first integration test a guide frame failed and later
SDK discovery became unstable, despite Windows reporting both devices present.
After the operator reconnected USB and the live-SDK enumeration paths were
removed, the full acceptance passed. This is evidence of recovery and corrected
session handling; it does not prove a unique root cause of the original failure.

Successful FastAPI bench report:
`var/hardware-acceptance/20261016T032327Z/report.json` (local ignored artifact).
It validates:

- both serial-bound real cameras, with no vendor capture application;
- repeated 0.1/0.2 s and 10 s science exposures with concurrent guide preview;
- 8 saved full-frame 4144 x 2822 uint16 RAW16/RGGB engineering FITS files;
- independent Astropy parsing, timestamps, non-simulated provenance, serials
  and SHA-256 consistency;
- Abort A, then B surviving A's obsolete deadline;
- active-exposure and loaded-sequence reload rejection;
- unsupported early-readout rejection followed by automatic normal completion;
- safe close/rebind, two operator-started sequence steps with automatic readout;
- shutdown during exposure, task cancellation, and a new lifecycle capturing
  another frame successfully.

`tools/hardware_acceptance.py` makes this deployment-specific acceptance
repeatable with explicit `--hardware` and SDK-path arguments. It uses isolated
state/data paths, does not change cooling and is not part of unattended pytest.

A second complete acceptance also passed with a 30 s science integration and
continuous guide preview, plus the same abort/sequence/reload/restart checks:
`var/hardware-acceptance/20261016T032605Z/report.json`. Both successful runs
saved and independently validated 8 engineering FITS files each.

After transplantation onto main ancestry, the identical integrated source
passed all 423 tests again. A real Uvicorn HTTP server smoke also passed:
UI/script routes, health, both camera connections, live guide image, a saved
real science exposure, science image retrieval, controlled reload and graceful
shutdown. Local report: `var/http-smoke/20261016T033020Z/report.json`.
All 11 served JavaScript source files passed Node syntax checks.

## What this milestone does not certify

These are engineering connectivity frames, not sky spectra or calibrated data.
Physical USB-loss/power-loss injection, hours-long endurance, cooling control
acceptance and on-sky observing have not been certified here. Fault injection
regressions supplement the bench tests; they do not replace physical tests.
No test suite establishes absence of all bugs.

The preserved base includes generic schema-v2 topology, optional guide camera,
request/job feedback, readiness/Arm gates, setup persistence, explicit save
policy, atomic FITS publication, ExposureRecord/DataProductRef provenance and
durable conservative sequence recovery. The snapshot additionally supplies
managed hardware, preview, save-last-frame, output-location and instrument
metadata work. B/G/R views remain compatibility aliases for the beta SCI source.

No telescope/OCS/TCS write authority, closed-loop guiding, real slit/lamp drivers
or unattended scheduling is introduced. New cameras should continue to enter
through adapters and deployment roles.
