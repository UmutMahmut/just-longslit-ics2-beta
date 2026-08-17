# Project Status

## Snapshot

```text
Project: ICS Beta
Status: Phase 3.0-B Lite plus camera-role/acquisition-workspace transition
Validation: pytest -q -> 292 passed
Current emphasis: finish transition acceptance, then begin Phase 3.1 science-FITS contract closure
```

This file is a current-state snapshot. Historical detail belongs in git history.

## Current Working Loops

Single exposure:

```text
Setup/session context -> readiness check -> backend arm gate -> arm/start
  -> finish or early stop/readout -> optional FITS + PNG quicklook
  -> ExposureRecord -> operator summary + Diagnostics
```

Multi-exposure:

```text
ObservationPlan -> side-effect-free SequencePreview -> load
  -> operator starts and completes each step through the single-exposure path
  -> per-step ExposureRecord -> pause/resume or abort -> terminal sequence state
```

The sequence executor is intentionally operator-stepped. Its versioned JSON
state survives restart, but it does not run a background timer or schedule
observatory resources. Restart during a detector-active step is never resumed
automatically; it enters `recovery_required` for explicit operator review.

Single exposures use the same explicit lifecycle: `Start` enters exposing, and
the operator chooses Finish or Stop & Readout. The requested exposure time is
recorded and passed to the detector path, but this baseline does not schedule an
automatic completion callback.

## Completed Baseline

- FastAPI `/api/v1/*` surface with request IDs and structured errors.
- Runtime state, jobs, latest-job visibility, and backend mutation guards.
- Setup/session context persistence and saved-sequence file-stem snapshots.
- Slit, calibration, detector configuration, and guarded presets.
- Side-effect-free readiness preview, authoritative arm gate, command feedback, and lifecycle.
- Local simulated FITS/PNG writer with honest simulated provenance.
- `ExposureRecord`, `DataProductRef`, quicklook, checksum, physical-camera and shared B/G/R capture metadata.
- Read-only unavailable/stale-aware observatory context without write authority.
- Default-on v7 Setup, Instrument, Presets, Observe, status, camera, sequence, and safety-guard runtimes.
- Operator summaries for request IDs, jobs, errors, exposure records, data products, and sequence progress.
- `ObservationPlan`, per-step `SequencePreview`, `SequenceExecutionSnapshot`, pause-after-active-step, resume, early readout, and abort/discard semantics.
- Backend sequence ownership: direct exposure commands are blocked while a sequence is active.
- Atomic JSON sequence persistence with schema versioning and fail-closed load errors.
- Explicit acquisition save policy, default off, with intentional `not_requested` data-product state.
- Saved Single exposure reservation at Arm and saved whole-plan reservation at Load; unsaved acquisitions do not consume file indices.
- One science-acquisition workspace with mutually exclusive Single/Sequence modes and no separate science preview task.
- Independent slit/guide Preview start/stop lifecycle, default on and never persisted.
- Height-balanced slit/guide-over-B/G/R Observe layout; all three logical science panes honestly mirror one shared science-camera source during beta development and remain structurally ready for independent cameras.
- Stable `/camera/{b|g|r}/latest.jpg` logical-channel endpoints; future physical-camera routing can change without rebuilding the operator layout.
- Restart reconciliation for completed FITS/PNG files and FITS checksums.
- Conservative Retry Current Step, Abort, and Mark Failed recovery actions.
- In-process serialization preventing concurrent sequence commands from starting the same step twice.

## Sequence Boundary

The current sequence contract supports 1-100 exposure steps. Every step:

- is previewed without side effects;
- is armed through the existing readiness gate;
- uses the existing detector lifecycle;
- creates the existing exposure/data-product record;
- carries a distinct setup file-stem only when persistence is requested;
- is visible through status and auditable jobs.

Not yet implemented:

- automatic time-based step completion or unattended auto-advance;
- timer-driven automatic completion/readout for a started exposure;
- automatic retry or automatic resume of an interrupted active exposure;
- per-step automatic instrument/preset reconfiguration;
- retry policy after hardware failure;
- OCS submission or scheduling.

## Explicitly Deferred

- ZWO SDK drivers and real dual-camera hardware integration;
- independent physical B/G/R cameras;
- real TCS readiness or telescope/dome/weather write authority;
- durable DataProduct archive/catalog database;
- authentication and operator/engineer permission enforcement;
- closed-loop guiding and real hardware protocols.

## Current Phase Status

```text
Phase 2.9-A  Setup/Data Context                           closed
Phase 2.9-B  Observation Request / Preview / Arm Gate    closed
Phase 2.9-C  Command Feedback + v7 Observe               closed
Phase 2.9-D  ExposureRecord / DataProductRef             closed
Phase 2.9-E  Read-only Observatory Context               closed
Phase 2.9-F  Operator Workflow Polish                    baseline complete
Phase 3.0-A  Observation Plan / Sequence Contract        baseline complete
Phase 3.0-B  Minimum Safe Recovery (Lite)                baseline complete
Transition   Camera Roles / Acquisition Workspace        baseline complete
```

## Recommended Next Boundary

Phase 3.1 closes the science-FITS contract before hardware integration:

- standards-readable FITS structure and pixel representation;
- atomic write/no-overwrite behavior and record/file consistency;
- stable Science/Bias/Dark/Flat/Arc metadata;
- requested versus actual exposure timing fields;
- simulator tests that become hardware-adapter conformance tests.

Real ZWO work remains paused until exact models, serials, SDK version, pixel formats, and exposure/readout calls are verified.

## Engineering Cautions

- Frontend guards are advisory; backend guards remain authoritative.
- Do not present simulated files as sky data.
- Do not imply B/G/R aliases are separate physical cameras.
- Do not add OCS/TCS write authority without an external contract.
- Do not describe the durable, operator-stepped executor as unattended automation.
- Do not introduce a database until restart/recovery requirements justify it.
- Run one ICS Beta server process against a sequence-state JSON file; Lite does not provide cross-process locking.
