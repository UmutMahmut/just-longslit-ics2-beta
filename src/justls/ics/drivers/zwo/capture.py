from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from justls.ics.adapters.detector.adapter import DetectorAdapter
from justls.ics.drivers.zwo.detector_driver import ZwoDetectorDriver
from justls.ics.drivers.zwo.probe import resolve_sdk_library
from justls.ics.drivers.zwo.sdk import ZwoSdk
from justls.ics.infra.camera_config import CameraDeviceConfig
from justls.ics.infra.data_products import LocalDataProductWriter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture one full-frame ZWO RAW16 exposure through the ICS detector "
            "adapter and write the normal ICS FITS plus quicklook products."
        )
    )
    parser.add_argument("--dll", type=Path, default=None)
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--data-root", type=Path, default=Path("var/hardware-smoke"))
    parser.add_argument("--exposure-s", type=float, default=0.01)
    parser.add_argument("--gain", type=int, default=0)
    parser.add_argument("--offset", type=int, default=30)
    parser.add_argument(
        "--frame-type",
        choices=("science", "bias", "dark", "flat", "arc", "test"),
        default="test",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sdk = ZwoSdk(resolve_sdk_library(args.dll))
    cameras = sdk.discover()
    try:
        descriptor = cameras[args.camera_index]
    except IndexError as exc:
        raise SystemExit(
            f"camera index {args.camera_index} is unavailable; detected {len(cameras)}"
        ) from exc

    config = CameraDeviceConfig(
        device_id=f"zwo-camera-{descriptor.camera_id}",
        driver="zwo",
        manufacturer="ZWO",
        model=descriptor.name,
        width=descriptor.max_width,
        height=descriptor.max_height,
        bit_depth=descriptor.bit_depth,
        gain=args.gain,
    )
    driver = ZwoDetectorDriver(
        sdk,
        descriptor,
        config,
        gain=args.gain,
        offset=args.offset,
    )
    adapter = DetectorAdapter(
        driver,
        writer=LocalDataProductWriter(args.data_root),
        logical_channels=("SCI",),
        simulated=False,
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    with driver:
        result = adapter.acquire_exposure(
            obs_id=f"zwo-smoke-{timestamp}",
            exp_time_s=args.exposure_s,
            frame_type=args.frame_type,
            save_requested=True,
        )

    print(
        json.dumps(
            {
                "sdk_version": sdk.sdk_version(),
                "camera": descriptor.to_dict(),
                "capture": result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
