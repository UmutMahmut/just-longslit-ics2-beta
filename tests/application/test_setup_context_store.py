import json

import pytest

from justls.ics.application.services.setup_context_store import (
    InMemorySetupContextStore,
    JsonSetupContextStore,
)
from justls.ics.domain.setup import SessionDataContext


def test_in_memory_setup_context_store_round_trips_context() -> None:
    store = InMemorySetupContextStore()

    saved = store.save(
        SessionDataContext(
            observers="Observer",
            project_id="P-001",
            root_name="science",
            date_prefix="20260527",
            next_frame_index=9,
        )
    )

    loaded = store.load()

    assert saved.to_persisted_dict() == loaded.to_persisted_dict()
    assert loaded.observers == "Observer"
    assert loaded.project_id == "P-001"
    assert loaded.next_frame_token() == "20260527-0009"


def test_in_memory_setup_context_store_does_not_expose_internal_mutation() -> None:
    store = InMemorySetupContextStore(
        SessionDataContext(root_name="science", date_prefix="20260527")
    )

    loaded = store.load()
    loaded.root_name = "mutated"

    assert store.load().root_name == "science"


def test_json_setup_context_store_returns_default_when_file_is_missing(tmp_path) -> None:
    store = JsonSetupContextStore(tmp_path / "setup_context.json")

    context = store.load()

    assert context.root_name == "justls"
    assert context.date_prefix == "AUTO"
    assert context.next_frame_index == 1


def test_json_setup_context_store_round_trips_context(tmp_path) -> None:
    path = tmp_path / "setup" / "setup_context.json"
    store = JsonSetupContextStore(path)

    saved = store.save(
        SessionDataContext(
            observers="Observer",
            project_id="P-001",
            pi_name="PI",
            support_operator="Support",
            root_name="science",
            date_prefix="20260527",
            comment="night setup",
            next_frame_index=12,
            data_directory="/data/just",
        )
    )

    loaded = store.load()

    assert saved.to_persisted_dict() == loaded.to_persisted_dict()
    assert loaded.observers == "Observer"
    assert loaded.project_id == "P-001"
    assert loaded.pi_name == "PI"
    assert loaded.support_operator == "Support"
    assert loaded.root_name == "science"
    assert loaded.date_prefix == "20260527"
    assert loaded.comment == "night setup"
    assert loaded.next_frame_index == 12
    assert loaded.data_directory == "/data/just"

    raw_payload = json.loads(path.read_text(encoding="utf-8"))
    assert raw_payload == loaded.to_persisted_dict()
    assert "next_frame_token" not in raw_payload
    assert "file_stem" not in raw_payload
    assert "fits_filename" not in raw_payload


def test_json_setup_context_store_rejects_non_object_payload(tmp_path) -> None:
    path = tmp_path / "setup_context.json"
    path.write_text("[]", encoding="utf-8")

    store = JsonSetupContextStore(path)

    with pytest.raises(ValueError, match="must contain an object"):
        store.load()


def test_json_setup_context_store_rejects_invalid_json(tmp_path) -> None:
    path = tmp_path / "setup_context.json"
    path.write_text("{not valid json", encoding="utf-8")

    store = JsonSetupContextStore(path)

    with pytest.raises(ValueError, match="Invalid setup context JSON"):
        store.load()