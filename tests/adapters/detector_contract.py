from __future__ import annotations

from justls.ics.adapters.detector.adapter import BaseDetectorAdapter
from justls.ics.domain.detector.frame import DetectorFrameMetadata


def assert_detector_exposure_contract(adapter: BaseDetectorAdapter) -> None:
    started = adapter.start_exposure(
        obs_id="obs-contract",
        exp_id="exp-contract",
        exp_time_s=12.5,
        frame_type="science",
        save_requested=False,
    )

    assert started["obs_id"] == "obs-contract"
    assert started["exp_id"] == "exp-contract"
    assert started["frame_type"] == "science"
    assert started["exp_time_s"] == 12.5
    assert started["save_requested"] is False
    assert started["frame_token"].startswith("frame-")
    assert started["started_at"]
    DetectorFrameMetadata.model_validate(started["detector_metadata"])
    assert adapter.get_status()["state"] == "exposing"

    completed = adapter.finish_exposure()

    assert completed["result"] == "completed"
    assert completed["requested_exp_time_s"] == 12.5
    assert completed["actual_exp_time_s"] >= 0
    assert completed["finished_at"]
    assert completed["physical_camera_id"]
    assert completed["simulated"] is True
    DetectorFrameMetadata.model_validate(completed["detector_metadata"])
    assert adapter.get_status()["state"] == "idle"


def assert_detector_abort_contract(adapter: BaseDetectorAdapter) -> None:
    adapter.start_exposure(
        obs_id="obs-abort-contract",
        exp_id="exp-abort-contract",
        exp_time_s=60.0,
        frame_type="dark",
        save_requested=False,
    )

    result = adapter.abort_exposure()

    assert result["result"] == "aborted"
    assert result["had_active_exposure"] is True
    assert result["finished_at"]
    assert adapter.get_status()["state"] == "idle"
