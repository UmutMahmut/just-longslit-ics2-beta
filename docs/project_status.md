# Project Status

## Snapshot

```text
Project: ICS Beta
Status: campus camera vertical slice implemented in simulation
Validation: pytest -q -> 249 passed
Current emphasis: preserve the ICS 2.0 UI and contracts while preparing ZWO driver replacement
```

This file is a current-state snapshot. It is not a project diary. Historical details should be recovered from git history, not accumulated here.

## Current baseline

ICS Beta inherits the simulator-backed, API-driven ICS 2.0 baseline and adapts
it to the campus telescope branch.

The current working loop is:

```text
Setup/session context
  -> ObservationRequest / preview
  -> backend readiness gate
  -> start science-camera exposure
  -> finish or early stop/readout
  -> ObservationCommandFeedbackResponse
  -> local FITS + PNG quicklook
  -> ExposureRecord / available DataProductRef
  -> read-only ObservatoryContext
  -> v7 Observe summary + raw diagnostics
```

The current default UI route is:

```text
/ui    -> v7.1 operator-console prototype
/ui/v7 -> explicit v7.1 route
```

The v5 fallback remains available:

```text
/ui/v5
/ui/legacy
```

## Completed Baseline

Established:

- FastAPI application and `/api/v1/*` control/status surface.
- Request ID middleware and structured error responses.
- Runtime/subsystem state aggregation.
- Exposure state model.
- Job tracking and latest-job read model.
- Simulation-first assembly path.
- Setup/session context model, service, JSON store, and API.
- Slit width and slit-angle API surfaces with arcsec/um unit boundary.
- Calibration status/mode/lamp API surfaces and simulator state.
- Detector configuration visibility and guarded mutation.
- Preset catalog, preview, guarded apply, risk/confirmation metadata, and observation metadata linkage.
- Observation request, side-effect-free preview, readiness snapshot, validation issues, and backend arm gate.
- Observation command feedback for success, blocked, and failed command results.
- v7 status runtime, Observe runtime, and Observe guard default-on.

## Exposure Records

The beta branch now provides:

- `ExposureRecord`, `FrameRecord`, `DataProductRef`, `FitsHeaderSummary`, and `QualityFlag`.
- Latest exposure record attached to detector snapshots and observation metadata.
- Completed simulator exposures produce actual local FITS and PNG quicklook files.
- Discarded exposures explicitly report `not_created` data-product state.
- Products retain `simulated=true` provenance and `SIMULATE=true` FITS metadata.
- Physical camera ID, B/G/R logical-channel aliases, and a shared capture ID are recorded.

Important boundary:

```text
Exposure completion only succeeds after the local FITS and quicklook writer returns.
The files exist, but simulated pixels must never be presented as sky data.
Archive/catalog persistence remains a future concern.
```

## Observatory Context

Established in Phase 2.9-E:

- `ObservatoryContext` and `ObservatoryComponentContext`.
- `GET /api/v1/observatory/context`.
- `/api/v1/status/full` includes observatory context.
- OCS, TCS, telescope, dome, weather, and guider are visible as unavailable by default.
- The context is explicitly read-only and exposes no telescope/dome/weather write route.

Important boundary:

```text
ICS can expose observatory context.
ICS still has no telescope, dome, weather, or OCS write authority.
```

## Current Test Baseline

Current reported validation:

```text
pytest -q
249 passed
```

This means code and tests are aligned with the current runtime/default route behavior.

## Explicitly Not Implemented

The following are intentionally not part of the current baseline:

- multi-exposure sequence runner;
- observation plan executor;
- durable DataProduct archive/catalog persistence;
- durable ExposureRecord persistence beyond current runtime state;
- OCS adapter;
- TCS telescope control;
- real TCS readiness integration;
- telescope pointing, rotator, guiding, dome, or weather authority;
- real hardware communication protocols;
- ZWO SDK science-camera and slit-camera drivers;
- independent physical B/G/R camera control;
- closed-loop guiding;
- role-based authentication or operator/engineer permission enforcement.

## Current Phase Status

```text
Phase 2.9-A  Setup/Data Context                         closed
Phase 2.9-B  Observation Request / Preview / Arm Gate    closed
Phase 2.9-C  Observation Command Feedback + v7 Observe   closed
Phase 2.9-D  ExposureRecord / DataProductRef Contract    closed
Phase 2.9-E  Read-only Observatory Context               closed
```

## Recommended Next Feature Phase

The next phase should begin only after the exact ZWO models, serial numbers, SDK
version, supported pixel formats, and exposure/readout calls are known:

- implement SDK drivers behind the existing adapters;
- add timeout, disconnect, abort, and reconnect contracts;
- perform desk tests with each camera separately;
- then perform telescope/spectrograph hardware-in-loop tests.

The manually selected grating, fixed nominal 25 µm slit, and second Nasmyth
visual optical path remain observing metadata/operational facts, not software
control responsibilities in this beta phase.

## Engineering Cautions

- Do not let frontend preview state become safety authority.
- Do not present placeholder telemetry as real.
- Do not add telescope write-control inside ICS without an OCS/TCS contract.
- Do not introduce a database just because persistence will eventually matter.
- Do not imply that B/G/R aliases are three physical cameras.
- Do not imply that simulated FITS files contain sky data.
- Do not keep appending history to this document. Rewrite the snapshot when the phase changes.

## Documentation State

This document should be rewritten at phase boundaries.

Other durable documents:

```text
README.md
docs/ics2_software_development_strategy.md
docs/operator_console_requirements.md
```

Rules:

- README states current facts.
- Project status states current snapshot.
- Software strategy changes only when strategy changes.
- Operator-console requirements change only when UI responsibility boundaries or hardware facts change.
