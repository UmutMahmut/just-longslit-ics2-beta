from __future__ import annotations

from justls.ics.domain.observation.models import (
    DataProductState,
    ExposureRecord,
    FrameResult,
    ObservationMeta,
)


def test_completed_exposure_record_separates_lifecycle_from_data_product() -> None:
    meta = ObservationMeta.create(
        frame_type="science",
        exp_time_s=30.0,
        detector_config={"profile_name": "default"},
        setup_context={"file_stem": "just_20260702_0001"},
    )
    meta.mark_exposing()
    meta.mark_completed(finished_at_utc="2026-07-02T00:00:03+00:00")

    frame_result = FrameResult(
        frame_token="frame-token",
        file_uri=None,
        kept=True,
        early_stop=False,
        discarded=False,
        checksum=None,
        started_at_utc="2026-07-02T00:00:01+00:00",
        finished_at_utc="2026-07-02T00:00:03+00:00",
        result="completed",
    )

    record = ExposureRecord.from_frame_result(
        observation_meta=meta,
        frame_result=frame_result,
    )

    assert record.state == "completed"
    assert record.data_product_state == DataProductState.SIMULATED_REFERENCE
    assert record.primary_data_product is not None
    assert record.primary_data_product.exists is False
    assert record.primary_data_product.simulated is True
    assert record.primary_data_product.uri.startswith("sim://justls/")
    assert "no FITS file" in record.primary_data_product.message
    assert "no_fits_writer" in record.model_dump(mode="json")["quality_flags"]


def test_discarded_exposure_record_has_no_data_product() -> None:
    meta = ObservationMeta.create(frame_type="flat", exp_time_s=10.0)
    meta.mark_discarded(finished_at_utc="2026-07-02T00:00:02+00:00")

    frame_result = FrameResult(
        frame_token=None,
        file_uri=None,
        kept=False,
        early_stop=False,
        discarded=True,
        checksum=None,
        started_at_utc=None,
        finished_at_utc="2026-07-02T00:00:02+00:00",
        result="discarded",
    )

    record = ExposureRecord.from_frame_result(
        observation_meta=meta,
        frame_result=frame_result,
    )

    assert record.state == "discarded"
    assert record.data_product_state == DataProductState.NOT_CREATED
    assert record.primary_data_product is not None
    assert record.primary_data_product.exists is False
    assert record.primary_data_product.uri is None
    assert record.quicklook is None
    assert "discarded" in record.model_dump(mode="json")["quality_flags"]


def test_available_local_fits_does_not_report_missing_writer() -> None:
    meta = ObservationMeta.create(
        frame_type="science",
        exp_time_s=5,
        data_preview={"file_stem": "just_20260812_0001"},
    )
    meta.mark_exposing()
    meta.mark_completed()
    frame_result = FrameResult(
        frame_token="frame-token",
        file_uri="file:///tmp/frame.fits",
        quicklook_uri="file:///tmp/frame.png",
        kept=True,
        early_stop=False,
        discarded=False,
        checksum="abc123",
        started_at_utc=meta.started_at_utc,
        finished_at_utc=meta.finished_at_utc,
        result="completed",
        exists=True,
        simulated=True,
    )

    record = ExposureRecord.from_frame_result(
        observation_meta=meta,
        frame_result=frame_result,
    )

    assert record.data_product_state == DataProductState.AVAILABLE
    assert record.fits_header.setup_file_stem == "just_20260812_0001"
    assert "simulated" in record.model_dump(mode="json")["quality_flags"]
    assert "no_fits_writer" not in record.model_dump(mode="json")["quality_flags"]
