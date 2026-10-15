# Project Status

## Snapshot

```text
Project: ICS Beta
Status: Phase 3.1 closed; Phase 3.2 schema-v2 and standalone ZWO hardware spike complete
Validation: pytest -q --basetemp .pytest-tmp -> 322 passed (2026-08-22)
Current emphasis: integrate the proven ZWO path into managed runtime/API lifecycle without weakening the generic detector boundary
```

This file is a current-state snapshot. Historical detail belongs in git history.

Astropy is now a development dependency and independently validates produced
FITS files.

## Campus Test Platform Direction

The currently identified campus test platform is a 50 cm telescope with two
Nasmyth focal stations. One focal station is intended to carry a Shelyak Lhires
III long-slit spectrograph. This is a development and integration platform, not
the default hardware definition for ICS 2.0.

The planned two-camera arrangement is provisionally:

- ZWO ASI294MC Pro on the Lhires III acquisition port as the first
  science/engineering detector;
- a compact monochrome camera on the Lhires reflective-slit guide port for
  slit viewing and eventual guiding.

ASI294MC Pro may be used temporarily as a guide camera for a mechanical or SDK
test, but this is not the preferred operational assignment. Its cooled 4/3-inch
color sensor is more useful for acquisition than for short-cadence guiding, and
the Lhires guide port is designed around a compact C-mount camera. If the second
available camera is a better matched cooled monochrome science detector, the
role assignment must be reviewed rather than treated as fixed.

The Lhires test profile has one logical science spectrum channel. It must not be
represented as the final JUST B/G/R topology. A camera placed at the second
Nasmyth focus is a separate focal-station resource and cannot replace the
Lhires common-path reflective-slit guide camera.

### Vendor-tool bench baseline (2026-08-22)

Windows and the installed ZWO USB3 driver enumerate the ASI294MC Pro correctly.
ASICap and ASIImg were used once as reference tools to confirm full-frame
acquisition, RAW16/RGGB FITS semantics, and cooler operation with external 12 V
power. A stopped fan while the software cooler state is off is not by itself a
fan fault.

That vendor-tool connectivity gate is complete; repeated Bias/Dark acquisition
is not required at this stage. ASIImg and ASICap are reference/oracle tools only
and must not become ICS runtime dependencies. The production boundary remains:

```text
ICS generic detector contract -> ZWO adapter -> vendor driver/SDK
```

ICS owns camera lifecycle and FITS persistence.

### Direct ICS/ZWO SDK verification (2026-08-22)

The standalone hardware spike now proves the dependency boundary directly:

- ICS loads the locally configured `ASICamera2` SDK library without importing
  or launching any ASIStudio application;
- read-only discovery found one `ZWO ASI294MC Pro`, camera ID 0, a readable
  eight-byte serial number, sensor `4144 x 2822`, 4.63 um pixels, 14-bit color
  RGGB, USB 3, cooling, Bin 1/2/3/4, and RAW8/RGB24/Y8/RAW16 output;
- open/init/control enumeration confirmed writable Gain, Exposure, Offset,
  Target Temperature, and Cooler On controls, plus read-only Temperature and
  Cooler Power telemetry. This camera exposes no independent Fan On control;
- ICS set the cooler target to `-10 C`, read back `COOLER_ON=true`, and restored
  the prior off/`0 C` state after a two-second smoke cycle;
- ICS performed one full-frame Bin 1 RAW16 exposure at `0.01 s`, Gain 0,
  Offset 30, and wrote its own FITS and PNG quicklook without vendor capture
  software;
- Astropy independently opened the resulting one-HDU `uint16` FITS and verified
  its `2822 x 4144` shape, RAW16/14-bit/RGGB metadata, `SIMULATE=false`, and
  recorded checksum consistency;
- the driver validates the detected serial against the deployment profile so a
  configured instrument does not silently bind to a different ZWO camera.

The smoke-test FITS is an engineering connectivity frame, not calibrated sky
data. One exposure was intentionally sufficient; a Bias/Dark series is not the
critical path at this stage.

Known hardware-integration gaps:

- the proven driver is not yet owned by the main Runtime/FastAPI startup and
  shutdown lifecycle;
- cooler commands and telemetry are not yet exposed through the stable generic
  API/state-machine contract;
- the first temperature value immediately after camera initialization can be
  stale (observed as `0.0 C`); runtime telemetry needs a settling/validity rule;
- abort was implemented, but early-stop-and-retained-readout behavior has not
  yet been verified on this SDK/camera combination;
- ROI/binning combinations, disconnect/reconnect, USB interruption, long
  exposures, and error recovery still need hardware-in-loop tests;
- simultaneous science exposure and independent slit/guide preview must wait
  for the second camera and its role binding.

Facts still required before hardware integration:

- actual telescope focal ratio and plate scale at the selected Nasmyth focus;
- available backfocus, adapter train, load, balance, rotator orientation,
  flexure, cable routing, and focal-station selection behavior;
- exact Lhires III version, grating modules, slit set, calibration module, and
  which adjustments or lamps are manual versus remotely controllable;
- exact identity and capabilities of the second camera; additional ZWO SDK
  materials; ROI/binning combinations; long-exposure, abort, disconnect, and
  readout error behavior;
- USB topology, 12 V power arrangement, cooling set points, and disconnect or
  power-loss behavior.

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
- Phase 3.1 science-FITS closure: independently readable unsigned-16 FITS,
  Science/Bias/Dark/Flat/Arc/Test frame metadata, requested/actual timing,
  detector/cooling metadata, atomic no-overwrite publication, checksums, sizes,
  and record/header consistency.
- Reusable detector-adapter conformance tests shared by the simulator and real
  adapter boundary.
- Camera configuration schema v2: physical device registry separated from
  deployment role bindings, generic logical channel names, optional slit
  camera, legacy v1 in-memory migration, and unchanged default B/G/R behavior.
- A non-default single-SCI `test-50cm-lhires-asi294` deployment example.
- Standalone ZWO SDK discovery, control/cooling, serial validation, RAW16 snap
  exposure, ICS FITS/quicklook persistence, and real-hardware smoke validation.

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

- managed Runtime/FastAPI ownership of the proven ZWO detector driver;
- real dual-camera science plus slit/guide integration;
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
Phase 3.1    Science FITS Contract Closure                closed
Phase 3.2-A  Device Registry / Role-Binding Schema v2     baseline complete
Phase 3.2-B  Standalone ZWO Hardware Spike                complete
Phase 3.2-C  Managed Runtime/API Hardware Integration     active next boundary
```

## Recommended Next Boundary

Phase 3.2-C promotes the successful standalone driver into a managed hardware
runtime without pretending that the whole instrument is already real:

1. add an explicit mixed/integration deployment mode or equivalent per-device
   driver selection; do not label simulated slit/lamp subsystems as real;
2. give Runtime/application startup and shutdown ownership of ZWO open/init,
   abort-on-shutdown, cooler-safe policy, close, and reconnect behavior;
3. bind the physical camera by configured serial, with camera index only as a
   discovery detail;
4. expose vendor-neutral cooler set point/on-off and temperature/power telemetry
   with initialization-settling and stale/invalid semantics;
5. route normal Arm/Start/Finish API calls through the real detector adapter and
   repeat the one-frame FITS acceptance through FastAPI, not only the CLI;
6. verify stop/abort, timeout, USB disconnect, reconnect, file-publication
   failure, and shutdown behavior before calling Phase 4.0 complete.

After that, Phase 4.1 should run a small deliberate Science/Bias/Dark/Flat/Arc
acceptance matrix. Large calibration stacks are unnecessary until repeatability
or detector characterization becomes the actual question.

The first on-sky acceptance loop should acquire Bias, Dark, Flat, Arc, and a
bright-target Science frame, preferably beginning near H-alpha. Closed-loop
guiding and unattended sequence execution are later boundaries.

## Resume Checklist

When work resumes after a long pause:

1. read this document and treat Phase 3.2-C, not Phase 3.1, as the active
   boundary;
2. reconnect the ASI294MC Pro, set `ICS_ZWO_SDK_LIBRARY` to the local SDK path,
   and verify read-only discovery with
   `python -m justls.ics.drivers.zwo.probe`;
3. rerun the configured suite with
   `python -m pytest -q --basetemp .pytest-tmp` and compare with 322 passed;
4. preserve the separation between generic device/role contracts and the
   `test-50cm-lhires-asi294` deployment profile;
5. integrate lifecycle/API ownership before taking more repeated test frames.

## Engineering Cautions

- Frontend guards are advisory; backend guards remain authoritative.
- Do not present simulated files as sky data.
- Do not imply B/G/R aliases are separate physical cameras.
- Do not present Lhires III, the 50 cm telescope, or ASI294MC Pro as ICS 2.0 defaults.
- Do not reuse the JUST slit conversion for Lhires; the conversion is optical-train and instrument-profile specific.
- Do not debayer or otherwise transform the primary ASI294 science frame silently; display conversion belongs to quicklook metadata.
- Do not add OCS/TCS write authority without an external contract.
- Do not describe the durable, operator-stepped executor as unattended automation.
- Do not introduce a database until restart/recovery requirements justify it.
- Run one ICS Beta server process against a sequence-state JSON file; Lite does not provide cross-process locking.
