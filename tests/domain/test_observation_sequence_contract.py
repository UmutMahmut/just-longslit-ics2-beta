from __future__ import annotations

import pytest
from pydantic import ValidationError

from justls.ics.domain.observation.models import ExposureSpec
from justls.ics.domain.observation.sequence import (
    ObservationPlan,
    SequenceExecutionSnapshot,
    SequenceExecutionState,
)


def test_observation_plan_accepts_multiple_exposures() -> None:
    plan = ObservationPlan(
        plan_id="plan-contract",
        target_name="Vega",
        exposures=[
            ExposureSpec(frame_type="science", exp_time_s=10, label="science-1"),
            ExposureSpec(frame_type="test", exp_time_s=2, label="focus-check"),
        ],
    )

    assert plan.plan_id == "plan-contract"
    assert len(plan.exposures) == 2
    assert plan.exposures[1].label == "focus-check"


def test_observation_plan_caps_initial_sequence_length() -> None:
    with pytest.raises(ValidationError):
        ObservationPlan(
            exposures=[
                ExposureSpec(frame_type="science", exp_time_s=1)
                for _ in range(101)
            ]
        )


def test_sequence_snapshot_exposes_progress_without_mutating_plan() -> None:
    snapshot = SequenceExecutionSnapshot(
        plan=ObservationPlan(
            exposures=[
                ExposureSpec(frame_type="science", exp_time_s=5),
                ExposureSpec(frame_type="science", exp_time_s=6),
            ]
        )
    )

    assert snapshot.state == SequenceExecutionState.LOADED
    assert snapshot.total_steps == 2
    assert snapshot.completed_steps == 0
    assert snapshot.current_exposure().exp_time_s == 5
    assert snapshot.to_status_dict()["current_exposure"]["exp_time_s"] == 5


def test_sequence_snapshot_rejects_unsafe_durable_indices() -> None:
    plan = ObservationPlan(
        plan_id="plan-invalid-index",
        exposures=[ExposureSpec(frame_type="science", exp_time_s=1)],
    )

    with pytest.raises(ValueError, match="current_index"):
        SequenceExecutionSnapshot(plan=plan, current_index=2)


def test_recovery_required_snapshot_requires_recovery_details() -> None:
    plan = ObservationPlan(
        plan_id="plan-invalid-recovery",
        exposures=[ExposureSpec(frame_type="science", exp_time_s=1)],
    )

    with pytest.raises(ValueError, match="recovery details"):
        SequenceExecutionSnapshot(
            plan=plan,
            state=SequenceExecutionState.RECOVERY_REQUIRED,
        )
