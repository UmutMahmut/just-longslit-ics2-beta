from __future__ import annotations

import pytest

from justls.ics.application.services.observation_service import ObservationService
from justls.ics.kernel.errors import InterlockBlockedError
from justls.ics.kernel.runtime import RuntimeAssembler


class FailingDispatcher:
    def dispatch(self, request):  # pragma: no cover - should not be reached
        raise AssertionError("blocked arm gate must not dispatch detector.arm_exposure")


def test_observation_service_arm_gate_blocks_calibration_mismatch_before_dispatch() -> None:
    runtime = RuntimeAssembler().build()
    runtime.lamps.select_lamp("flat", enable=True)

    service = ObservationService(runtime, FailingDispatcher())

    with pytest.raises(InterlockBlockedError) as exc_info:
        service.arm(exp_time_s=30.0, frame_type="science")

    error = exc_info.value
    assert error.code.value == "interlock_blocked"
    assert error.info.subsystem == "detector"

    details = error.info.details
    assert details["preview"]["blocked"] is True
    assert details["preview"]["single_exposure_compatible"] is False
    assert details["blocked_components"] == ["calibration"]
    assert details["validation_issue_codes"] == ["science_calibration_not_ready"]


def test_observation_service_arm_gate_blocks_busy_detector_before_dispatch() -> None:
    runtime = RuntimeAssembler().build()
    runtime.detector.arm(exp_time_s=5.0, frame_type="science")

    service = ObservationService(runtime, FailingDispatcher())

    with pytest.raises(InterlockBlockedError) as exc_info:
        service.arm(exp_time_s=30.0, frame_type="science")

    details = exc_info.value.info.details
    assert details["preview"]["blocked"] is True
    assert details["preview"]["single_exposure_compatible"] is False
    assert details["preview"]["readiness"]["detector"]["state"] == "blocked"
    assert details["blocked_components"] == ["detector"]
    assert details["validation_issue_codes"] == []
