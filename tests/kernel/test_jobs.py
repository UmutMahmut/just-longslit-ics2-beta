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


def test_job_tracker_success_flow():
    tracker = JobTracker()

    req = CommandRequest.create(
        subsystem="slit",
        action="set_width",
        params={"width_um": 120.0},
        source=CommandSource.UI,
    )

    job = tracker.create_job(req, state_before="idle")
    tracker.mark_running(job.job_id)
    tracker.mark_succeeded(
        job.job_id,
        result={"width_um": 120.0},
        state_after="idle",
    )

    latest = tracker.latest_job()
    assert latest is not None
    assert latest.status.value == "succeeded"
    assert latest.result["width_um"] == 120.0
    assert latest.state_before == "idle"
    assert latest.state_after == "idle"
