from datetime import date

import pytest

from justls.ics.domain.setup import SessionDataContext


def test_default_context_has_predictable_preview() -> None:
    context = SessionDataContext()

    assert context.root_name == "justls"
    assert context.date_prefix == "AUTO"
    assert context.next_frame_index == 1
    assert context.next_frame_token(date(2026, 5, 27)) == "20260527-0001"
    assert context.file_stem_preview(date(2026, 5, 27)) == "justls_20260527_0001"
    assert context.fits_filename_preview(date(2026, 5, 27)) == "justls_20260527_0001.fits"


def test_context_trims_text_fields_and_serializes_source_fields() -> None:
    context = SessionDataContext(
        observers="  Alice, Bob  ",
        project_id="  JUST-P001  ",
        pi_name="  Dr. Pi  ",
        support_operator="  Night Support  ",
        root_name=" science_run ",
        date_prefix=" auto ",
        comment="  first night  ",
        next_frame_index="12",
        data_directory="  D:/data/JUST  ",
    )

    assert context.observers == "Alice, Bob"
    assert context.project_id == "JUST-P001"
    assert context.pi_name == "Dr. Pi"
    assert context.support_operator == "Night Support"
    assert context.root_name == "science_run"
    assert context.date_prefix == "AUTO"
    assert context.comment == "first night"
    assert context.next_frame_index == 12
    assert context.data_directory == "D:/data/JUST"

    assert context.to_persisted_dict() == {
        "observers": "Alice, Bob",
        "project_id": "JUST-P001",
        "pi_name": "Dr. Pi",
        "support_operator": "Night Support",
        "root_name": "science_run",
        "date_prefix": "AUTO",
        "comment": "first night",
        "next_frame_index": 12,
        "data_directory": "D:/data/JUST",
    }


def test_explicit_date_prefix_does_not_require_observing_date() -> None:
    context = SessionDataContext(
        root_name="bias",
        date_prefix="20260527",
        next_frame_index=3,
    )

    assert context.next_frame_token() == "20260527-0003"
    assert context.file_stem_preview() == "bias_20260527_0003"
    assert context.fits_filename_preview() == "bias_20260527_0003.fits"


def test_to_dict_includes_persisted_fields_and_derived_preview() -> None:
    context = SessionDataContext(
        observers="Observer",
        project_id="P-001",
        root_name="target",
        date_prefix="AUTO",
        next_frame_index=42,
        data_directory="/data/just",
    )

    payload = context.to_dict(date(2026, 5, 27))

    assert payload["observers"] == "Observer"
    assert payload["project_id"] == "P-001"
    assert payload["root_name"] == "target"
    assert payload["date_prefix"] == "AUTO"
    assert payload["next_frame_index"] == 42
    assert payload["data_directory"] == "/data/just"
    assert payload["next_frame_token"] == "20260527-0042"
    assert payload["file_stem"] == "target_20260527_0042"
    assert payload["fits_filename"] == "target_20260527_0042.fits"


def test_from_dict_ignores_derived_display_fields() -> None:
    context = SessionDataContext.from_dict(
        {
            "observers": "Observer",
            "project_id": "P-001",
            "root_name": "science",
            "date_prefix": "20260527",
            "next_frame_index": 7,
            "next_frame_token": "wrong",
            "file_stem": "wrong",
            "fits_filename": "wrong.fits",
        }
    )

    assert context.observers == "Observer"
    assert context.project_id == "P-001"
    assert context.next_frame_token() == "20260527-0007"
    assert context.file_stem_preview() == "science_20260527_0007"
    assert context.fits_filename_preview() == "science_20260527_0007.fits"


@pytest.mark.parametrize(
    "root_name",
    [
        "",
        "science run",
        "science/run",
        "science\\run",
        ".science",
        "science.run",
    ],
)
def test_invalid_root_name_is_rejected(root_name: str) -> None:
    with pytest.raises(ValueError):
        SessionDataContext(root_name=root_name)

@pytest.mark.parametrize("date_prefix", ["", "2026-05-27", "2026052", "202605270", "night"])
def test_invalid_date_prefix_is_rejected(date_prefix: str) -> None:
    with pytest.raises(ValueError):
        SessionDataContext(date_prefix=date_prefix)


@pytest.mark.parametrize("next_frame_index", [0, -1, "0", "abc", True])
def test_invalid_next_frame_index_is_rejected(next_frame_index: object) -> None:
    with pytest.raises(ValueError):
        SessionDataContext(next_frame_index=next_frame_index)  # type: ignore[arg-type]
