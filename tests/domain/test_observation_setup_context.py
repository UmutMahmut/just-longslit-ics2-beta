from justls.ics.adapters.detector.adapter import SimDetectorAdapter
from justls.ics.domain.detector.subsystem import DetectorSubsystem
from justls.ics.domain.observation.models import ObservationMeta
from justls.ics.drivers.sim.detector_driver import SimDetectorDriver


def test_observation_meta_serializes_setup_context_and_data_preview() -> None:
    setup_context = {
        "observers": "Observer",
        "project_id": "P-001",
        "root_name": "science",
        "date_prefix": "20260527",
        "next_frame_index": 5,
        "data_directory": "/data/just",
    }
    data_preview = {
        "next_frame_token": "20260527-0005",
        "file_stem": "science_20260527_0005",
        "fits_filename": "science_20260527_0005.fits",
        "data_directory": "/data/just",
    }

    meta = ObservationMeta.create(
        frame_type="science",
        exp_time_s=30.0,
        setup_context=setup_context,
        data_preview=data_preview,
    )

    payload = meta.to_dict()

    assert payload["setup_context"] == setup_context
    assert payload["data_preview"] == data_preview


def test_detector_arm_preserves_setup_context_in_observation_meta() -> None:
    detector = DetectorSubsystem(SimDetectorAdapter(SimDetectorDriver()))
    setup_context = {
        "observers": "Observer",
        "project_id": "P-001",
        "root_name": "science",
        "date_prefix": "20260527",
        "next_frame_index": 5,
        "data_directory": "/data/just",
    }
    data_preview = {
        "next_frame_token": "20260527-0005",
        "file_stem": "science_20260527_0005",
        "fits_filename": "science_20260527_0005.fits",
        "data_directory": "/data/just",
    }

    snapshot = detector.arm(
        exp_time_s=30.0,
        frame_type="science",
        setup_context=setup_context,
        data_preview=data_preview,
    )

    payload = snapshot.to_dict()
    meta = payload["observation_meta"]

    assert meta["setup_context"] == setup_context
    assert meta["data_preview"] == data_preview
    assert meta["frame_results"] == []