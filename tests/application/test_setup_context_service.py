from datetime import date

import pytest

from justls.ics.application.services.setup_context_service import SetupContextService
from justls.ics.application.services.setup_context_store import JsonSetupContextStore
from justls.ics.domain.setup import SessionDataContext


def test_setup_context_service_returns_default_context() -> None:
    service = SetupContextService()

    context = service.get_context()

    assert isinstance(context, SessionDataContext)
    assert context.root_name == "justls"
    assert context.date_prefix == "AUTO"
    assert context.next_frame_index == 1


def test_setup_context_service_returns_derived_payload() -> None:
    service = SetupContextService(
        SessionDataContext(
            observers="Observer",
            project_id="P-001",
            root_name="science",
            date_prefix="AUTO",
            next_frame_index=5,
            data_directory="/data/just",
        )
    )

    payload = service.get_context_payload(date(2026, 5, 27))

    assert payload["observers"] == "Observer"
    assert payload["project_id"] == "P-001"
    assert payload["root_name"] == "science"
    assert payload["date_prefix"] == "AUTO"
    assert payload["next_frame_index"] == 5
    assert payload["data_directory"] == "/data/just"
    assert payload["next_frame_token"] == "20260527-0005"
    assert payload["file_stem"] == "science_20260527_0005"
    assert payload["fits_filename"] == "science_20260527_0005.fits"


def test_setup_context_service_saves_context_through_store(tmp_path) -> None:
    store = JsonSetupContextStore(tmp_path / "setup_context.json")
    service = SetupContextService(store=store)

    service.save_context(
        SessionDataContext(
            observers="Observer",
            project_id="P-001",
            root_name="science",
            date_prefix="20260527",
            next_frame_index=8,
        )
    )

    payload = service.get_context_payload()

    assert payload["observers"] == "Observer"
    assert payload["project_id"] == "P-001"
    assert payload["root_name"] == "science"
    assert payload["next_frame_token"] == "20260527-0008"


def test_setup_context_service_saves_payload_through_store(tmp_path) -> None:
    store = JsonSetupContextStore(tmp_path / "setup_context.json")
    service = SetupContextService(store=store)

    service.save_context_payload(
        {
            "observers": "Observer",
            "project_id": "P-001",
            "root_name": "science",
            "date_prefix": "20260527",
            "next_frame_index": 11,
        }
    )

    payload = service.get_context_payload()

    assert payload["observers"] == "Observer"
    assert payload["project_id"] == "P-001"
    assert payload["root_name"] == "science"
    assert payload["next_frame_token"] == "20260527-0011"


def test_setup_context_service_reload_reads_store(tmp_path) -> None:
    path = tmp_path / "setup_context.json"
    first_service = SetupContextService(store=JsonSetupContextStore(path))
    second_service = SetupContextService(store=JsonSetupContextStore(path))

    first_service.save_context_payload(
        {
            "observers": "Observer",
            "project_id": "P-001",
            "root_name": "science",
            "date_prefix": "20260527",
            "next_frame_index": 13,
        }
    )

    reloaded = second_service.reload_context()

    assert reloaded.observers == "Observer"
    assert reloaded.project_id == "P-001"
    assert reloaded.next_frame_token() == "20260527-0013"


def test_setup_context_service_rejects_context_and_store_together(tmp_path) -> None:
    store = JsonSetupContextStore(tmp_path / "setup_context.json")

    with pytest.raises(ValueError, match="either context or store"):
        SetupContextService(SessionDataContext(), store=store)