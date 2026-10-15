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


def test_lamps_legacy_on_off_flow():
    runtime = RuntimeAssembler().build()

    on_snapshot = runtime.lamps.set_legacy_on(True)
    assert on_snapshot.mode.value == "calibration"
    assert on_snapshot.active_lamp.value == "flat"
    assert on_snapshot.lamp_enabled is True
    assert on_snapshot.mirror_inserted is True

    off_snapshot = runtime.lamps.set_legacy_on(False)
    assert off_snapshot.mode.value == "science"
    assert off_snapshot.active_lamp is None
    assert off_snapshot.lamp_enabled is False
    assert off_snapshot.mirror_inserted is False

def test_lamps_explicit_mode_and_lamp_flow():
    runtime = RuntimeAssembler().build()

    snap1 = runtime.lamps.set_mode("calibration")
    assert snap1.mode.value == "calibration"
    assert snap1.mirror_inserted is True
    assert snap1.lamp_enabled is False

    snap2 = runtime.lamps.select_lamp("arc_hgar", enable=True)
    assert snap2.mode.value == "calibration"
    assert snap2.active_lamp.value == "arc_hgar"
    assert snap2.lamp_enabled is True
    assert snap2.mirror_inserted is True

    snap3 = runtime.lamps.set_mode("science")
    assert snap3.mode.value == "science"
    assert snap3.active_lamp is None
    assert snap3.lamp_enabled is False
    assert snap3.mirror_inserted is False
