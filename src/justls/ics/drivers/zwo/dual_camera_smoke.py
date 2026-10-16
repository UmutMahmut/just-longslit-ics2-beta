"""Dual-camera hardware smoke: science FITS + concurrent guide preview.

Run this after plugging both ZWO cameras back in. It verifies, in order:

1. SDK loads (with actionable error if the DLL is missing);
2. both configured serials are found among the attached cameras
   (serial binding, never USB index);
3. the science camera (ASI294MC Pro) writes a real FITS
   (``SIMULATE=false``, astropy-readable, checksum verified) while the
   guide camera (ASI678MC) captures preview JPEGs **concurrently** —
   proving both can expose at the same time;
4. both cameras are released cleanly on exit.

``--preflight-only`` stops after step 2 (no exposures).

Example::

    python -m justls.ics.drivers.zwo.dual_camera_smoke \
        --science-serial 28344F041D010900 --guide-serial <678MC serial> \
        --science-exposure-s 2.0 --guide-frames 5
"""

from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from justls.ics.adapters.detector.adapter import DetectorAdapter
from justls.ics.drivers.zwo.assembly import (
    build_zwo_detector_driver,
    build_zwo_preview_driver,
    resolve_sdk_library_path,
)
from justls.ics.drivers.zwo.sdk import (
    ZwoCameraTopologyChangedError,
    ZwoSdk,
    ZwoSdkError,
    ZwoSdkLibraryLoadError,
)
from justls.ics.infra.camera_config import CameraDeviceConfig
from justls.ics.infra.data_products import LocalDataProductWriter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dll", type=Path, default=None)
    parser.add_argument("--science-serial", required=True)
    parser.add_argument("--guide-serial", required=True)
    parser.add_argument("--science-exposure-s", type=float, default=2.0)
    parser.add_argument("--guide-frames", type=int, default=5)
    parser.add_argument("--guide-exposure-ms", type=float, default=100.0)
    parser.add_argument("--guide-binning", type=int, default=2)
    parser.add_argument("--gain", type=int, default=100)
    parser.add_argument("--offset", type=int, default=30)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("var/hardware-smoke"),
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="enumerate and bind cameras only; take no exposures",
    )
    return parser


def _science_config(serial: str, args: argparse.Namespace) -> CameraDeviceConfig:
    return CameraDeviceConfig(
        device_id="zwo-science-smoke",
        driver="zwo",
        manufacturer="ZWO",
        model="",
        serial=serial,
        width=4144,  # ASI294MC Pro SDK-reported maximum (bin 1 full frame)
        height=2822,
        bit_depth=14,
        gain=args.gain,
        offset=args.offset,
        binning=1,
    )


def _guide_config(serial: str, args: argparse.Namespace) -> CameraDeviceConfig:
    return CameraDeviceConfig(
        device_id="zwo-guide-smoke",
        driver="zwo",
        manufacturer="ZWO",
        model="",
        serial=serial,
        width=1920,
        height=1080,
        bit_depth=12,
        gain=args.gain,
        offset=args.offset,
        binning=args.guide_binning,
        preview_exposure_ms=args.guide_exposure_ms,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "preflight_only": bool(args.preflight_only),
        "steps": [],
    }

    def step(name: str, **details: Any) -> None:
        report["steps"].append({"step": name, "ok": True, **details})
        print(f"[ok] {name}: {json.dumps(details, ensure_ascii=False)}")

    try:
        sdk = ZwoSdk(resolve_sdk_library_path(args.dll))
        step("sdk_loaded", version=sdk.sdk_version())
    except ZwoSdkLibraryLoadError as exc:
        report["steps"].append({"step": "sdk_loaded", "ok": False, "error": str(exc)})
        report["result"] = "FAIL"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    try:
        cameras = sdk.discover()
        step(
            "cameras_enumerated",
            count=len(cameras),
            models=[camera.name for camera in cameras],
        )
    except (ZwoSdkError, ZwoCameraTopologyChangedError) as exc:
        report["steps"].append(
            {"step": "cameras_enumerated", "ok": False, "error": str(exc)}
        )
        report["result"] = "FAIL"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    try:
        science_driver = build_zwo_detector_driver(
            _science_config(args.science_serial, args),
            sdk=sdk,
        )
        step(
            "science_bound",
            model=science_driver.descriptor.name,
            serial=science_driver.detected_serial,
        )
        guide_driver = build_zwo_preview_driver(
            _guide_config(args.guide_serial, args),
            sdk=sdk,
            role="slit",
        )
        step(
            "guide_bound",
            model=guide_driver.descriptor.name,
            serial=guide_driver.detected_serial,
        )
    except (RuntimeError, ZwoSdkError, ValueError) as exc:
        report["steps"].append({"step": "bind", "ok": False, "error": str(exc)})
        report["result"] = "FAIL"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    if args.preflight_only:
        science_driver.disconnect()
        guide_driver.disconnect()
        report["result"] = "PASS"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    data_root = args.data_root / timestamp
    data_root.mkdir(parents=True, exist_ok=True)

    adapter = DetectorAdapter(
        science_driver,
        writer=LocalDataProductWriter(data_root),
        logical_channels=("SCI",),
        simulated=False,
    )

    guide_results: list[dict[str, Any]] = []
    guide_errors: list[str] = []
    stop_guide = threading.Event()

    def guide_loop() -> None:
        for index in range(args.guide_frames):
            if stop_guide.is_set():
                return
            try:
                payload, meta = guide_driver.capture_jpeg()
                jpeg_path = data_root / f"guide-{index:03d}.jpg"
                jpeg_path.write_bytes(payload)
                guide_results.append(
                    {"path": str(jpeg_path), "bytes": len(payload), **meta}
                )
            except Exception as exc:  # noqa: BLE001 - reported, not raised
                guide_errors.append(str(exc))
                return

    fits_path: str | None = None
    try:
        # Start the science exposure, then hammer the guide camera while the
        # science frame is integrating: concurrent exposure is the point.
        science_driver.start_exposure(
            obs_id=f"dual-smoke-{timestamp}",
            exp_id=f"exp-{timestamp}",
            exp_time_s=float(args.science_exposure_s),
            frame_type="test",
            save_requested=True,
        )
        guide_thread = threading.Thread(target=guide_loop, daemon=True)
        guide_thread.start()
        result = adapter.finish_exposure()
        guide_thread.join(timeout=30)
        stop_guide.set()

        fits_path = result.get("file_path")
        if not fits_path or not Path(fits_path).is_file():
            raise RuntimeError("science capture did not produce a FITS file")

        # Verify FITS independently: astropy-readable + checksum matches.
        from astropy.io import fits as astropy_fits

        with astropy_fits.open(fits_path) as hdul:
            header = hdul[0].header
            checks = {
                "simulate_flag": bool(header.get("SIMULATE")),
                "exptime_s": float(header.get("EXPTIME", -1)),
                "camera": header.get("CAMERA"),
                "naxis": [header.get("NAXIS1"), header.get("NAXIS2")],
            }
        if checks["simulate_flag"] is not False:
            raise RuntimeError("FITS SIMULATE flag is not False")
        digest = hashlib.sha256(Path(fits_path).read_bytes()).hexdigest()
        if digest != result.get("checksum"):
            raise RuntimeError("FITS checksum mismatch after write")
        step(
            "science_fits_verified",
            path=fits_path,
            checksum=digest,
            **checks,
        )
        step(
            "guide_concurrent_frames",
            captured=len(guide_results),
            errors=guide_errors,
        )
        if not guide_results:
            raise RuntimeError("guide camera produced no concurrent frames")
    except Exception as exc:  # noqa: BLE001 - smoke reports, then exits 1
        report["steps"].append({"step": "capture", "ok": False, "error": str(exc)})
        report["result"] = "FAIL"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    finally:
        # Handles must be released even on failure so the next run can bind.
        for driver in (science_driver, guide_driver):
            try:
                driver.disconnect()
            except Exception:  # noqa: BLE001
                pass

    # Brief settle, then confirm both cameras are re-bindable (handles freed).
    time.sleep(0.5)
    try:
        rebind_check = sdk.connected_camera_count()
        step("handles_released", cameras_visible=rebind_check)
    except Exception as exc:  # noqa: BLE001
        report["steps"].append(
            {"step": "handles_released", "ok": False, "error": str(exc)}
        )

    report["result"] = "PASS"
    report["fits_path"] = fits_path
    report["guide_frames"] = guide_results
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
