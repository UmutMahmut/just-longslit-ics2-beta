# ICS Beta

Campus-integration branch of the long-slit Instrument Control System.

ICS Beta inherits the ICS 2.0 backbone and keeps its existing operator-console
layout. Its purpose is to run the smallest useful campus observing loop with one
science camera, one optional slit/guide camera, and a manually operated compact
spectrograph.

## Current baseline

Current code baseline: simulator-backed operator workflows, closed science-FITS
contract, schema-v2 device/role topology, durable operator-stepped sequence
state, conservative restart recovery, and a standalone hardware-verified ZWO
RAW16 detector path awaiting managed Runtime/API ownership.

Validation baseline:

```text
pytest -q --basetemp .pytest-tmp
322 passed
```

Current default UI behavior:

```text
/ui        -> v7.1 operator-console prototype
/ui/v7     -> v7.1 explicit operator-console prototype
/ui/v5     -> v5 fallback shell
/ui/legacy -> v5 fallback alias
/ui/v6     -> v6 review shell
```

`/ui` and `/ui/v7` load the complete operator-safe v7 runtime by default. Observe keeps the instrument-facing layout: a slit/guide preview above three B/G/R science panes, with Single/Sequence controls on the right. During beta development the B/G/R panes deliberately mirror the same completed shared science-camera readout; the three-pane structure and logical-channel endpoints are retained for the future independent cameras. The science acquisition path has no separate preview lifecycle.

## What works now

The current repository supports simulator-backed single-exposure and operator-stepped multi-exposure loops with auditable command feedback:

```text
Setup / Instrument context
  -> Observation preview
  -> backend readiness gate
  -> arm
  -> start physical-camera exposure
  -> finish or early stop/readout
  -> optional FITS + PNG quicklook when save_requested=true
  -> ExposureRecord / available or not_requested DataProductRef
  -> read-only observatory context visibility
  -> v7 Observe command summary
  -> raw JSON diagnostics when needed
```

Multi-exposure plans reuse that same loop for every step:

```text
ObservationPlan -> side-effect-free SequencePreview -> load
  -> start current step -> finish or early stop/readout
  -> ExposureRecord -> next step
  -> optional pause/resume or abort
```

Exposure completion is explicitly operator-driven in this baseline. `Start`
enters the exposing state but does not schedule `Finish` when `exp_time_s`
elapses; the operator uses Finish or Stop & Readout. Timer ownership, automatic
readout, and timeout handling remain deferred; restart recovery is conservative
and never assumes that an interrupted exposure completed.

Implemented capabilities include:

- FastAPI backend under `/api/v1/*`.
- Request ID middleware and structured API error responses.
- Runtime, subsystem state, exposure state, job tracking, and latest-job visibility.
- Setup/session context domain model, service, JSON store, and API.
- Setup context snapshot handoff into observation metadata.
- Slit width and slit-angle API surfaces.
- Calibration mode/lamp API surfaces and simulator state.
- Detector configuration visibility and guarded mutation.
- Preset catalog, preview, guarded apply, risk/confirmation metadata, and observation metadata linkage.
- Observation single-exposure lifecycle: arm, start, finish, stop/readout, abort/discard.
- `ObservationPlan`, `SequencePreview`, versioned JSON sequence state, atomic saves, saved-plan frame-index reservation, and auditable load/start/finish-step/pause/resume/abort commands.
- Conservative restart reconciliation with `recovery_required`, local FITS/PNG existence and FITS checksum checks, Retry Current Step, Abort, and Mark Failed.
- Backend ownership guard preventing direct single-exposure commands from competing with an active sequence.
- Side-effect-free observation preview contract.
- Backend arm gate based on current readiness preview.
- Observation command feedback contract for success, blocked, and failed command results.
- Stateful science-camera lifecycle: start, finish/readout, early stop/readout,
  and abort.
- Explicit per-acquisition `save_requested` policy, default off; unsaved readouts remain available as the latest in-memory science image and do not consume file indices.
- One physical science camera bridged to the existing logical B/G/R channels.
- Three persistent B/G/R science display panes and stable logical-channel image endpoints; the beta bridge marks their currently shared science-camera source instead of hiding the final instrument topology.
- Independent simulated slit/guide-camera live preview with explicit start/stop state; it never writes data products and remains available during science acquisition.
- Actual local FITS files and PNG quicklooks in simulation mode when persistence is requested.
- Standards-readable unsigned-16 FITS with atomic no-overwrite publication,
  stable frame types, requested/actual timing, detector/CFA/cooling metadata,
  checksums, sizes, and independent Astropy validation.
- ExposureRecord provenance for the physical camera, logical channels, shared
  capture ID, checksum, and file URI.
- Camera schema v2 profiles under `config/`, with physical devices separated
  from deployment role bindings, legacy v1 migration, generic logical channel
  names, and an optional slit camera.
- Standalone ZWO SDK discovery/control/cooling and full-frame RAW16 acquisition
  through the normal ICS adapter and FITS/quicklook writer; the 2026-08-22
  ASI294MC Pro hardware smoke test passed without ASIImg/ASICap at runtime.
- Read-only `/api/v1/observatory/context` for OCS/TCS/telescope/dome/weather/guider visibility with unavailable/stale-ready semantics reserved.
- `/api/v1/status/full` includes observatory context and latest exposure-record visibility.
- Simulator adapter contract tests for detector, slit, and calibration behavior.
- v7 operator workflow runtime enabled across Setup, Instrument, Presets, Observe, sequence progress, exposure-record summaries, and Diagnostics.
- v7 route/runtime tests and API contract tests.

## What is not implemented yet

The repository intentionally does not yet implement:

- unattended/background sequence scheduling, timed auto-advance, automatic retry, or automatic mid-exposure resume;
- timer-driven automatic completion/readout for a started exposure;
- durable DataProduct database or archive pipeline;
- OCS adapter;
- TCS telescope control;
- real TCS readiness integration;
- telescope pointing, rotator, guider, dome, weather, or safety authority;
- managed Runtime/FastAPI lifecycle and API exposure for the proven standalone
  ZWO detector driver;
- independent physical B/G/R cameras (the beta bridge intentionally shares one);
- closed-loop guiding;
- role-based authentication and operator/engineer permission separation;
- real hardware communication protocols.

These are future phases. They should enter through contracts and adapters, not direct UI shortcuts.

## Quick start

Install for local development:

```powershell
python -m pip install -U pip
pip install -e ".[dev]"
```

Run tests:

```powershell
pytest -q
```

Run backend:

```powershell
python -m uvicorn justls.ics.app.main:app --app-dir src --reload
```

Open:

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/ui
http://127.0.0.1:8000/ui/v7
```

Use backend-served UI routes rather than opening HTML files directly. This keeps API calls, runtime scripts, and static assets on the same origin.

## Camera profiles and data

The default profile is:

```text
config/cameras.sim.json
```

It is a schema-v2 simulated B/G/R compatibility profile. Override it with:

```powershell
$env:ICS_BETA_CAMERA_CONFIG="C:\path\to\camera-profile.json"
$env:ICS_BETA_DATA_ROOT="D:\observations\ics-beta"
```

`config/cameras.zwo.example.json` is a generic vendor template.
`config/cameras.lhires-asi294.example.json` is the non-default campus
50 cm/Lhires/ASI294 deployment example with one logical `SCI` channel. Selecting
`driver: "zwo"` in the main Runtime still fails clearly because managed
startup/shutdown and API integration are the active next boundary; it does not
mean the low-level driver is absent.

Configure the machine-local SDK path, then use the read-only discovery and
explicit hardware smoke commands:

```powershell
$env:ICS_ZWO_SDK_LIBRARY = "C:\path\to\ASICamera2.dll"
python -m justls.ics.drivers.zwo.probe
python -m justls.ics.drivers.zwo.probe --controls
python -m justls.ics.drivers.zwo.capture --data-root "var\hardware-smoke" --exposure-s 0.01 --gain 0 --offset 30 --frame-type test
```

The first command is read-only. `--controls` opens/initializes the camera and
reads values. The capture command writes a real FITS and quicklook. ASIStudio,
ASIImg, and ASICap are reference tools only; the runtime dependency is the ZWO
driver/SDK library.

Simulation products are real local files, but their FITS metadata and
ExposureRecord remain marked `SIMULATE=true` / `simulated=true`. The default
output directory is ignored by Git:

```text
var/data/YYYYMMDD/<obs-id>/*.fits
var/data/YYYYMMDD/<obs-id>/*-quicklook.png
```

Operator setup and sequence recovery state use local, ignored JSON files:

```text
.justls/setup_context.json
.justls/sequence_execution.json
```

Override them with `JUSTLS_SETUP_CONTEXT_PATH` and
`JUSTLS_SEQUENCE_STATE_PATH`. The sequence file is an operational recovery
artifact, not a portable plan template; do not edit it while ICS Beta is
running. This Lite store assumes one ICS Beta server process; do not point
multiple Uvicorn workers or independent processes at the same sequence file.

## Runtime defaults

Default v7 behavior:

```text
JUSTLS_UI_V7_RUNTIME_ENABLED         default: on
JUSTLS_UI_V7_RUNTIME_STATUS_ENABLED  default: on
JUSTLS_UI_V7_SETUP_RUNTIME_ENABLED   default: on
JUSTLS_UI_V7_INSTRUMENT_RUNTIME_ENABLED default: on
JUSTLS_UI_V7_PRESET_RUNTIME_ENABLED default: on
JUSTLS_UI_V7_OBSERVE_RUNTIME_ENABLED default: on
JUSTLS_UI_V7_OBSERVE_GUARD_ENABLED   default: on
```

To force the v7 static shell:

```powershell
$env:JUSTLS_UI_V7_RUNTIME_ENABLED="0"
```

Individual modules can still be disabled for troubleshooting:

```powershell
$env:JUSTLS_UI_V7_INSTRUMENT_RUNTIME_ENABLED="0"
$env:JUSTLS_UI_V7_PRESET_RUNTIME_ENABLED="0"
$env:JUSTLS_UI_V7_SETUP_RUNTIME_ENABLED="0"
```

## API overview

Representative current endpoints:

```text
GET  /api/v1/health
GET  /api/v1/status
GET  /api/v1/status/full
GET  /api/v1/capabilities
GET  /api/v1/observatory/context
GET  /api/v1/cameras/status
POST /api/v1/cameras/slit/preview/start
POST /api/v1/cameras/slit/preview/stop
GET  /camera/slit/latest.jpg
GET  /camera/{b|g|r}/latest.jpg  -> stable logical channels; same shared science-camera readout during beta

GET  /api/v1/setup/context
PUT  /api/v1/setup/context
POST /api/v1/setup/context/reload

POST /api/v1/slit
POST /api/v1/slit_angle

GET  /api/v1/calibration/status
POST /api/v1/calibration/mode
POST /api/v1/calibration/lamp

GET  /api/v1/detector/config
POST /api/v1/detector/config

GET  /api/v1/observation/status
POST /api/v1/observation/preview
POST /api/v1/observation/arm
POST /api/v1/observation/start
POST /api/v1/observation/finish
POST /api/v1/observation/stop_readout
POST /api/v1/observation/abort_discard

POST /api/v1/observation/sequence/preview
GET  /api/v1/observation/sequence/status
POST /api/v1/observation/sequence/load
POST /api/v1/observation/sequence/start
POST /api/v1/observation/sequence/finish_step
POST /api/v1/observation/sequence/stop_readout_step
POST /api/v1/observation/sequence/pause
POST /api/v1/observation/sequence/resume
POST /api/v1/observation/sequence/abort
POST /api/v1/observation/sequence/retry_current_step
POST /api/v1/observation/sequence/mark_failed

GET  /api/v1/presets
POST /api/v1/presets/preview
POST /api/v1/presets/apply
```

Important contract split:

```text
GET  /observation/status  -> current observation state
POST /observation/preview -> side-effect-free readiness/validation preview
POST observation commands -> ObservationCommandFeedbackResponse
latest_exposure_record -> exposure lifecycle + data-product reference contract
```

Preview is advisory. Arm is an independent command. Every Arm call reruns the backend readiness gate.

Sequence preview is also advisory and side-effect-free. Loading rechecks every
step and saves sequence state under
`.justls/sequence_execution.json` by default. Each sequence start reruns the
single-exposure backend arm gate. The executor remains operator-stepped and has
no background timer. A restart during an active step enters `recovery_required`;
retry is blocked whenever a possible FITS already exists.

`save_requested` defaults to false for both Single and Sequence. A saved Single
reserves one file index at Arm; a saved Sequence reserves its full range at
Load. Unsaved acquisitions do not consume file indices. The save choice is
frozen while an exposure or non-terminal sequence owns the science detector.

## Documentation map

Current durable docs:

```text
docs/project_status.md
docs/ics2_software_development_strategy.md
docs/operator_console_requirements.md
```

Use them as follows:

- `README.md`: current repository entry point.
- `docs/project_status.md`: current status snapshot and next-step boundary.
- `docs/ics2_software_development_strategy.md`: software strategy, architecture, roadmap, and documentation policy.
- `docs/operator_console_requirements.md`: operator-console requirements, hardware facts, capability visibility, and UI responsibility boundaries.

Avoid adding one-off phase notes. If a decision remains useful, fold it into one of the durable documents.

## Test layout

```text
tests/api/          API behavior and response contracts
tests/application/  application services and use-case contracts
tests/adapters/     simulator adapter parity contracts
tests/drivers/      vendor SDK/driver contract tests
tests/infra/        configuration and FITS publication contracts
tests/domain/       domain models and validation
tests/kernel/       runtime, job, state, and guard behavior
tests/ui/           UI routes, static shells, static assets, runtime gates
```

Prefer boundary-specific tests. Do not add new root-level temporary test files for phase work.

## Development guardrails

Every meaningful change should preserve:

- contract-first development;
- simulation parity with future real hardware;
- backend safety authority over frontend assumptions;
- request ID / latest job / error visibility;
- clear Domain / Kernel / Application / API / UI / Adapter boundaries;
- honest labeling of simulated, unavailable, placeholder, and real capabilities;
- no telescope/OCS/TCS authority overreach.

## License

If no `LICENSE` file is present, treat this repository as internal until a license is chosen.
