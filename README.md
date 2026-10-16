# ICS Beta

ICS Beta is an attended acquisition and development platform for a small
spectrograph on a 50 cm telescope. It is distinct from the eventual JUST ICS.
The beta slit and lamps are manually operated; their simulator adapters remain
available. The current ZWO cameras are deployment choices, not architectural
requirements for future detectors.

## Verified baseline (2026-10-16)

The integrated candidate retains main's generic device/role contracts, FITS
publication and durable sequence recovery, and incorporates the useful
`stable/2026-10-15` snapshot features with acquisition-lifecycle repairs.

- Simulator single/sequence workflows; automatic per-exposure readout by default.
- Operator starts each sequence step; there is no unattended auto-advance.
- Managed ZWO RAW16 science acquisition and independent slit/guide JPEG preview.
- Serial-based dual-camera binding with discovery completed before acquisition.
- Runtime-owned, generation-guarded readout tasks; serialized transitions.
- Reload rejects armed/active exposures and non-terminal sequences.
- SDK native-call timeout quarantine: no further native calls in that process
  after an unresolved timeout or native access violation; restart is required.
- Windows PnP hotplug observation without re-enumerating an active vendor SDK.
- Explicit simulation opt-in. A missing configured real science camera blocks
  acquisition; it does not silently become a simulated detector.
- Optional FITS/PNG persistence, save-last-frame, output-location selection,
  operator instrument context and exposure provenance.

Validation: **440 automated tests passed** on the manual-feedback repair branch.
Bias accepts a zero-second request (mapped to the SDK minimum), Lhires Flat/Arc
use manual illumination, and Observe provides camera acquisition settings.
This local repair round awaits the operator's browser retest before main.
A real ASI294MC Pro + ASI678MC bench
acceptance passed through FastAPI, including independent Astropy FITS validation,
concurrent guide preview, abort/replacement, sequences, reload and shutdown/restart.
See `docs/project_status.md` for evidence, limits and integration provenance.

ZWO retained early readout is explicitly unsupported in the current snap adapter.
Stop & Readout returns a command rejection while preserving automatic completion;
Abort discards the exposure. Premature Finish is rejected without cancelling the
automatic timer. Simulation retains its early-readout contract.

## Development and startup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q --basetemp var/pytest
```

Simulation server:

```powershell
.\.venv\Scripts\python.exe -m uvicorn justls.ics.app.main:app --app-dir src --host 127.0.0.1 --port 8123
```

Open `http://127.0.0.1:8123/ui` or `/ui/v7`. `/ui/v5` and `/ui/legacy` are
fallback shells; `/ui/v6` is a review shell. Use backend-served pages.

Explicit real dual-camera deployment (set the SDK path for this machine):

```powershell
.\start_ics.ps1 -SdkLibrary "C:\vendor\ASICamera2.dll" -NoBrowser
```

The launcher uses `.venv\Scripts\python.exe` or a non-Store Python on PATH;
`-Python` selects another interpreter. It refuses an occupied port and never
kills another process. `-ForceSim` explicitly selects simulation; missing SDK
paths do not silently enable simulation. No ASIStudio capture application is
required at runtime. Close competing vendor camera sessions before acquisition.

## Camera profiles and local state

Default: `config/cameras.sim.json`. Override with `ICS_BETA_CAMERA_CONFIG`.

- `cameras.zwo.example.json`: generic vendor template.
- `cameras.lhires-asi294.example.json`: one SCI camera.
- `cameras.lhires-dual-zwo.example.json`: this bench's ASI294 science + ASI678 guide.

Schema v2 separates physical devices from science/slit role bindings. This beta
profile has one SCI channel. The inherited B/G/R UI panes remain compatibility
views of the same readout, not three independent cameras; broader UI topology
work is deferred.

`ICS_BETA_DATA_ROOT` overrides the profile/operator-selected output root.
Saved frames use `var/data/YYYYMMDD/<obs-id>/` by default. Unsaved captures stay
in memory and do not reserve file indices. Saved single exposures reserve at
Arm; saved sequences reserve their range at Load. FITS uses unsigned-16 raw
pixels, honest simulated provenance and atomic no-overwrite publication.
Quicklook display conversion does not alter the primary science pixels.

Default local files (ignored by Git):

```text
.justls/setup_context.json
.justls/sequence_execution.json
.justls/instrument_context.json
.justls/output_location.json
```

Override paths with `JUSTLS_SETUP_CONTEXT_PATH`, `JUSTLS_SEQUENCE_STATE_PATH`,
`JUSTLS_INSTRUMENT_CONTEXT_PATH`, and `JUSTLS_OUTPUT_LOCATION_PATH` respectively.
Run only one ICS server process per device set and state directory. Do not use
Uvicorn multiple workers or hardware development auto-reload.

`JUSTLS_AUTO_READOUT_ENABLED=0` disables automatic completion for manual/scripted
operation. `ICS_BETA_FORCE_SIM=1` explicitly replaces camera drivers with simulation.
`JUSTLS_SLIT_PREVIEW_AUTOSTART=0` disables guide-preview autostart.
`ICS_BETA_HOTPLUG_INTERVAL_S=0` disables OS hotplug monitoring.
See `.env.example` and `docs/operator_runbook.md`.

## Explicit hardware acceptance

Read-only discovery, then optional open/read-controls/close:

```powershell
.\.venv\Scripts\python.exe -m justls.ics.drivers.zwo.probe --dll "C:\vendor\ASICamera2.dll"
.\.venv\Scripts\python.exe -m justls.ics.drivers.zwo.probe --dll "C:\vendor\ASICamera2.dll" --controls
```

The following explicitly acquires real engineering frames using the supplied
ASI294/ASI678 serial profile. It writes an isolated JSON report and FITS files,
uses normal FastAPI lifecycle and endpoints, and releases cameras on exit:

```powershell
.\.venv\Scripts\python.exe tools/hardware_acceptance.py --hardware --dll "C:\vendor\ASICamera2.dll"
```

It does not change cooler settings or physically unplug devices. Automated
regressions cover injected timeout/disconnect/storage failures. Real cable-loss
and power-loss behavior and on-sky usability remain separate acceptance work.

## API and development boundaries

FastAPI contracts: `/docs`; status: `/api/v1/status/full` and
`/api/v1/cameras/status`. Observation preview is side-effect-free; Arm reruns
readiness. Commands carry request/job feedback; exposure records carry product
and physical-camera provenance. Sequence state is durable; interrupted active
steps require explicit recovery, never automatic mid-exposure resume.

Keep Domain / Kernel / Application / API / UI / Adapter boundaries. Backend
ownership guards remain authoritative. Real science, simulated actuators and
operator-declared settings must not be confused. There is no OCS/TCS control,
closed-loop guiding or unattended scheduler in this milestone.

Durable documentation:

- `docs/project_status.md`: current evidence, provenance and next boundaries.
- `docs/operator_runbook.md`: startup and recovery.
- `docs/ics2_software_development_strategy.md`: broader development strategy.
- `docs/operator_console_requirements.md`: console requirements and constraints.

If no LICENSE exists, treat this repository as internal until one is chosen.
