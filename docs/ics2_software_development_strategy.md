# ICS Beta Software Development Strategy

```text
Scope: campus-integration strategy for this ICS Beta repository
Status: Phase 3.1 closed; Phase 3.2 managed hardware-runtime integration active
```

## Mission

ICS Beta is the active campus-integration line for the JUST long-slit
instrument. It inherits the useful ICS 2.0 backbone, but this roadmap governs
the Beta repository and does not reopen development of the frozen historical
project.

It is not only a GUI, and it is not a single hardware driver. Its purpose is to provide stable software contracts for routine instrument operation, diagnostics, simulation-first development, future real-hardware adapters, and eventual observatory/OCS integration.

The long-term observing loop is:

```text
Operator / Future Script / Later OCS
  -> ObservationRequest / ObservationPlan
  -> ICS validation and readiness
  -> command execution
  -> command feedback
  -> ExposureRecord / DataProduct / Quicklook
  -> audit log and recovery path
```

Current phases should build toward this loop through small, testable contracts.

## Strategic principles

### Simulation first

Every contract should work in simulation before real hardware is required. Simulation is not a toy path; it is the first implementation of the same contract real hardware should later satisfy.

### API first

Operator UI, future scripts, future OCS adapters, and tests should all depend on stable API/domain contracts rather than private frontend behavior.

### Contract first

A feature should first stabilize its domain/API meaning before adding large UI surfaces or hardware-specific implementation.

### Operator-safe UI

Routine pages should show safe, meaningful controls and summaries. Low-level hardware, recovery, and unsafe controls belong in Engineer, Housekeeping, or Diagnostics areas and later require role gating.

### Auditable command lifecycle

High-impact commands must remain traceable through:

```text
request_id
command name
latest_job
status
result summary
error code/message/details
raw diagnostics payload
```

### Adapter-bounded hardware integration

Real hardware must enter through explicit adapter/gateway boundaries. Routine UI must not talk directly to vendor SDKs, buses, PLCs, motion controllers, or telescope-control channels.

## ICS boundary

### ICS owns

ICS should own:

- instrument-control API contracts;
- setup/session context;
- slit, calibration, detector, preset, observation, command-feedback semantics;
- runtime state and exposure state;
- command dispatch, job audit, and error reporting;
- simulator-backed operation;
- operator-console information architecture;
- hardware adapter boundaries;
- future data-product metadata contracts.

### ICS does not own

ICS should not own:

- OCS scheduling;
- telescope pointing/slew/focus/rotator authority;
- dome/weather authority;
- full science reduction;
- complete observatory automation;
- low-level hardware bus control in routine UI;
- fake hardware telemetry;
- optical performance itself.

Optical requirements such as resolution, dispersion, throughput, and wavelength range are instrument constraints. Software can expose, validate, record, and coordinate relevant state, but it cannot create optical performance.

## Layered architecture

Recommended responsibility split:

```text
Domain
  Stable concepts: ObservationRequest, Preview, CommandFeedback,
  ExposureRecord, DataProductRef, ObservatoryContext,
  SetupContext, DetectorConfig, Calibration, Slit.

Kernel
  Runtime, states, guards, jobs, command request/job lifecycle.

Application
  Services and use cases. Orchestrates domain/kernel behavior.

API
  FastAPI schemas and routes. Converts request/response contracts.

UI
  Backend-served operator console. Shows summaries first, raw diagnostics second.

Adapter
  Simulator and future real-hardware boundary.

Driver
  Hardware-specific implementation below the adapter boundary.
```

No layer should compensate for a missing contract by leaking implementation detail upward.

## Deployment topology and role binding

ICS 2.0 is intended to be a general long-slit control platform. A physical
device definition must therefore be separate from the operational role assigned
to that device at a particular site.

The generic model should distinguish:

```text
physical device
  stable identity, manufacturer/model/serial, driver, connection, capabilities

deployment binding
  science detector, slit viewer, guide sensor, calibration unit, focal station

instrument profile
  logical science channels, slit model, calibration sources, optical metadata

telescope/site profile
  focal stations, plate scale, readiness context, external control boundaries
```

A device may support several capabilities, but incompatible roles must not be
owned concurrently without an explicit arbitration contract. The science
detector lifecycle, continuous preview lifecycle, guide-measurement pipeline,
and telescope guide-command authority remain separate concepts even when one
camera can technically participate in more than one of them.

Camera schema v2 now implements a physical device registry plus deployment role
bindings. It supports generic logical channel names, a required science role,
an optional slit role, a single-channel `SCI` profile, and in-memory migration
of the legacy schema. The default Beta profile still binds one shared simulated
camera to B/G/R so existing behavior is unchanged. Device definitions contain
no operational `role`; the Lhires/ASI294 profile is a separate non-default
deployment artifact.

## Current contract baseline

The current baseline after Phase 2.9-E includes:

```text
SetupContext
ObservationRequest
ExposureSpec
ObservationPreviewResult
ReadinessSnapshot
ValidationIssue
ObservationCommandFeedback
ObservationCommandFeedbackResponse
ExposureRecord
FrameRecord
DataProductRef
FitsHeaderSummary
QualityFlag
ObservatoryContext
```

Important split:

```text
/status  -> current state
/preview -> side-effect-free advisory readiness/validation
command  -> auditable command feedback
record   -> exposure lifecycle and data-product reference status
context  -> read-only observatory/OCS/TCS visibility
```

Preview and Arm are intentionally independent. UI preview is advisory. Backend Arm gate is authoritative.

Exposure completion, save intent, and data-product existence are intentionally separate. Unsaved acquisitions are `not_requested`; saved simulator acquisitions produce local FITS/PNG with simulated provenance.

Observatory context is intentionally read-only. ICS must not gain telescope, dome, weather, or OCS write authority without a formal external contract.

## UI route and runtime strategy

Default routes:

```text
/ui        -> v7.1 operator-console prototype
/ui/v7     -> v7.1 explicit prototype
/ui/v5     -> v5 fallback shell
/ui/legacy -> v5 fallback alias
/ui/v6     -> v6 review shell
```

Current runtime policy:

```text
v7 runtime master gate     default on
runtime_status.js          default on
observe_runtime.js         default on
observe_guard.js           default on
setup_runtime.js           default on
instrument_runtime.js      default on
preset_runtime.js          default on
sequence_runtime.js        default on with Observe
```

Reasoning:

- Observe is now part of the active command-feedback workflow.
- Status runtime is needed for operator context.
- Observe guard is a UI guard, not a backend safety authority.
- Setup/Instrument/Presets now share the default operator workflow and remain individually disableable for troubleshooting.
- Sequence execution remains operator-stepped; runtime JavaScript does not become backend authority.

HTML owns durable structure. Runtime JavaScript enhances existing skeletons and should not create duplicate competing panels except as a fallback when a skeleton is missing.

## Roadmap

### Completed contract-hardening baseline

```text
Phase 2.9-A  Setup/Data Context
Phase 2.9-B  Observation Request / Preview / Arm Gate
Phase 2.9-C  Observation Command Feedback + v7 Observe feedback UI
Phase 2.9-D  ExposureRecord / DataProductRef contract
Phase 2.9-E  Read-only ObservatoryContext
Phase 2.9-F  Operator Workflow Polish
Phase 3.0-A  Observation Plan / operator-stepped Sequence Contract
Phase 3.0-B  Minimum Safe Recovery (Lite)
Transition   Camera Roles / Acquisition Workspace
```

### Active ICS Beta mainline

The near-term objective is a short, stable path to trustworthy raw science and
calibration FITS while telescope pointing remains an external/manual
responsibility:

```text
Phase 3.1  Science FITS contract closure
Phase 3.2  Deployment topology/schema v2 plus real-camera and hardware-fact readiness
Phase 4.0  First single-science-camera acquisition through ICS Beta
Phase 4.1  Stable operator-driven Science/Bias/Dark/Flat/Arc acquisition
Phase 4.2  Science camera + slit/guide camera + required instrument-state integration
```

Phase 3.0-B Lite deliberately uses versioned JSON rather than a database. It
persists plans, progress, completed ExposureRecords, active-step identity, and
frame reservations. Restart during an uncertain active step requires explicit
Retry, Abort, or Mark Failed; Retry is unavailable if a possible FITS is found.

The transition fixes three responsibilities before Phase 3.1: science Single
exposure, science operator-stepped Sequence, and continuous slit/guide Preview.
The science acquisition path has no separate preview lifecycle. Save intent is
an acquisition property, defaults off, and alone controls file-index
reservation and FITS/quicklook persistence. Slit/guide Preview defaults on,
remains independent from science acquisition, and never writes data products.

This responsibility split does not collapse the instrument-facing display
topology. Observe keeps a height-balanced slit/guide image above three B/G/R
science panes. The beta bridge mirrors one shared science-camera readout into
those stable logical channels and labels that fact; the structure remains ready
for three independent science cameras.

That B/G/R presentation is the current JUST/Beta compatibility topology, not a
universal UI requirement. A profile-driven operator console must also support a
single-channel long-slit instrument without inventing B/G/R channels. The
campus Lhires profile is the first concrete test of this boundary.

Phase 3.1 is now closed: FITS uses a standards-readable unsigned-16 contract,
atomic no-overwrite publication, requested/actual timing, stable frame types,
detector/CFA/cooling metadata, checksums, sizes, and independent Astropy
validation. Phase 3.2-A schema v2 and Phase 3.2-B standalone ZWO hardware spike
are also complete. The active Phase 3.2-C boundary is managed Runtime/API
ownership of camera startup, serial binding, exposure, cooling, telemetry
validity, abort, shutdown, and reconnect. The standalone hardware path is proof
of the adapter and data-product chain; it does not by itself close Phase 4.0's
operator/API acceptance loop.

Unattended multi-step auto-advance is not on the Phase 4.2 critical path.
Single-exposure completion ownership may be added with the real-camera
lifecycle, without first building an unattended scheduler.

### Deferred beyond the active mainline

Phase 5.0 observatory/OCS integration and later production automation are
paused. Full automatic retry/resume, a data-product database/archive, closed-loop
guiding, independent physical B/G/R cameras, role enforcement, and a large UI
redesign must not block the Phase 4.2 science-FITS objective.

## Technology adoption gate

A new database, event system, hardware bus, fieldbus, external platform, protocol, or large framework must answer:

```text
1. What current project problem does it solve?
2. Is that problem present in the current phase?
3. Is there real hardware, real operations, or a real interface contract behind it?
4. Can a simpler schema, simulator, file contract, or adapter boundary solve it for now?
5. Does it preserve Domain / Kernel / Application / Adapter boundaries?
6. Does it keep low-level engineering complexity out of routine operator UI?
7. Can it be covered by pytest, integration tests, or hardware-in-loop tests?
8. If we do not adopt it now, can the current phase still move forward cleanly?
```

If these questions cannot be answered, keep the item as:

```text
TBD
candidate
adapter-bounded
future integration
```

Do not promote it into the main roadmap.

## Hardware reality constraints

Current software design must respect these facts:

- JUST long-slit is a B/G/R three-channel spectrograph, not a Blue/Red two-channel instrument.
- Slit width must preserve both operator angular units and backend mechanical units.
- The current `1 arcsec = 128.34 um` conversion is specific to the JUST optical
  train and must not be promoted into the generic core.
- Calibration involves mode/path/source/lamp/frame-type compatibility, not only lamp on/off.
- Slit monitor / guider should remain a first-class visible concept.
- TCS context is part of readiness, but early integration should be read-only.
- Real hardware protocol choices are not yet software-roadmap commitments.
- Bottom-layer integration remains hardware-selection-driven.

### Campus integration profile

The identified campus platform is a 50 cm dual-Nasmyth telescope with a Lhires
III at one focal station. The provisional preferred binding assigns a ZWO
ASI294MC Pro to science/engineering acquisition and a compact monochrome camera
to the Lhires reflective-slit guide port. These are deployment choices and do
not become ICS 2.0 defaults.

Relevant instrument facts to verify against the exact hardware unit before
coding include:

- Lhires is nominally an f/10 instrument and uses discrete slit apertures rather
  than the current JUST continuous slit conversion;
- its acquisition and guide ports have different mechanical interfaces and
  backfocus requirements;
- its science topology is one tunable spectrum channel rather than B/G/R;
- calibration lamp and grating control may be manual or version-dependent and
  must be reported honestly until a real command interface is verified;
- a second Nasmyth camera is a separate focal-station resource and does not
  substitute for common-path slit guiding.

If the 50 cm focus is actually f/10, the plate scale is approximately
41.25 arcsec/mm and a 23 um slit projects to approximately 0.95 arcsec. This is
an engineering estimate only; readiness and UI values must use the measured
site optical configuration.

The ASI294MC Pro is a cooled color detector. It is suitable for engineering
first light and may support limited science validation, but the primary FITS
must preserve the un-debayered raw mosaic with pixel-format/CFA, gain, offset,
ROI, binning, requested/actual timing, and cooling metadata. Debayering may be
used for a labeled quicklook, not as an unrecorded mutation of primary data.

The 2026-08-22 hardware spike verified that the generic detector adapter can
load the vendor SDK directly, bind the detected serial, enumerate controls,
write and restore cooler state, acquire full-frame RAW16, and publish an ICS
FITS plus quicklook with `SIMULATE=false`. This does not make ASI294MC Pro a
default or introduce ASIStudio as a dependency. The durable architecture stays:

```text
generic detector/cooling contract
  -> deployment role binding
  -> ZWO adapter/driver
  -> ASICamera2 SDK and installed device driver
```

The next architectural gate is lifecycle ownership by Runtime/Application and
vendor-neutral API exposure. Machine-local SDK paths belong in deployment
configuration or environment, not generic profiles shipped as defaults.

Reference hardware documents:

- [Shelyak Lhires III product and interface specifications](https://www.shelyak.com/produit/spectroscope-lhires-iii/?lang=en)
- [Shelyak Lhires III guiding and calibration upgrade guide](https://www.shelyak.com/wp-content/uploads/DC0026C-Guide-Utilisateur-Kit-Lhires-III-EN.pdf)
- [ZWO ASI294 camera manual](https://astronomy-imaging-camera.com/manuals/ASI294_Manual_EN_V2.0.pdf)

## Documentation policy

Repository documentation should remain few and durable.

Current durable documents:

```text
README.md
docs/project_status.md
docs/ics2_software_development_strategy.md
docs/operator_console_requirements.md
```

Maintenance rules:

```text
README.md
  Only current repository facts. Do not write implementation history.

docs/project_status.md
  Rewrite the current snapshot at phase boundaries. Do not append project history.

docs/ics2_software_development_strategy.md
  Update only when strategy, architecture, roadmap, or documentation policy changes.

docs/operator_console_requirements.md
  Update only when UI responsibility boundaries, capability classification, or hardware facts change.
```

Do not add one-off phase notes unless there is a clear reason they cannot be folded into one of the durable documents.

A good markdown document should help the next developer decide what to do now. If it mainly explains how the project arrived here, it probably belongs in git history, not in the current document set.

## Success criteria

Short term:

- full test suite remains green;
- current UI/API behavior matches documentation;
- C-stage command feedback remains stable;
- next phase starts from a narrow contract boundary.

Medium term:

- ExposureRecord/DataProductRef semantics become durable;
- simulator-backed end-to-end observing flow becomes repeatable;
- read-only observatory/TCS context becomes honest and useful;
- operator workflow becomes clearer without exposing engineering complexity.

Long term:

- OCS can submit observing intent and read results;
- real hardware integrates through adapter contracts;
- failures, blocked operations, aborts, discards, and recovery steps remain auditable;
- operators can distinguish real, simulated, unavailable, stale, and future capabilities.
