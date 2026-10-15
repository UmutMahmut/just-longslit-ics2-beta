from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from justls.ics.drivers.zwo.sdk import (
    ZwoCameraTopologyChangedError,
    ZwoSdk,
    ZwoSdkError,
    ZwoSdkLibraryLoadError,
)


SDK_LIBRARY_ENV = "ICS_ZWO_SDK_LIBRARY"


def resolve_sdk_library(path: Path | None) -> Path:
    if path is not None:
        return path
    configured = os.getenv(SDK_LIBRARY_ENV)
    if configured and configured.strip():
        return Path(configured.strip())
    raise SystemExit(
        f"provide --dll or set {SDK_LIBRARY_ENV} to the ASICamera2 library path"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only ZWO ASI discovery probe. This does not open, initialize, "
            "cool, or expose the camera."
        )
    )
    parser.add_argument(
        "--dll",
        type=Path,
        default=None,
        help="Path to the vendor ASICamera2 library.",
    )
    parser.add_argument(
        "--controls",
        action="store_true",
        help=(
            "Open and initialize each camera, read its control capabilities and "
            "current values, then close it. This can affect an active vendor session."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        sdk = ZwoSdk(resolve_sdk_library(args.dll))
        cameras = sdk.discover()
    except ZwoCameraTopologyChangedError as exc:
        print(
            json.dumps(
                {
                    "error": "camera_topology_changed",
                    "detail": str(exc),
                    "expected_count": exc.expected_count,
                    "actual_count": exc.actual_count,
                    "recovery": "re-run the probe after the USB topology settles",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    except (ZwoSdkLibraryLoadError, ZwoSdkError) as exc:
        print(
            json.dumps(
                {
                    "error": type(exc).__name__,
                    "detail": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    controls_by_camera: dict[str, list[dict]] = {}
    serial_by_camera: dict[str, str] = {}
    if args.controls:
        for camera in cameras:
            with sdk.open_camera(camera.camera_id) as session:
                serial_by_camera[str(camera.camera_id)] = session.serial_number()
                controls_by_camera[str(camera.camera_id)] = [
                    control.to_dict() for control in session.controls()
                ]
    print(
        json.dumps(
            {
                "dll_path": str(sdk.dll_path),
                "sdk_version": sdk.sdk_version(),
                "connected_camera_count": len(cameras),
                "cameras": [camera.to_dict() for camera in cameras],
                "serial_number_by_camera_id": serial_by_camera,
                "controls_by_camera_id": controls_by_camera,
                "probe_scope": (
                    "open-initialize-read-controls-close"
                    if args.controls
                    else "read-only-discovery"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
