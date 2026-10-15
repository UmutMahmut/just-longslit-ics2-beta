from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from justls.ics.adapters.camera.adapter import PreviewCameraAdapter
from justls.ics.adapters.detector.adapter import DetectorAdapter, SimDetectorAdapter
from justls.ics.adapters.lamps.adapter import SimCalibrationAdapter
from justls.ics.adapters.slit.adapter import SimSlitAdapter
from justls.ics.domain.detector.config import (
    DetectorConfig,
    build_beta_detector_config,
    build_default_detector_config,
)
from justls.ics.domain.detector.subsystem import DetectorSubsystem
from justls.ics.domain.lamps.subsystem import CalibrationSubsystem
from justls.ics.domain.observation.sequence import SequenceExecutionSnapshot
from justls.ics.domain.slit.subsystem import SlitSubsystem
from justls.ics.drivers.sim.camera_driver import SimPreviewCameraDriver
from justls.ics.drivers.sim.detector_driver import SimDetectorDriver
from justls.ics.drivers.sim.lamp_driver import SimCalibrationDriver
from justls.ics.drivers.sim.slit_driver import SimSlitDriver
from justls.ics.infra.camera_config import (
    CameraSystemConfig,
    load_camera_system_config,
    resolve_data_root,
)
from justls.ics.infra.data_products import LocalDataProductWriter
from justls.ics.infra.hotplug import HotplugMonitor, make_probe
from justls.ics.kernel.errors import ICSException
from justls.ics.kernel.jobs import CommandRequest, JobRecord, JobTracker
from justls.ics.kernel.states import (
    ControlState,
    ExposureState,
    RunMode,
    SubsystemState,
    SystemStateSnapshot,
    build_initial_state,
)


logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _env_flag(name: str, default: bool) -> bool:
    """Read a boolean toggle from the environment."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _force_sim_enabled() -> bool:
    """Return true when the runtime must skip all ZWO SDK access.

    When the ZWO SDK is in a bad USB state (camera hot-replugged mid-session,
    driver stale after a forced kill, etc.) the native library can hang the
    service and cause the uvicorn worker to crash. Operators can opt in to
    "safe mode" with ``ICS_BETA_FORCE_SIM=1``; the resulting runtime is fully
    simulated and exposes the same HTTP surface, so UI work can continue
    while the hardware problem is repaired.
    """
    return _env_flag("ICS_BETA_FORCE_SIM", False)


def _hotplug_interval_s(default: float = 30.0) -> float:
    """Return the hot-plug poll interval in seconds.

    Operators can override with ``ICS_BETA_HOTPLUG_INTERVAL_S=15`` for tighter
    detection, or ``0`` to disable the background monitor entirely. The
    monitor is only started when a real ZWO driver successfully bound, so
    setting ``0`` is safe in fully-simulated deployments.
    """
    raw = os.environ.get("ICS_BETA_HOTPLUG_INTERVAL_S")
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw.strip())
    except ValueError:
        logger.warning(
            "ICS_BETA_HOTPLUG_INTERVAL_S=%r is not a number; using default %s",
            raw, default,
        )
        return default
    if value < 0:
        logger.warning(
            "ICS_BETA_HOTPLUG_INTERVAL_S=%r is negative; using default %s",
            raw, default,
        )
        return default
    return value


@dataclass(slots=True)
class RuntimeConfig:
    run_mode: RunMode = RunMode.SIM
    app_name: str = "ICS Beta"
    version: str = "0.1.0"
    telemetry_enabled: bool = False
    camera_config_path: str | None = None
    # The slit/guide camera is the observer's live view; it must be running as
    # soon as the system is up, not only after someone clicks "start preview".
    slit_preview_autostart: bool = field(
        default_factory=lambda: _env_flag("JUSTLS_SLIT_PREVIEW_AUTOSTART", True)
    )


@dataclass(slots=True)
class Runtime:
    config: RuntimeConfig
    system_state: SystemStateSnapshot
    # Whether this runtime was assembled from simulated drivers because the
    # ZWO SDK was forced off (ICS_BETA_FORCE_SIM=1). Surfaced via
    # /api/v1/cameras/status so the operator console can render a banner.
    force_sim: bool = False
    slit: SlitSubsystem | None = None
    lamps: CalibrationSubsystem | None = None
    detector: DetectorSubsystem | None = None
    slit_camera: PreviewCameraAdapter | None = None
    # Why the guide/slit camera is missing (unplugged, busy, driver error).
    # Recorded so /api/v1/cameras/status can explain the degradation instead of
    # silently reporting null.
    slit_camera_error: str | None = None
    camera_config: CameraSystemConfig | None = None
    camera_config_path: str | None = None
    data_root: str | None = None
    detector_config: DetectorConfig = field(default_factory=build_default_detector_config)
    job_tracker: JobTracker = field(default_factory=JobTracker)
    sequence_execution: SequenceExecutionSnapshot | None = None
    sequence_execution_loaded: bool = False
    sequence_persistence_path: str | None = None
    sequence_persistence_error: str | None = None
    sequence_lock: RLock = field(default_factory=RLock, repr=False)
    started_at: datetime = field(default_factory=utc_now)
    # Background hot-plug monitor (None when the runtime is fully simulated or
    # when no ZWO driver successfully bound). The monitor is advisory: it only
    # records camera-count changes via the SDK; it never rebinds drivers.
    hotplug_monitor: HotplugMonitor | None = None
    # Probe interval in seconds; the value is owned by the assembler so the
    # ``/api/v1/cameras/status`` payload reflects what the monitor was started
    # with (and so unit tests can inspect it without poking private state).
    hotplug_interval_s: float = 0.0

    def get_snapshot(self) -> SystemStateSnapshot:
        if self.detector is not None:
            detector_snapshot = self.detector.get_snapshot()
            self.system_state.exposure_state = detector_snapshot.state
        self.system_state.refresh_timestamp()
        return self.system_state

    def status_dict(self) -> dict[str, Any]:
        snapshot = self.get_snapshot()
        return {
            "app_name": self.config.app_name,
            "version": self.config.version,
            "run_mode": self.config.run_mode.value,
            "telemetry_enabled": self.config.telemetry_enabled,
            "started_at": self.started_at.isoformat(),
            "state": snapshot.to_dict(),
            "latest_job": self.latest_job_dict(),
        }

    def get_capabilities_dict(self) -> dict[str, bool]:
        return {
            "slit": self.slit is not None,
            "slit_angle": self.slit is not None,
            "calib_lamps": self.lamps is not None,
            "rotator": False,
            "slit_monitor_camera": self.slit_camera is not None,
            "guider": False,
            "science_channels_bgr": self.detector is not None,
            "fast_photometry": False,
        }

    def set_data_root(self, data_root: str | Path) -> str:
        """Repoint where saved frames are written, live.

        The detector adapter owns the writer instance, so the new root has to be
        pushed into it as well; otherwise the UI would show one folder while the
        FITS still landed in the old one.
        """
        candidate = Path(str(data_root)).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        resolved = candidate.resolve()
        self.data_root = str(resolved)

        adapter = self.detector.adapter if self.detector is not None else None
        writer = getattr(adapter, "writer", None)
        setter = getattr(writer, "set_data_root", None)
        if callable(setter):
            setter(resolved)
        return self.data_root

    def shutdown(self) -> None:
        """Managed teardown: abort in-flight exposures and release hardware.

        Hardware drivers (e.g. ZWO) hold exclusive OS handles on cameras;
        without an explicit disconnect the process can leave a camera busy
        for the next session. Simulated drivers simply have no disconnect
        hook and are skipped.
        """
        if self.hotplug_monitor is not None:
            # Stop the background polling thread before releasing the SDK
            # handle it is probing; otherwise it can crash mid-tick.
            try:
                self.hotplug_monitor.stop(timeout_s=2.0)
            except Exception:
                logger.exception("hot-plug monitor stop failed")
            self.hotplug_monitor = None
        if self.detector is not None:
            adapter = self.detector.adapter
            try:
                adapter.abort_exposure()
            except Exception:
                pass
            driver = getattr(adapter, "driver", None)
            disconnect = getattr(driver, "disconnect", None)
            if callable(disconnect):
                disconnect()
        if self.slit_camera is not None:
            driver = getattr(self.slit_camera, "driver", None)
            disconnect = getattr(driver, "disconnect", None)
            if callable(disconnect):
                try:
                    disconnect()
                except Exception:
                    pass

    def get_camera_status_dict(self) -> dict[str, Any]:
        science = (
            self.detector.adapter.get_status()
            if self.detector is not None
            else None
        )
        slit = self.slit_camera.get_status() if self.slit_camera is not None else None
        if slit is None:
            # The guide/slit camera is an operator aid; if it is unplugged the
            # science path must still work, so report it as degraded rather
            # than hiding the fact that it was configured.
            slit = {
                "device_id": (
                    self.camera_config.slit_camera.device_id
                    if self.camera_config is not None
                    and self.camera_config.slit_camera is not None
                    else None
                ),
                "role": "slit",
                "connected": False,
                "state": "unavailable",
                "preview_enabled": False,
                "message": self.slit_camera_error or "slit/guide camera is not available",
            }
        return {
            "profile_name": (
                self.camera_config.profile_name if self.camera_config else None
            ),
            "config_path": self.camera_config_path,
            "data_root": self.data_root,
            "science_camera": science,
            "slit_camera": slit,
            "service": {
                "force_sim": self.force_sim,
                "run_mode": self.config.run_mode.value,
                "slit_preview_autostart": self.config.slit_preview_autostart,
                "message": (
                    "hardware probing disabled (ICS_BETA_FORCE_SIM=1); "
                    "running in safe simulation mode"
                    if self.force_sim
                    else None
                ),
            },
            "hot_plug": (
                self.hotplug_monitor.status_dict()
                if self.hotplug_monitor is not None
                else {
                    "enabled": False,
                    "interval_s": self.hotplug_interval_s,
                    "last_count": None,
                    "last_check_at": None,
                    "last_change_at": None,
                    "last_error": None,
                    "message": (
                        "hot-plug monitor not running "
                        "(no ZWO driver bound or ICS_BETA_HOTPLUG_INTERVAL_S=0)"
                    ),
                }
            ),
            "bridge": {
                "physical_camera_id": (
                    self.camera_config.science_camera.device_id
                    if self.camera_config
                    else None
                ),
                "logical_channels": (
                    list(self.camera_config.logical_science_channels)
                    if self.camera_config
                    else []
                ),
                "shared_capture": (
                    self.camera_config.science_binding.shared_capture
                    if self.camera_config
                    else False
                ),
            },
        }

    def get_detector_config(self) -> DetectorConfig:
        return self.detector_config

    def get_detector_config_dict(self) -> dict[str, Any]:
        return self.detector_config.to_dict()

    def set_detector_config(self, config: DetectorConfig | dict[str, Any]) -> DetectorConfig:
        if isinstance(config, DetectorConfig):
            self.detector_config = config
        else:
            self.detector_config = DetectorConfig.model_validate(config)
        return self.detector_config

    def latest_job(self) -> JobRecord | None:
        return self.job_tracker.latest_job()

    def latest_job_dict(self) -> dict[str, Any] | None:
        job = self.latest_job()
        return job.to_dict() if job else None

    def get_subsystem_state(self, name: str) -> SubsystemState:
        mapping = {
            "system": self.system_state.system,
            "slit": self.system_state.slit,
            "lamps": self.system_state.lamps,
            "detector": self.system_state.detector,
            "health": self.system_state.health,
        }
        try:
            return mapping[name]
        except KeyError as exc:
            raise KeyError(f"Unknown subsystem: {name}") from exc

    def set_subsystem_connected(
        self,
        name: str,
        connected: bool,
        *,
        message: str = "",
    ) -> SubsystemState:
        subsystem = self.get_subsystem_state(name)
        subsystem.mark_connected(connected, message=message)
        self.system_state.refresh_timestamp()
        return subsystem

    def set_subsystem_state(
        self,
        name: str,
        state: ControlState,
        *,
        message: str = "",
    ) -> SubsystemState:
        subsystem = self.get_subsystem_state(name)
        subsystem.set_state(state, message=message)
        self.system_state.refresh_timestamp()
        return subsystem

    def set_exposure_state(self, state: ExposureState) -> None:
        self.system_state.exposure_state = state
        self.system_state.refresh_timestamp()

    def create_job(
        self,
        request: CommandRequest,
        *,
        subsystem_state_name: str | None = None,
    ) -> JobRecord:
        state_before = None
        if subsystem_state_name is not None:
            state_before = self.get_subsystem_state(subsystem_state_name).state.value
        return self.job_tracker.create_job(request, state_before=state_before)

    def mark_job_running(
        self,
        job_id: str,
        *,
        subsystem: str | None = None,
        message: str = "",
    ) -> JobRecord:
        job = self.job_tracker.mark_running(job_id)
        if subsystem is not None:
            self.set_subsystem_state(subsystem, ControlState.BUSY, message=message)
        return job

    def mark_job_succeeded(
        self,
        job_id: str,
        *,
        subsystem: str | None = None,
        result: dict[str, Any] | None = None,
        message: str = "",
    ) -> JobRecord:
        state_after = None
        if subsystem is not None:
            self.set_subsystem_state(subsystem, ControlState.IDLE, message=message)
            state_after = self.get_subsystem_state(subsystem).state.value
        return self.job_tracker.mark_succeeded(
            job_id,
            result=result,
            state_after=state_after,
        )

    def _parse_control_state(self, value: str | None) -> ControlState | None:
        if value is None:
            return None
        try:
            return ControlState(value)
        except ValueError:
            return None

    def mark_job_rejected(
        self,
        job_id: str,
        exc: ICSException,
        *,
        subsystem: str | None = None,
        message: str = "",
    ) -> JobRecord:
        """
        Mark a job as failed without escalating the subsystem into FAULT.

        This is intended for command rejections such as invalid params,
        invalid state transitions, and unsupported operations.
        """
        state_after = None

        if subsystem is not None:
            job = self.job_tracker.get_job(job_id)
            restore_state = self._parse_control_state(job.state_before if job else None)

            if restore_state is None:
                restore_state = ControlState.IDLE

            self.set_subsystem_state(
                subsystem,
                restore_state,
                message=message or exc.info.message,
            )
            state_after = self.get_subsystem_state(subsystem).state.value

        return self.job_tracker.mark_failed_from_exception(
            job_id,
            exc,
            state_after=state_after,
        )

    def mark_job_failed(
        self,
        job_id: str,
        exc: ICSException,
        *,
        subsystem: str | None = None,
        message: str = "",
    ) -> JobRecord:
        state_after = None
        if subsystem is not None:
            self.set_subsystem_state(
                subsystem,
                ControlState.FAULT,
                message=message or exc.info.message,
            )
            state_after = self.get_subsystem_state(subsystem).state.value
        return self.job_tracker.mark_failed_from_exception(
            job_id,
            exc,
            state_after=state_after,
        )

    def mark_job_aborted(
        self,
        job_id: str,
        *,
        subsystem: str | None = None,
        reason: str = "Job aborted.",
    ) -> JobRecord:
        state_after = None
        if subsystem is not None:
            self.set_subsystem_state(subsystem, ControlState.IDLE, message=reason)
            state_after = self.get_subsystem_state(subsystem).state.value
        return self.job_tracker.mark_aborted(
            job_id,
            reason=reason,
            state_after=state_after,
        )


class RuntimeAssembler:
    def __init__(self, config: RuntimeConfig | None = None) -> None:
        self.config = config or RuntimeConfig()
        self._slit_camera_error: str | None = None
        # Probe instance kept across detector + slit builds so the hotplug
        # monitor (when started) reuses the same SDK handle and avoids an
        # extra ``ASIGetNumOfConnectedCameras``-on-a-second-handle during the
        # reload window. The actual probe closure is built by ``make_probe``
        # with a final SDK instance; if either subsystem ends up taking the
        # sim fallback the monitor is not started.
        self._zwo_sdk_for_monitor = None

    def build(self) -> Runtime:
        state = build_initial_state(self.config.run_mode)
        camera_config, camera_config_path = load_camera_system_config(
            self.config.camera_config_path
        )
        data_root = resolve_data_root(camera_config, camera_config_path)
        self._camera_config = camera_config
        self._data_root = data_root

        slit_subsystem = self._build_slit_subsystem()
        lamps_subsystem = self._build_lamps_subsystem()
        detector_subsystem = self._build_detector_subsystem()
        slit_camera = self._build_slit_camera()

        runtime = Runtime(
            config=self.config,
            system_state=state,
            slit=slit_subsystem,
            lamps=lamps_subsystem,
            detector=detector_subsystem,
            slit_camera=slit_camera,
            slit_camera_error=self._slit_camera_error,
            camera_config=camera_config,
            camera_config_path=str(camera_config_path),
            data_root=str(data_root),
            detector_config=build_beta_detector_config(
                camera_config.science_camera.device_id,
                logical_channels=tuple(camera_config.logical_science_channels),
                profile_name=(
                    camera_config.detector_profile_name
                    or camera_config.profile_name
                ),
                shared_physical_camera=camera_config.science_binding.shared_capture,
            ),
        )
        runtime.force_sim = _force_sim_enabled()

        runtime.set_subsystem_connected("system", True, message="runtime assembled")
        runtime.set_subsystem_state("system", ControlState.IDLE, message="ready")

        runtime.set_subsystem_connected("health", True, message="health service ready")
        runtime.set_subsystem_state("health", ControlState.IDLE, message="ready")

        if slit_subsystem is not None:
            runtime.set_subsystem_connected(
                "slit",
                True,
                message=f"{self.config.run_mode.value} slit adapter ready",
            )
            runtime.set_subsystem_state("slit", ControlState.IDLE, message="ready")

        if lamps_subsystem is not None:
            runtime.set_subsystem_connected(
                "lamps",
                True,
                message=f"{self.config.run_mode.value} calibration adapter ready",
            )
            runtime.set_subsystem_state("lamps", ControlState.IDLE, message="ready")

        if detector_subsystem is not None:
            runtime.set_subsystem_connected(
                "detector",
                True,
                message=f"{self.config.run_mode.value} detector adapter ready",
            )
            runtime.set_subsystem_state("detector", ControlState.IDLE, message="ready")
            runtime.set_exposure_state(ExposureState.READY_TO_ARM)

        # Hot-plug monitor: only when at least one ZWO driver successfully
        # bound to real hardware, and the operator has not disabled it via
        # ``ICS_BETA_HOTPLUG_INTERVAL_S=0``. The monitor is advisory: it
        # records changes; re-binding is an explicit operator action.
        interval_s = _hotplug_interval_s()
        if self._zwo_sdk_for_monitor is not None and interval_s > 0:
            monitor = HotplugMonitor(
                make_probe(self._zwo_sdk_for_monitor),
                interval_s=interval_s,
                initial_count=self._zwo_sdk_for_monitor.connected_camera_count(),
            )
            monitor.start()
            runtime.hotplug_monitor = monitor
            runtime.hotplug_interval_s = interval_s
            logger.info(
                "hot-plug monitor started: interval=%.1fs", interval_s
            )
        else:
            logger.info(
                "hot-plug monitor disabled (sdk=%s, interval=%.1fs)",
                self._zwo_sdk_for_monitor is not None,
                interval_s,
            )

        self._autostart_slit_preview(runtime)

        return runtime

    def _autostart_slit_preview(self, runtime: Runtime) -> None:
        """Bring the slit/guide live view up with the system.

        The preview is the observer's only way to see whether the star is on the
        slit, so it must survive a service restart without a manual click. A
        failure here is reported as a subsystem message instead of aborting
        startup: the science path must stay usable even if the guide camera is
        unplugged.
        """
        if runtime.slit_camera is None or not self.config.slit_preview_autostart:
            return
        if _force_sim_enabled():
            # Sim preview auto-starts as part of the adapter; do not call the
            # real driver to avoid any chance of touching the ZWO SDK.
            try:
                runtime.slit_camera.start_preview()
            except Exception as exc:  # pragma: no cover - sim only
                logger.warning("slit/guide preview failed to start: %s", exc)
            return

        try:
            runtime.slit_camera.start_preview()
        except Exception as exc:  # pragma: no cover - hardware dependent
            # Surfaced through /api/v1/cameras/status (state stays "stopped").
            logger.warning("slit/guide preview failed to start: %s", exc)

    def _build_slit_subsystem(self) -> SlitSubsystem | None:
        if self.config.run_mode == RunMode.SIM:
            driver = SimSlitDriver()
            adapter = SimSlitAdapter(driver)
            return SlitSubsystem(adapter=adapter)

        raise NotImplementedError("HW slit adapter is not implemented yet.")

    def _build_lamps_subsystem(self) -> CalibrationSubsystem | None:
        if self.config.run_mode == RunMode.SIM:
            driver = SimCalibrationDriver()
            adapter = SimCalibrationAdapter(driver)
            return CalibrationSubsystem(adapter=adapter)

        raise NotImplementedError("HW calibration adapter is not implemented yet.")

    def _build_data_product_writer(self) -> LocalDataProductWriter:
        # The FITS writer stamps every saved frame with the operator-declared
        # instrument context (telescope/spectrograph state). The declaration
        # file is re-read per write, so an attended-declaration update via
        # the API lands on the very next frame; a missing/corrupt file never
        # blocks capture.
        from justls.ics.infra.instrument_context import (
            get_instrument_context_path,
            load_instrument_fits_cards,
        )

        declaration_path = get_instrument_context_path()
        return LocalDataProductWriter(
            self._data_root,
            instrument_cards_provider=lambda: load_instrument_fits_cards(
                declaration_path
            ),
        )

    def _build_detector_subsystem(self) -> DetectorSubsystem | None:
        science_camera = self._camera_config.science_camera
        if _force_sim_enabled():
            # Hardware probing is disabled — assemble from the simulated
            # detector driver so the service stays usable.
            driver = SimDetectorDriver(science_camera)
            return DetectorSubsystem(
                adapter=SimDetectorAdapter(
                    driver,
                    writer=self._build_data_product_writer(),
                    logical_channels=tuple(
                        self._camera_config.logical_science_channels
                    ),
                )
            )
        if science_camera.driver == "zwo":
            # Mixed deployment is supported: the science camera may be real
            # hardware while slit/lamps remain simulated. Selection is
            # driver-based, not run-mode-based.
            from justls.ics.drivers.zwo.assembly import build_zwo_detector_driver

            try:
                driver, sdk = build_zwo_detector_driver(science_camera, return_sdk=True)
            except Exception as exc:
                # The ZWO SDK can hang when a camera is in a bad USB state
                # (for example after a hot-replug). The service must still
                # come up so the operator can diagnose and recover; we fall
                # back to the simulated detector and surface the reason.
                logger.error(
                    "science camera unavailable; falling back to simulated "
                    "detector: %s",
                    exc,
                )
                self._slit_camera_error = (
                    f"science camera unavailable: {exc}"
                )
                driver = SimDetectorDriver(science_camera)
                return DetectorSubsystem(
                    adapter=SimDetectorAdapter(
                        driver,
                        writer=self._build_data_product_writer(),
                        logical_channels=tuple(
                            self._camera_config.logical_science_channels
                        ),
                    )
                )
            self._zwo_sdk_for_monitor = sdk
            adapter = DetectorAdapter(
                driver,
                writer=self._build_data_product_writer(),
                logical_channels=tuple(
                    self._camera_config.logical_science_channels
                ),
                simulated=False,
            )
            return DetectorSubsystem(adapter=adapter)

        if self.config.run_mode == RunMode.SIM:
            driver = SimDetectorDriver(science_camera)
            adapter = SimDetectorAdapter(
                driver,
                writer=self._build_data_product_writer(),
                logical_channels=tuple(
                    self._camera_config.logical_science_channels
                ),
            )
            return DetectorSubsystem(adapter=adapter)

        raise NotImplementedError("HW detector adapter is not implemented yet.")

    def _build_slit_camera(self) -> PreviewCameraAdapter | None:
        slit_camera = self._camera_config.slit_camera
        if slit_camera is None:
            return None
        if _force_sim_enabled():
            driver = SimPreviewCameraDriver(slit_camera)
            return PreviewCameraAdapter(driver)
        # Hardware binding is driver-based, not run-mode-based, so mixed
        # profiles (e.g. sim science + real guide camera) keep working.
        if slit_camera.driver == "zwo":
            from justls.ics.drivers.zwo.assembly import build_zwo_preview_driver

            try:
                driver, sdk = build_zwo_preview_driver(
                    slit_camera, role="slit", return_sdk=True
                )
            except Exception as exc:
                # The guide camera is an operator aid, not the science path. A
                # missing/unplugged guide camera must degrade gracefully instead
                # of taking the whole runtime (and the science camera) down.
                self._slit_camera_error = (
                    f"slit/guide camera unavailable: {exc}"
                )
                logger.warning("slit/guide camera unavailable: %s", exc)
                return None
            # Reuse the same SDK instance for the hot-plug monitor if the
            # detector path did not already supply one.
            if self._zwo_sdk_for_monitor is None:
                self._zwo_sdk_for_monitor = sdk
            return PreviewCameraAdapter(driver)
        if self.config.run_mode == RunMode.SIM:
            if slit_camera.driver != "simulated":
                raise NotImplementedError(
                    f"slit-camera driver {slit_camera.driver!r} is not supported; "
                    "use 'simulated' or 'zwo'."
                )
            driver = SimPreviewCameraDriver(slit_camera)
            return PreviewCameraAdapter(driver)
        raise NotImplementedError(
            f"slit-camera driver {slit_camera.driver!r} is not supported in "
            f"run_mode={self.config.run_mode.value!r}."
        )


_default_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    global _default_runtime
    if _default_runtime is None:
        _default_runtime = RuntimeAssembler().build()
    return _default_runtime


def reset_runtime() -> Runtime:
    global _default_runtime
    if _default_runtime is not None:
        # Release hardware handles before discarding the old runtime,
        # otherwise a config reload leaks the exclusive camera session.
        _default_runtime.shutdown()
    _default_runtime = RuntimeAssembler().build()
    return _default_runtime


def shutdown_runtime() -> None:
    """Release the default runtime's hardware handles, if one was built."""
    global _default_runtime
    if _default_runtime is not None:
        _default_runtime.shutdown()
        _default_runtime = None
