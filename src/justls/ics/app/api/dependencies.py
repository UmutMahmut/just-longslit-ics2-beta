from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends

from justls.ics.application.dispatcher import CommandDispatcher, validate_required_params
from justls.ics.application.services.health_service import HealthService
from justls.ics.application.services.instrument_context_service import (
    InstrumentContextService,
)
from justls.ics.application.services.management_service import ManagementService
from justls.ics.application.services.observatory_context_service import (
    ObservatoryContextService,
)
from justls.ics.application.services.observation_service import ObservationService
from justls.ics.application.services.observation_sequence_service import (
    ObservationSequenceService,
)
from justls.ics.application.services.observation_sequence_store import (
    JsonObservationSequenceStore,
    ObservationSequenceStore,
    initialize_runtime_sequence,
)
from justls.ics.application.services.observation_preview_service import ObservationPreviewService
from justls.ics.application.services.output_location_service import OutputLocationService
from justls.ics.application.services.setup_context_service import SetupContextService
from justls.ics.application.services.setup_context_store import JsonSetupContextStore
from justls.ics.infra.output_location import (
    get_output_location_path,
)
from justls.ics.kernel.errors import InvalidStateError, UnsupportedError
from justls.ics.kernel.runtime import Runtime, get_runtime


SETUP_CONTEXT_PATH_ENV = "JUSTLS_SETUP_CONTEXT_PATH"
DEFAULT_SETUP_CONTEXT_PATH = Path(".justls") / "setup_context.json"
SEQUENCE_STATE_PATH_ENV = "JUSTLS_SEQUENCE_STATE_PATH"
DEFAULT_SEQUENCE_STATE_PATH = Path(".justls") / "sequence_execution.json"


def get_runtime_dependency() -> Runtime:
    runtime = get_runtime()
    path = get_sequence_state_path()
    initialize_runtime_sequence(
        runtime,
        JsonObservationSequenceStore(path),
        persistence_path=str(path),
    )
    return runtime


RuntimeDep = Annotated[Runtime, Depends(get_runtime_dependency)]


def get_health_service(runtime: RuntimeDep) -> HealthService:
    return HealthService(runtime)


def get_management_service(runtime: RuntimeDep) -> ManagementService:
    return ManagementService(runtime)


def get_observatory_context_service(runtime: RuntimeDep) -> ObservatoryContextService:
    return ObservatoryContextService(runtime)


def get_setup_context_path() -> Path:
    raw_path = os.getenv(SETUP_CONTEXT_PATH_ENV)
    if raw_path and raw_path.strip():
        return Path(raw_path.strip())
    return DEFAULT_SETUP_CONTEXT_PATH


def get_sequence_state_path() -> Path:
    raw_path = os.getenv(SEQUENCE_STATE_PATH_ENV)
    if raw_path and raw_path.strip():
        return Path(raw_path.strip())
    return DEFAULT_SEQUENCE_STATE_PATH


def get_observation_sequence_store() -> ObservationSequenceStore:
    return JsonObservationSequenceStore(get_sequence_state_path())


def get_setup_context_service() -> SetupContextService:
    return SetupContextService(store=JsonSetupContextStore(get_setup_context_path()))


def get_instrument_context_service() -> InstrumentContextService:
    from justls.ics.infra.instrument_context import get_instrument_context_path

    return InstrumentContextService(path=get_instrument_context_path())


InstrumentContextServiceDep = Annotated[
    InstrumentContextService,
    Depends(get_instrument_context_service),
]


def get_output_location_service(runtime: RuntimeDep) -> OutputLocationService:
    return OutputLocationService(runtime, path=get_output_location_path())


OutputLocationServiceDep = Annotated[
    OutputLocationService,
    Depends(get_output_location_service),
]


def _require_slit(runtime: Runtime):
    if runtime.slit is None:
        raise UnsupportedError(
            "Slit subsystem is unavailable.",
            subsystem="slit",
        )
    return runtime.slit


def _require_lamps(runtime: Runtime):
    if runtime.lamps is None:
        raise UnsupportedError(
            "Calibration subsystem is unavailable.",
            subsystem="lamps",
        )
    return runtime.lamps


def _require_detector(runtime: Runtime):
    if runtime.detector is None:
        raise UnsupportedError(
            "Detector subsystem is unavailable.",
            subsystem="detector",
        )
    return runtime.detector


def _assert_observation_mutation_allowed(runtime: Runtime, action_name: str) -> None:
    if runtime.detector is None:
        return

    state = runtime.detector.get_snapshot().state.value
    if state in {"armed", "exposing"}:
        raise InvalidStateError(
            f"{action_name} is blocked while observation state is {state}",
            subsystem="detector",
            details={
                "observation_state": state,
                "blocked_action": action_name,
            },
        )


def _latest_successful_preset_apply(runtime: Runtime) -> dict | None:
    for job in runtime.job_tracker.list_jobs(limit=20):
        job_dict = job.to_dict()
        request = job_dict.get("request", {})
        result = job_dict.get("result", {})
        if (
            job_dict.get("status") == "succeeded"
            and request.get("subsystem") == "presets"
            and request.get("action") == "apply_preset"
            and result.get("kind") == "preset_apply"
        ):
            return {
                "job_id": job_dict.get("job_id"),
                "preset": result.get("preset"),
                "category": result.get("category"),
                "risk_level": result.get("risk_level"),
                "requires_confirmation": result.get("requires_confirmation"),
                "changed_fields_count": result.get("changed_fields_count"),
                "calibration_applied": result.get("calibration_applied"),
                "slit_applied": result.get("slit_applied"),
                "finished_at": job_dict.get("finished_at"),
            }
    return None


def _handle_slit_set_width(runtime: Runtime, request):
    _assert_observation_mutation_allowed(runtime, "set_slit_width")
    validate_required_params(request, {"width_um"})
    slit = _require_slit(runtime)
    snapshot = slit.set_width_um(float(request.params["width_um"]))
    return snapshot.to_state_fragment()


def _handle_slit_set_angle(runtime: Runtime, request):
    _assert_observation_mutation_allowed(runtime, "set_slit_angle")
    validate_required_params(request, {"angle_deg"})
    slit = _require_slit(runtime)
    snapshot = slit.set_angle_deg(float(request.params["angle_deg"]))
    return snapshot.to_state_fragment()


def _handle_lamp_legacy_set(runtime: Runtime, request):
    _assert_observation_mutation_allowed(runtime, "set_legacy_lamp")
    validate_required_params(request, {"on"})
    lamps = _require_lamps(runtime)
    snapshot = lamps.set_legacy_on(bool(request.params["on"]))
    return snapshot.to_legacy_state_fragment()


def _handle_calibration_set_mode(runtime: Runtime, request):
    _assert_observation_mutation_allowed(runtime, "set_calibration_mode")
    validate_required_params(request, {"mode"})
    lamps = _require_lamps(runtime)
    snapshot = lamps.set_mode(str(request.params["mode"]))
    return snapshot.to_dict()


def _handle_calibration_select_lamp(runtime: Runtime, request):
    _assert_observation_mutation_allowed(runtime, "select_calibration_lamp")
    validate_required_params(request, {"lamp", "enabled"})
    lamps = _require_lamps(runtime)
    snapshot = lamps.select_lamp(
        str(request.params["lamp"]),
        enable=bool(request.params["enabled"]),
    )
    return snapshot.to_dict()


def _handle_observation_arm(runtime: Runtime, request):
    validate_required_params(request, {"exp_time_s", "frame_type"})

    detector = _require_detector(runtime)

    instrument_snapshot = None
    if runtime.slit is not None:
        instrument_snapshot = runtime.slit.get_snapshot().to_state_fragment()

    calibration_snapshot = None
    if runtime.lamps is not None:
        calibration_snapshot = runtime.lamps.get_snapshot().to_dict()
    if runtime.camera_config is not None and runtime.camera_config.calibration_control == "manual":
        calibration_snapshot = {"control_mode": "manual", "physical_state_verified": False,
                                "frame_type": str(request.params["frame_type"])}

    detector_config = runtime.get_detector_config_dict()
    preset_apply = _latest_successful_preset_apply(runtime)
    setup_context = request.params.get("setup_context")
    data_preview = request.params.get("data_preview")

    snapshot = detector.arm(
        exp_time_s=float(request.params["exp_time_s"]),
        frame_type=str(request.params["frame_type"]),
        save_requested=bool(request.params.get("save_requested", False)),
        operator_note=request.params.get("operator_note"),
        instrument_snapshot=instrument_snapshot,
        calibration_snapshot=calibration_snapshot,
        detector_config=detector_config,
        preset_apply=preset_apply,
        setup_context=setup_context,
        data_preview=data_preview,
    )
    return snapshot.to_dict()


def _handle_observation_start(runtime: Runtime, request):
    detector = _require_detector(runtime)
    snapshot = detector.start()
    return snapshot.to_dict()


def _handle_observation_finish(runtime: Runtime, request):
    detector = _require_detector(runtime)
    snapshot = detector.finish_normal()
    return snapshot.to_dict()


def _handle_observation_stop_readout(runtime: Runtime, request):
    detector = _require_detector(runtime)
    snapshot = detector.stop_and_readout()
    return snapshot.to_dict()


def _handle_observation_abort_discard(runtime: Runtime, request):
    detector = _require_detector(runtime)
    snapshot = detector.abort_discard()
    return snapshot.to_dict()


def _handle_observation_save_last_frame(runtime: Runtime, request):
    detector = _require_detector(runtime)
    return detector.save_last_frame()


def get_dispatcher(runtime: RuntimeDep) -> CommandDispatcher:
    dispatcher = CommandDispatcher(runtime)
    dispatcher.register_handler("slit", "set_width", _handle_slit_set_width)
    dispatcher.register_handler("slit", "set_angle", _handle_slit_set_angle)
    dispatcher.register_handler("lamps", "set_legacy_on", _handle_lamp_legacy_set)
    dispatcher.register_handler("lamps", "set_mode", _handle_calibration_set_mode)
    dispatcher.register_handler("lamps", "select_lamp", _handle_calibration_select_lamp)
    dispatcher.register_handler("detector", "arm_exposure", _handle_observation_arm)
    dispatcher.register_handler("detector", "start_exposure", _handle_observation_start)
    dispatcher.register_handler("detector", "finish_exposure", _handle_observation_finish)
    dispatcher.register_handler("detector", "stop_readout", _handle_observation_stop_readout)
    dispatcher.register_handler("detector", "abort_discard", _handle_observation_abort_discard)
    dispatcher.register_handler("detector", "save_last_frame", _handle_observation_save_last_frame)
    return dispatcher


DispatcherDep = Annotated[CommandDispatcher, Depends(get_dispatcher)]
HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]
ManagementServiceDep = Annotated[ManagementService, Depends(get_management_service)]
ObservatoryContextServiceDep = Annotated[
    ObservatoryContextService,
    Depends(get_observatory_context_service),
]
SetupContextServiceDep = Annotated[SetupContextService, Depends(get_setup_context_service)]
ObservationSequenceStoreDep = Annotated[
    ObservationSequenceStore,
    Depends(get_observation_sequence_store),
]

def get_observation_preview_service(
    runtime: RuntimeDep,
    setup_context_service: SetupContextServiceDep,
) -> ObservationPreviewService:
    return ObservationPreviewService(runtime, setup_context_service)


ObservationPreviewServiceDep = Annotated[
    ObservationPreviewService,
    Depends(get_observation_preview_service),
]



def get_observation_service(
    runtime: RuntimeDep,
    dispatcher: DispatcherDep,
    setup_context_service: SetupContextServiceDep,
) -> ObservationService:
    return ObservationService(runtime, dispatcher, setup_context_service)


ObservationServiceDep = Annotated[ObservationService, Depends(get_observation_service)]


def get_observation_sequence_service(
    runtime: RuntimeDep,
    observation_service: ObservationServiceDep,
    observation_preview_service: ObservationPreviewServiceDep,
    setup_context_service: SetupContextServiceDep,
    sequence_store: ObservationSequenceStoreDep,
) -> ObservationSequenceService:
    return ObservationSequenceService(
        runtime,
        observation_service,
        observation_preview_service,
        setup_context_service,
        sequence_store,
    )


ObservationSequenceServiceDep = Annotated[
    ObservationSequenceService,
    Depends(get_observation_sequence_service),
]
