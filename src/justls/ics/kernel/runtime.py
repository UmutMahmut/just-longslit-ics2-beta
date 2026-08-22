from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from justls.ics.adapters.camera.adapter import SimPreviewCameraAdapter
from justls.ics.adapters.detector.adapter import SimDetectorAdapter
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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class RuntimeConfig:
    run_mode: RunMode = RunMode.SIM
    app_name: str = "ICS Beta"
    version: str = "0.1.0"
    telemetry_enabled: bool = False
    camera_config_path: str | None = None


@dataclass(slots=True)
class Runtime:
    config: RuntimeConfig
    system_state: SystemStateSnapshot
    slit: SlitSubsystem | None = None
    lamps: CalibrationSubsystem | None = None
    detector: DetectorSubsystem | None = None
    slit_camera: SimPreviewCameraAdapter | None = None
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

    def get_camera_status_dict(self) -> dict[str, Any]:
        science = (
            self.detector.adapter.get_status()
            if self.detector is not None
            else None
        )
        slit = self.slit_camera.get_status() if self.slit_camera is not None else None
        return {
            "profile_name": (
                self.camera_config.profile_name if self.camera_config else None
            ),
            "config_path": self.camera_config_path,
            "data_root": self.data_root,
            "science_camera": science,
            "slit_camera": slit,
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

        return runtime

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

    def _build_detector_subsystem(self) -> DetectorSubsystem | None:
        if self.config.run_mode == RunMode.SIM:
            if self._camera_config.science_camera.driver != "simulated":
                raise NotImplementedError(
                    "The selected science-camera profile requires a ZWO driver; "
                    "use cameras.sim.json until that driver is implemented."
                )
            driver = SimDetectorDriver(self._camera_config.science_camera)
            adapter = SimDetectorAdapter(
                driver,
                writer=LocalDataProductWriter(self._data_root),
                logical_channels=tuple(
                    self._camera_config.logical_science_channels
                ),
            )
            return DetectorSubsystem(adapter=adapter)

        raise NotImplementedError("HW detector adapter is not implemented yet.")

    def _build_slit_camera(self) -> SimPreviewCameraAdapter | None:
        if self.config.run_mode == RunMode.SIM:
            slit_camera = self._camera_config.slit_camera
            if slit_camera is None:
                return None
            if slit_camera.driver != "simulated":
                raise NotImplementedError(
                    "The selected slit-camera profile requires a ZWO driver; "
                    "use cameras.sim.json until that driver is implemented."
                )
            driver = SimPreviewCameraDriver(slit_camera)
            return SimPreviewCameraAdapter(driver)
        raise NotImplementedError("HW slit camera adapter is not implemented yet.")


_default_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    global _default_runtime
    if _default_runtime is None:
        _default_runtime = RuntimeAssembler().build()
    return _default_runtime


def reset_runtime() -> Runtime:
    global _default_runtime
    _default_runtime = RuntimeAssembler().build()
    return _default_runtime
