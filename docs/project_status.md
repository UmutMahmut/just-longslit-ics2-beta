# Project Status

## Snapshot

```text
Project: ICS Beta
Status: simulator-backed operator workflow and observation sequence baseline
Validation: pytest -q -> 265 passed
Current emphasis: stabilize operator-stepped sequences while real camera work remains paused
```

This file is a current-state snapshot. Historical detail belongs in git history.

## Current Working Loops

Single exposure:

```text
Setup/session context -> preview -> backend arm gate -> arm/start
  -> finish or early stop/readout -> local FITS + PNG quicklook
  -> ExposureRecord -> operator summary + Diagnostics
```

Multi-exposure:

```text
ObservationPlan -> side-effect-free SequencePreview -> load
  -> operator starts and completes each step through the single-exposure path
  -> per-step ExposureRecord -> pause/resume or abort -> terminal sequence state
```

The sequence executor is intentionally in-memory and operator-stepped. It does not run a background timer, survive process restart, or schedule observatory resources.

Single exposures use the same explicit lifecycle: `Start` enters exposing, and
the operator chooses Finish or Stop & Readout. The requested exposure time is
recorded and passed to the detector path, but this baseline does not schedule an
automatic completion callback.

## Completed Baseline

- FastAPI `/api/v1/*` surface with request IDs and structured errors.
- Runtime state, jobs, latest-job visibility, and backend mutation guards.
- Setup/session context persistence and per-sequence-step file-stem snapshots.
- Slit, calibration, detector configuration, and guarded presets.
- Single-exposure preview, authoritative arm gate, command feedback, and lifecycle.
- Local simulated FITS/PNG writer with honest simulated provenance.
- `ExposureRecord`, `DataProductRef`, quicklook, checksum, physical-camera and shared B/G/R capture metadata.
- Read-only unavailable/stale-aware observatory context without write authority.
- Default-on v7 Setup, Instrument, Presets, Observe, status, camera, sequence, and safety-guard runtimes.
- Operator summaries for request IDs, jobs, errors, exposure records, data products, and sequence progress.
- `ObservationPlan`, per-step `SequencePreview`, `SequenceExecutionSnapshot`, pause-after-active-step, resume, early readout, and abort/discard semantics.
- Backend sequence ownership: direct exposure commands are blocked while a sequence is active.

## Sequence Boundary

The current sequence contract supports 1-100 exposure steps. Every step:

- is previewed without side effects;
- is armed through the existing readiness gate;
- uses the existing detector lifecycle;
- creates the existing exposure/data-product record;
- carries a distinct setup file-stem preview;
- is visible through status and auditable jobs.

Not yet implemented:

- automatic time-based step completion or unattended auto-advance;
- timer-driven automatic completion/readout for a started exposure;
- durable plan/execution persistence and restart recovery;
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
```

## Recommended Next Boundary

Before adding unattended execution, define and test durable recovery semantics:

- what survives process restart;
- how a partially completed plan is reconciled with files on disk;
- retry versus fail-fast rules;
- operator acknowledgement after failure;
- when setup frame indices are committed.

Real ZWO work remains paused until exact models, serials, SDK version, pixel formats, and exposure/readout calls are verified.

## Engineering Cautions

- Frontend guards are advisory; backend guards remain authoritative.
- Do not present simulated files as sky data.
- Do not imply B/G/R aliases are separate physical cameras.
- Do not add OCS/TCS write authority without an external contract.
- Do not describe the in-memory, operator-stepped executor as unattended automation.
- Do not introduce a database until restart/recovery requirements justify it.
