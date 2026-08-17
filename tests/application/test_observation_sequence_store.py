from __future__ import annotations

import json

import pytest

from justls.ics.application.services.observation_sequence_store import (
    InMemoryObservationSequenceStore,
    JsonObservationSequenceStore,
)
from justls.ics.domain.observation.models import ExposureSpec
from justls.ics.domain.observation.sequence import (
    ObservationPlan,
    SequenceExecutionSnapshot,
    SequenceFrameReservation,
)


def _snapshot() -> SequenceExecutionSnapshot:
    return SequenceExecutionSnapshot(
        plan=ObservationPlan(
            plan_id="plan-store",
            exposures=[ExposureSpec(frame_type="science", exp_time_s=5)],
        ),
        message="store test",
    )


def test_in_memory_sequence_store_returns_independent_snapshots() -> None:
    store = InMemoryObservationSequenceStore()
    original = _snapshot()

    store.save(original)
    loaded = store.load()
    assert loaded is not None
    loaded.message = "mutated"

    assert store.load().message == "store test"


def test_json_sequence_store_round_trips_versioned_snapshot(tmp_path) -> None:
    path = tmp_path / "state" / "sequence.json"
    store = JsonObservationSequenceStore(path)
    snapshot = _snapshot()
    snapshot.last_persisted_at_utc = "2026-08-17T00:00:00+00:00"

    store.save(snapshot)
    loaded = store.load()

    assert loaded is not None
    assert loaded.plan.plan_id == "plan-store"
    assert loaded.schema_version == 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["sequence"]["plan"]["plan_id"] == "plan-store"
    assert "total_steps" not in payload["sequence"]


def test_json_sequence_store_returns_none_when_missing(tmp_path) -> None:
    assert JsonObservationSequenceStore(tmp_path / "missing.json").load() is None


def test_json_sequence_store_migrates_pre_save_policy_reservations(tmp_path) -> None:
    path = tmp_path / "sequence.json"
    store = JsonObservationSequenceStore(path)
    snapshot = _snapshot()
    snapshot.frame_reservation = SequenceFrameReservation(
        start_index=3,
        count=1,
        end_index_exclusive=4,
        step_data_previews=[{"file_stem": "science_20260817_0003"}],
    )
    store.save(snapshot)
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["sequence"]["plan"]["save_requested"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = store.load()

    assert loaded.plan.save_requested is True


@pytest.mark.parametrize(
    "payload, message",
    [
        ("{bad json", "Invalid observation sequence JSON"),
        ("[]", "must contain an object"),
        ('{"schema_version": 99, "sequence": {}}', "Unsupported"),
        ('{"schema_version": 1}', "sequence object"),
    ],
)
def test_json_sequence_store_rejects_unsafe_payloads(
    tmp_path,
    payload: str,
    message: str,
) -> None:
    path = tmp_path / "sequence.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        JsonObservationSequenceStore(path).load()
