from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Sequence

from justls.ics.drivers.zwo.detector_driver import ZwoDetectorDriver
from justls.ics.drivers.zwo.probe import resolve_sdk_library
from justls.ics.drivers.zwo.sdk import ZwoSdk
from justls.ics.infra.camera_config import CameraDeviceConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Briefly enable an ASI camera cooler, read back telemetry, and restore "
            "the original cooler state and target temperature."
        )
    )
    parser.add_argument("--dll", type=Path, default=None)
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--target-c", type=int, default=-10)
    parser.add_argument("--hold-s", type=float, default=2.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.hold_s < 0 or args.hold_s > 30:
        raise SystemExit("--hold-s must be between 0 and 30 seconds")

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
    )
    driver = ZwoDetectorDriver(sdk, descriptor, config)
    with driver:
        before = driver.cooling_status()
        enabled = driver.set_cooling(
            enabled=True,
            target_temperature_c=args.target_c,
        )
        try:
            time.sleep(args.hold_s)
            during = driver.cooling_status()
        finally:
            restored = driver.set_cooling(
                enabled=bool(before["cooler_enabled"]),
                target_temperature_c=round(float(before["cooler_target_c"])),
            )

    print(
        json.dumps(
            {
                "sdk_version": sdk.sdk_version(),
                "camera": descriptor.to_dict(),
                "requested_target_c": args.target_c,
                "hold_s": args.hold_s,
                "before": before,
                "enabled_readback": enabled,
                "during": during,
                "restored": restored,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
