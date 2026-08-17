from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from justls.ics.kernel.runtime import RuntimeAssembler


def _path_from_file_uri(uri: str) -> Path:
    parsed = urlparse(uri)
    assert parsed.scheme == "file"
    return Path(unquote(parsed.path.lstrip("/")))


def test_completed_exposure_writes_valid_fits_blocks_and_quicklook() -> None:
    runtime = RuntimeAssembler().build()
    runtime.detector.arm(
        exp_time_s=2.5,
        frame_type="science",
        save_requested=True,
        detector_config=runtime.get_detector_config_dict(),
    )
    runtime.detector.start()
    completed = runtime.detector.finish_normal()

    record = completed.latest_exposure_record
    fits_path = _path_from_file_uri(record["primary_data_product"]["uri"])
    quicklook_path = _path_from_file_uri(record["quicklook"]["uri"])

    assert fits_path.exists()
    assert fits_path.read_bytes().startswith(b"SIMPLE  =")
    assert fits_path.stat().st_size % 2880 == 0
    assert quicklook_path.exists()
    assert quicklook_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert len(record["primary_data_product"]["checksum"]) == 64


def test_completed_unsaved_exposure_stays_in_memory_without_files() -> None:
    runtime = RuntimeAssembler().build()
    data_root = Path(runtime.data_root)
    before = set(data_root.rglob("*")) if data_root.exists() else set()
    runtime.detector.arm(
        exp_time_s=0.1,
        frame_type="test",
        save_requested=False,
        detector_config=runtime.get_detector_config_dict(),
    )
    runtime.detector.start()
    completed = runtime.detector.finish_normal()

    record = completed.latest_exposure_record
    assert record["save_requested"] is False
    assert record["data_product_state"] == "not_requested"
    assert record["primary_data_product"]["uri"] is None
    assert record["quicklook"] is None
    assert runtime.detector.adapter.get_latest_preview()[0].startswith(b"\x89PNG")
    after = set(data_root.rglob("*")) if data_root.exists() else set()
    assert after == before


def test_abort_after_start_clears_hardware_exposure_without_product() -> None:
    runtime = RuntimeAssembler().build()
    runtime.detector.arm(
        exp_time_s=10.0,
        frame_type="test",
        detector_config=runtime.get_detector_config_dict(),
    )
    runtime.detector.start()
    discarded = runtime.detector.abort_discard()

    assert discarded.camera_status["state"] == "idle"
    assert discarded.latest_exposure_record["data_product_state"] == "not_created"
    assert discarded.latest_exposure_record["primary_data_product"]["exists"] is False
