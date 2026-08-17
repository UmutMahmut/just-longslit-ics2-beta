# Operator Console Requirements

## Purpose

This document defines durable requirements for the JUST Long-Slit ICS operator console.

It should capture:

- operator workflow responsibilities;
- capability visibility rules;
- hardware facts that the UI must not distort;
- separation between routine observing, diagnostics, housekeeping, and engineering controls.

It should not become a phase diary or a long implementation memo.

## Source hierarchy

Use sources in this order:

```text
1. Current repository code and tests
2. P0 hardware/science/control requirements
3. v5 fallback capability baseline
4. ICS 1.0 intent reference
5. MODS/BFOSC mature-instrument workflow references
```

If code and docs disagree, update the docs or fix the code. If a UI assumption conflicts with a durable hardware fact, the hardware fact wins unless superseded by a later explicit project decision.

## Core principle

```text
Backend capability must be visible.
Operator-safe capability may be controllable.
Engineering, unsafe, incomplete, or unverified capability must be visible but gated, deferred, diagnostic-only, or engineer-only.
```

The UI must not silently drop available backend capability. It also must not present placeholders, simulated values, or unavailable subsystems as real hardware telemetry.

## Capability classification

Each capability should be classified before it appears in a routine page.

| Class | Meaning |
|---|---|
| `VISIBLE_STATUS` | Show status, do not directly control. |
| `VISIBLE_PLACEHOLDER` | Reserve the location and label honestly as future/demo/not wired/unavailable. |
| `OPERATOR_CONTROL` | Routine operator can control it with request ID, result, and error feedback. |
| `ENGINEER_ONLY` | Low-level, unsafe, maintenance, or recovery control. |
| `DIAGNOSTICS_ONLY` | Useful for troubleshooting, not routine workflow. |
| `DEFERRED_BACKEND_CONTRACT` | Needs domain/API/hardware contract first. |
| `NOT_CARRIED_FORWARD` | Intentionally retired with reason recorded. |

## v7 information architecture

Current v7.1 structure:

```text
Setup
Instrument / Configure
Observe
Presets
Diagnostics
Housekeeping
Engineer
```

### Setup

Responsibility:

- observer/session/project context;
- data directory and file naming context;
- setup context persistence;
- readiness checklist summary;
- navigation to Configure, Presets, Observe, and Diagnostics.

Setup should not become a catch-all hardware-control page.

### Instrument / Configure

Responsibility:

- routine slit configuration;
- routine calibration configuration;
- detector profile visibility;
- B/G/R channel summary;
- safe frame-type advisory context.

Instrument / Configure may expose operator controls only when backend/API contracts and guard behavior are clear.

### Observe

Responsibility:

- single-exposure operation;
- exposure time, frame type, operator note;
- preview readiness/validation visibility;
- arm/start/finish/stop-readout/abort-discard command path;
- clear notice that the current baseline requires explicit Finish or Stop & Readout after Start;
- command feedback summary;
- latest exposure record and data-product reference summary;
- latest preview/placeholder image areas.
- multi-exposure plan entry, preview, load, progress, pause/resume, and abort controls.

Sequence controls must remain visibly operator-stepped until unattended execution and restart recovery contracts exist. An active sequence owns the detector command path; backend guards must reject competing direct exposure commands.

### Presets

Responsibility:

- preset catalog;
- preset preview;
- confirmation for high-impact presets;
- guarded apply;
- future operator-facing diff.

### Diagnostics

Responsibility:

- raw JSON;
- request ID;
- latest job;
- last error;
- runtime status;
- latest exposure record and simulated/real data-product distinction;
- read-only observatory context;
- troubleshooting payloads.

Routine pages should show summaries first. Raw JSON belongs in collapsible detail areas and Diagnostics.

### Housekeeping

Responsibility:

- read-only subsystem health;
- environmental/power/support summaries;
- operational maintenance visibility.

### Engineer

Responsibility:

- low-level hardware/maintenance/recovery controls;
- unsafe operations;
- role-gated future controls.

Engineer controls should not leak into routine observing pages.

## Current UI runtime policy

Default-on:

```text
runtime_status.js
setup_runtime.js
instrument_runtime.js
preset_runtime.js
observe_runtime.js
observe_guard.js
sequence_runtime.js
```

Reasoning:

- Observe command feedback is now part of the active operator loop.
- Status runtime gives useful current context.
- Observe guard helps prevent accidental abort/discard actions.
- Setup, Instrument, Presets, and Sequence now participate in the default operator workflow and remain individually disableable for troubleshooting.

Frontend guards are advisory. Backend API and kernel/application checks remain authoritative.

## Current command-feedback requirements

Observation command responses use a command-feedback contract rather than returning a raw observation status directly.

The Observe UI should display:

```text
last_command
request_id
latest_job
last_error
result_summary
observation_state
blocked reason and blocked components when applicable
validation issues when applicable
raw command JSON as diagnostics
```

Important split:

```text
Observation status  -> current state
Observation preview -> side-effect-free advisory readiness/validation
Observation command -> auditable command feedback
```

Preview must not automatically disable Arm. Arm always reruns the backend readiness gate.

## Hardware facts the UI must preserve

### B/G/R channels

JUST is a B/G/R three-channel spectrograph.

Current channel bands:

```text
B: 365-573 nm
G: 546-772 nm
R: 747-985 nm
```

Do not copy Blue/Red two-channel assumptions from other instruments.

Until real B/G/R hardware contracts exist:

- show B/G/R as honest summary;
- do not fake per-channel exposure readiness;
- do not fake per-channel telemetry;
- do not expose per-channel write controls as if they were real.

### Slit width

Current slit-width contract:

```text
operator unit: arcsec
backend command unit: um
conversion: 1 arcsec = 128.34 um
```

Common shortcuts:

```text
1.0 arcsec = 128.34 um
1.5 arcsec = 192.51 um
2.0 arcsec = 256.68 um
3.0 arcsec = 385.02 um
```

Do not use `0.1 arcsec` as a common routine shortcut.

### Calibration

Calibration must distinguish:

- science/calibration mode;
- lamp/source selection;
- lamp enabled/disabled state;
- optical path/mirror state when available;
- frame-type compatibility.

Current advisory expectations:

```text
science frame -> science mode + lamps off
flat frame    -> calibration mode + flat lamp
arc frame     -> calibration mode + Hg(Ar) or Ne arc lamp
test frame    -> relaxed calibration requirement for now
```

Blocking validation belongs to backend preview/gate contracts, not frontend-only assumptions.

### Slit monitor / guider

Slit monitor is a first-class subsystem concept.

Until image backend contracts exist:

- keep visible placeholders;
- label unavailable/demo/not wired honestly;
- do not remove the concept from the operator console.

### OCS/TCS and observatory context

The broader observation workflow involves weather, dome, telescope pointing, tracking, rotator, guiding, and data transfer.

ICS must not take telescope write authority unless a formal OCS/TCS contract exists.

Early TCS/observatory work should be read-only:

```text
connected
stale
tracking_state
target_name
ra_dec
alt_az
rotator_angle
focus_position
weather_ok
dome_ready
telescope_ready
last_updated
```

Unavailable or stale context must be shown honestly.

## Current backend/API visibility matrix

| Capability | Current backend/API | UI location | Control level | Notes |
|---|---|---|---|---|
| Health/status | `GET /health`, `/status`, `/status/full` | top cards, Diagnostics | visible status | Runtime status default-on. |
| Setup context | `GET/PUT/reload /setup/context` | Setup | operator control | Runtime default-on with request-ID/error summary. |
| Slit width | `POST /slit` | Instrument / Configure | operator control candidate | Preserve arcsec/um conversion. |
| Slit angle | `POST /slit_angle` | Instrument / Configure | operator control candidate | Routine control only with feedback. |
| Calibration status/mode/lamp | `/calibration/*` | Instrument / Configure | operator control candidate | Mode/lamp/frame advisory visible. |
| Detector config | `/detector/config` | Instrument / Configure | visible / guarded control | Avoid premature complex writes. |
| Presets | `/presets`, `/presets/preview`, `/presets/apply` | Presets | guarded operator control | Needs future diff polish. |
| Observation status | `/observation/status` | Observe, Diagnostics | visible status | Current-state endpoint. |
| Observation preview | `/observation/preview` | Observe | advisory | Side-effect-free. |
| Observation commands | `/observation/arm/start/finish/stop_readout/abort_discard` | Observe | operator control | Returns command feedback. |
| B/G/R channels | detector/config summary only | Instrument / Configure | visible placeholder/status | No fake telemetry. |
| TCS/observatory | `GET /observatory/context`, `/status/full` | future Setup/Observe/Diagnostics | visible placeholder/status | Read-only and unavailable by default; no telescope control. |
| Data products | `latest_exposure_record` on observation/status payloads | Diagnostics/Observe | visible status | Local FITS/PNG files exist in simulation and remain explicitly marked simulated. |
| Observation sequence | `/observation/sequence/*` | Observe, Diagnostics | operator control | In-memory, operator-stepped, auditable; no unattended auto-advance or restart recovery. |
| Engineer controls | not implemented | Engineer | deferred | Future role gating. |

## Reference usage

### P0 requirements

Use P0 as hard source for:

- B/G/R channel identity;
- wavelength coverage;
- slit width range;
- plate scale;
- calibration system facts;
- slit monitor facts;
- OCS/TCS workflow expectations;
- electrical/control-system scope.

P0 hardware/electrical terms describe possible control scope and constraints. They do not preselect the ICS 2.0 software integration protocol.

### v5 fallback

v5 remains a fallback capability baseline. v7 should not silently lose v5-visible concepts, instrument facts, or stable API hooks.

### ICS 1.0

Use the previous ICS 1.0 repository as an intent checklist, not as implementation source. Relevant lessons include:

- API-first control;
- simulator-backed operation;
- backend-served static UI;
- status/capabilities map;
- slit/lamp closed-loop demo;
- slit camera and B/G/R placeholders.

### MODS/BFOSC

Use mature instruments as workflow references only.

Do translate:

- setup/data-naming closure;
- operator-visible command feedback;
- channel state visibility;
- diagnostics separation;
- housekeeping/engineer boundaries.

Do not copy:

- Blue/Red channel assumptions;
- dense all-controls-on-one-page layouts;
- unguarded engineering controls;
- telescope write-control without OCS/TCS contract.

## Deferred requirements

The following remain deferred:

- unattended/background sequence execution;
- timer-driven automatic exposure completion/readout;
- durable observing-plan persistence and restart recovery;
- full visual plan editor and per-step automatic reconfiguration;
- durable DataProduct pipeline beyond current data-product reference contract;
- quicklook/data watcher;
- real B/G/R camera control;
- slit monitor image backend;
- real observatory/TCS integration beyond unavailable read-only placeholders;
- OCS adapter;
- auth/role model;
- engineer recovery controls.

A deferred requirement may remain visible as a placeholder only if it is clearly labeled.

## Documentation policy

Keep this document focused on durable UI requirements and hardware facts.

Do not add one-off phase notes. Do not record implementation history here. If a statement is only useful for explaining how the code reached the current state, leave it to git history or `docs/project_status.md`.
