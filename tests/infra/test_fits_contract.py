from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from justls.ics.domain.detector.frame import DetectorFrameMetadata
from justls.ics.infra.data_products import (
    LocalDataProductWriter,
    build_fits_bytes,
    build_science_fits_cards,
)


def _metadata(*, width: int, height: int) -> DetectorFrameMetadata:
    return DetectorFrameMetadata(
        manufacturer="ZWO",
        model="ASI294MC Pro",
        serial="test-serial",
        width=width,
        height=height,
        pixel_format="RAW16",
        sensor_bit_depth=14,
        bayer_pattern="RGGB",
        bin_x=1,
        bin_y=1,
        gain=120,
        offset=30,
        detector_temperature_c=14.1,
        cooler_enabled=True,
        cooler_target_c=15.0,
        cooler_power_pct=18.5,
    )


def _write(
    writer: LocalDataProductWriter,
    image: np.ndarray,
    *,
    frame_type: str = "science",
):
    return writer.write(
        image,
        obs_id="obs-contract",
        exp_id="exp-contract",
        frame_token="frame-contract",
        frame_type=frame_type,
        exp_time_s=10.0,
        actual_exp_time_s=9.875,
        camera_id="science-camera-01",
        logical_channels=("SCI",),
        started_at="2026-08-22T10:55:18.083+00:00",
        finished_at="2026-08-22T10:55:27.958+00:00",
        detector_metadata=_metadata(width=image.shape[1], height=image.shape[0]),
        simulated=False,
    )


def test_unsigned_raw_pixels_round_trip_through_astropy() -> None:
    image = np.array(
        [[0, 1, 32767, 32768], [32769, 65534, 65535, 42]],
        dtype=np.uint16,
    )
    payload = build_fits_bytes(image, {"FRAMETYP": "SCIENCE"})

    with fits.open(io.BytesIO(payload), uint=True) as hdus:
        hdus.verify("exception")
        primary = hdus[0]
        assert primary.header["BITPIX"] == 16
        assert primary.header["BZERO"] == 32768
        assert primary.header["BSCALE"] == 1
        assert primary.data.dtype == np.dtype("uint16")
        np.testing.assert_array_equal(primary.data, image)


@pytest.mark.parametrize(
    "frame_type",
    ["science", "bias", "dark", "flat", "arc", "test"],
)
def test_science_cards_have_stable_frame_timing_and_detector_metadata(
    frame_type: str,
) -> None:
    cards = build_science_fits_cards(
        obs_id="obs-contract",
        exp_id="exp-contract",
        frame_type=frame_type,
        requested_exp_time_s=10.0,
        actual_exp_time_s=9.875,
        camera_id="science-camera-01",
        logical_channels=("SCI",),
        started_at="2026-08-22T10:55:18.083+00:00",
        finished_at="2026-08-22T10:55:27.958+00:00",
        simulated=False,
        detector_metadata=_metadata(width=4, height=2),
    )

    assert cards["FRAMETYP"] == frame_type.upper()
    assert cards["EXPREQ"] == 10.0
    assert cards["EXPTIME"] == 9.875
    assert cards["COLORTYP"] == "RAW16"
    assert cards["BITDEPTH"] == 14
    assert cards["BAYERPAT"] == "RGGB"
    assert cards["COOLER"] is True
    assert cards["SET-TEMP"] == 15.0
    assert cards["COOLPOWR"] == 18.5
    assert cards["SIMULATE"] is False
    assert cards["SAVEREQ"] is True


def test_local_writer_is_astropy_readable_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    image = np.arange(24, dtype=np.uint16).reshape(4, 6)
    writer = LocalDataProductWriter(tmp_path)

    products = _write(writer, image)
    fits_path = Path(products.file_path)
    quicklook_path = Path(products.quicklook_path)
    original_fits = fits_path.read_bytes()
    original_quicklook = quicklook_path.read_bytes()

    with fits.open(fits_path, uint=True) as hdus:
        hdus.verify("exception")
        header = hdus[0].header
        np.testing.assert_array_equal(hdus[0].data, image)
        assert header["EXPREQ"] == 10.0
        assert header["EXPTIME"] == 9.875
        assert header["FRAMETYP"] == "SCIENCE"
        assert header["BAYERPAT"] == "RGGB"

    assert products.checksum == hashlib.sha256(original_fits).hexdigest()
    assert products.quicklook_checksum == hashlib.sha256(
        original_quicklook
    ).hexdigest()
    assert products.file_size_bytes == len(original_fits)
    assert products.quicklook_size_bytes == len(original_quicklook)

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        _write(writer, image)

    assert fits_path.read_bytes() == original_fits
    assert quicklook_path.read_bytes() == original_quicklook


def test_preexisting_quicklook_blocks_publish_without_creating_fits(
    tmp_path: Path,
) -> None:
    date_path = datetime.now(timezone.utc).strftime("%Y%m%d")
    output_dir = tmp_path / date_path / "obs-contract"
    output_dir.mkdir(parents=True)
    quicklook_path = output_dir / "exp-contract-frame-contract-quicklook.png"
    quicklook_path.write_bytes(b"existing-user-file")

    writer = LocalDataProductWriter(tmp_path)
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        _write(writer, np.zeros((4, 6), dtype=np.uint16))

    assert quicklook_path.read_bytes() == b"existing-user-file"
    assert not (output_dir / "exp-contract-frame-contract.fits").exists()


def test_writer_rejects_detector_dimensions_that_do_not_match_raw_frame(
    tmp_path: Path,
) -> None:
    writer = LocalDataProductWriter(tmp_path)
    image = np.zeros((4, 6), dtype=np.uint16)

    with pytest.raises(ValueError, match="dimensions do not match"):
        writer.write(
            image,
            obs_id="obs-contract",
            exp_id="exp-contract",
            frame_token="frame-contract",
            frame_type="science",
            exp_time_s=1.0,
            actual_exp_time_s=1.0,
            camera_id="science-camera-01",
            logical_channels=("SCI",),
            started_at="2026-08-22T10:55:18+00:00",
            finished_at="2026-08-22T10:55:19+00:00",
            detector_metadata=_metadata(width=5, height=4),
        )


def test_fits_writer_rejects_structural_card_override() -> None:
    with pytest.raises(ValueError, match="BITPIX"):
        build_fits_bytes(
            np.zeros((2, 2), dtype=np.uint16),
            {"BITPIX": 8},
        )
