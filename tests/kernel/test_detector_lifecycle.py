from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from justls.ics.application.dispatcher import CommandDispatcher, validate_required_params
from justls.ics.application.services.health_service import HealthService
from justls.ics.application.services.management_service import ManagementService
from justls.ics.application.services.observation_service import ObservationService
from justls.ics.app.main import app
from justls.ics.application.usecases.presets import (
    build_preset_config,
    build_preset_plan,
    list_presets,
)
from justls.ics.domain.detector.config import DetectorConfig
from justls.ics.kernel.errors import (
    ErrorCode,
    InvalidParamError,
    InvalidStateError,
    UnsupportedError,
)
from justls.ics.kernel.jobs import CommandRequest, JobTracker
from justls.ics.kernel.runtime import RuntimeAssembler, RuntimeConfig, reset_runtime
from justls.ics.kernel.states import (
    CommandSource,
    ControlState,
    ExposureState,
    RunMode,
    build_initial_state,
)


@pytest.fixture(autouse=True)
def _reset_runtime_singleton():
    reset_runtime()
    yield
    reset_runtime()


def test_detector_initial_snapshot():
    runtime = RuntimeAssembler().build()
    snap = runtime.detector.get_snapshot()

    assert snap.state == ExposureState.READY_TO_ARM
    assert snap.armed_exposure is None
    assert snap.last_exposure is None
    assert snap.observation_meta is None
    assert snap.latest_exposure_record is None

def test_detector_arm_creates_observation_meta():
    runtime = RuntimeAssembler().build()

    armed = runtime.detector.arm(
        exp_time_s=30.0,
        frame_type="science",
        operator_note="meta-test",
        instrument_snapshot={"slit_width_um": 120.0, "slit_angle_deg": 0.0},
        calibration_snapshot={"mode": "science", "active_lamp": None, "lamp_enabled": False, "mirror_inserted": False},
        detector_config=runtime.get_detector_config_dict(),
    )

    assert armed.state == ExposureState.ARMED
    assert armed.armed_exposure is not None
    assert armed.observation_meta is not None
    assert armed.observation_meta["frame_type"] == "science"
    assert armed.observation_meta["operator_note"] == "meta-test"
    assert armed.observation_meta["instrument_snapshot"]["slit_width_um"] == 120.0
    assert (
        armed.observation_meta["detector_config"]["profile_name"]
        == "campus-beta-shared-camera"
    )

def test_detector_finish_normal_flow():
    runtime = RuntimeAssembler().build()

    runtime.detector.arm(
        exp_time_s=30.0,
        frame_type="science",
        operator_note="finish-case",
        instrument_snapshot={"slit_width_um": 120.0, "slit_angle_deg": 0.0},
        calibration_snapshot={"mode": "science", "active_lamp": None, "lamp_enabled": False, "mirror_inserted": False},
        detector_config=runtime.get_detector_config_dict(),
    )

    exposing = runtime.detector.start()
    assert exposing.state == ExposureState.EXPOSING
    assert exposing.observation_meta["state"] == "exposing"
    assert exposing.camera_status["state"] == "exposing"
    assert (
        exposing.camera_status["active_exposure"]["exp_id"]
        == exposing.armed_exposure["exp_id"]
    )

    completed = runtime.detector.finish_normal()
    assert completed.state == ExposureState.COMPLETED
    assert completed.armed_exposure is None
    assert completed.last_exposure is not None
    assert completed.last_exposure["frame_type"] == "science"
    assert completed.last_exposure["result"] == "completed"
    assert completed.last_exposure["kept"] is True
    assert completed.last_exposure["early_stop"] is False
    assert completed.last_exposure["discarded"] is False
    assert completed.observation_meta is not None
    assert completed.observation_meta["state"] == "completed"
    assert len(completed.observation_meta["frame_results"]) == 1
    assert completed.observation_meta["frame_results"][0]["kept"] is True
    assert completed.observation_meta["frame_results"][0]["early_stop"] is False
    assert completed.latest_exposure_record is not None
    assert completed.latest_exposure_record["state"] == "completed"
    assert completed.latest_exposure_record["data_product_state"] == "available"
    assert completed.latest_exposure_record["primary_data_product"]["exists"] is True
    assert completed.latest_exposure_record["quicklook"]["exists"] is True
    assert completed.latest_exposure_record["logical_channels"] == ["B", "G", "R"]
    assert (
        completed.latest_exposure_record["physical_camera_id"]
        == "science-camera-01"
    )
    assert completed.camera_status["state"] == "idle"
    assert completed.observation_meta["exposure_record"]["record_id"] == completed.latest_exposure_record["record_id"]

def test_detector_stop_readout_flow():
    runtime = RuntimeAssembler().build()

    runtime.detector.arm(
        exp_time_s=12.0,
        frame_type="flat",
        operator_note="early-stop",
        instrument_snapshot={"slit_width_um": 80.0, "slit_angle_deg": 2.0},
        calibration_snapshot={"mode": "science", "active_lamp": None, "lamp_enabled": False, "mirror_inserted": False},
        detector_config=runtime.get_detector_config_dict(),
    )
    runtime.detector.start()

    completed = runtime.detector.stop_and_readout()
    assert completed.state == ExposureState.COMPLETED
    assert completed.last_exposure is not None
    assert completed.last_exposure["kept"] is True
    assert completed.last_exposure["early_stop"] is True
    assert completed.last_exposure["discarded"] is False
    assert completed.observation_meta["state"] == "completed"
    assert completed.observation_meta["frame_results"][0]["early_stop"] is True
    assert completed.latest_exposure_record["state"] == "completed"
    assert "early_stop" in completed.latest_exposure_record["quality_flags"]

def test_detector_abort_discard_flow():
    runtime = RuntimeAssembler().build()

    runtime.detector.arm(
        exp_time_s=10.0,
        frame_type="flat",
        operator_note="discard-case",
        instrument_snapshot={"slit_width_um": 80.0, "slit_angle_deg": 2.0},
        calibration_snapshot={"mode": "calibration", "active_lamp": "flat", "lamp_enabled": True, "mirror_inserted": True},
        detector_config=runtime.get_detector_config_dict(),
    )
    discarded = runtime.detector.abort_discard()

    assert discarded.state == ExposureState.DISCARDED
    assert discarded.armed_exposure is None
    assert discarded.last_exposure is not None
    assert discarded.last_exposure["frame_type"] == "flat"
    assert discarded.last_exposure["result"] == "discarded"
    assert discarded.last_exposure["kept"] is False
    assert discarded.last_exposure["early_stop"] is False
    assert discarded.last_exposure["discarded"] is True
    assert discarded.observation_meta["state"] == "discarded"
    assert discarded.observation_meta["frame_results"][0]["discarded"] is True
    assert discarded.latest_exposure_record["state"] == "discarded"
    assert discarded.latest_exposure_record["data_product_state"] == "not_created"
    assert discarded.latest_exposure_record["primary_data_product"]["exists"] is False

def test_detector_invalid_start_before_arm():
    runtime = RuntimeAssembler().build()

    with pytest.raises(InvalidStateError):
        runtime.detector.start()

def test_detector_invalid_finish_before_start():
    runtime = RuntimeAssembler().build()

    runtime.detector.arm(
        exp_time_s=5.0,
        frame_type="science",
        operator_note=None,
        instrument_snapshot=None,
        calibration_snapshot=None,
        detector_config=runtime.get_detector_config_dict(),
    )
    with pytest.raises(InvalidStateError):
        runtime.detector.finish_normal()

def test_detector_invalid_stop_before_start():
    runtime = RuntimeAssembler().build()

    runtime.detector.arm(
        exp_time_s=5.0,
        frame_type="science",
        operator_note=None,
        instrument_snapshot=None,
        calibration_snapshot=None,
        detector_config=runtime.get_detector_config_dict(),
    )
    with pytest.raises(InvalidStateError):
        runtime.detector.stop_and_readout()

def test_detector_invalid_abort_before_arm():
    runtime = RuntimeAssembler().build()

    with pytest.raises(InvalidStateError):
        runtime.detector.abort_discard()
