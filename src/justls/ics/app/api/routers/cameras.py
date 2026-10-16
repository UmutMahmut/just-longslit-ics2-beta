from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from justls.ics.app.api.dependencies import RuntimeDep
from justls.ics.kernel.errors import InvalidStateError


router = APIRouter(tags=["cameras"])


logger = logging.getLogger(__name__)


def _no_cache_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    }


@router.get("/api/v1/cameras/status")
def get_camera_status(runtime: RuntimeDep) -> dict:
    return runtime.get_camera_status_dict()


@router.post("/api/v1/cameras/reload")
def reload_cameras(runtime: RuntimeDep) -> dict:
    """Tear down the current camera runtime and rebuild it from scratch.

    This is the operator-driven recovery path: after a hotplug (a camera
    that the SDK could not enumerate before is now visible, or a camera
    that was previously stuck is now responsive), the operator asks the
    service to release all handles and rebind. The reload runs the same
    ``RuntimeAssembler.build()`` path that brought the system up, so the
    watchdog fallbacks and ``ICS_BETA_FORCE_SIM`` safe mode still apply.

    The endpoint is intentionally synchronous and short: a build is
    allowed to take several seconds while the SDK enumerates and binds,
    but the reload is the operator's acknowledgement of a USB change, so
    no extra confirmation is required.
    """
    from justls.ics.kernel.runtime import reset_runtime

    try:
        new_runtime = reset_runtime(expected=runtime)
    except InvalidStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("camera reload failed")
        raise HTTPException(
            status_code=503,
            detail=(
                "camera reload failed: "
                f"{type(exc).__name__}: {exc}; the previous runtime has "
                "been released; restart the service to retry."
            ),
        ) from exc
    return {
        "reloaded": True,
        "force_sim": new_runtime.force_sim,
        "slit_camera": (
            new_runtime.slit_camera is not None
            and new_runtime.slit_camera.get_status().get("connected", False)
        ),
        "science_camera": (
            new_runtime.detector is not None
            and new_runtime.detector.adapter.get_status().get("connected", False)
        ),
        "hot_plug": (
            new_runtime.hotplug_monitor.status_dict()
            if new_runtime.hotplug_monitor is not None
            else None
        ),
    }


@router.get("/camera/slit/latest.jpg", include_in_schema=False)
def get_slit_camera_preview(runtime: RuntimeDep) -> Response:
    if runtime.slit_camera is None:
        raise HTTPException(status_code=503, detail="Slit camera is unavailable.")
    try:
        payload, metadata = runtime.slit_camera.get_preview()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    headers = _no_cache_headers()
    headers.update(
        {
            "X-ICS-Camera-ID": metadata["device_id"],
            "X-ICS-Camera-Role": "slit",
            "X-ICS-Frame-Sequence": str(metadata["sequence"]),
        }
    )
    return Response(payload, media_type="image/jpeg", headers=headers)


@router.post("/api/v1/cameras/slit/preview/start")
def start_slit_camera_preview(runtime: RuntimeDep) -> dict:
    if runtime.slit_camera is None:
        raise HTTPException(status_code=503, detail="Slit camera is unavailable.")
    with runtime.sequence_lock:
        runtime.require_open()
        return runtime.slit_camera.start_preview()


@router.post("/api/v1/cameras/slit/preview/stop")
def stop_slit_camera_preview(runtime: RuntimeDep) -> dict:
    if runtime.slit_camera is None:
        raise HTTPException(status_code=503, detail="Slit camera is unavailable.")
    with runtime.sequence_lock:
        runtime.require_open()
        return runtime.slit_camera.stop_preview()


def _science_channel_response(runtime: RuntimeDep, logical_channel: str) -> Response:
    if runtime.detector is None:
        raise HTTPException(status_code=503, detail="Science camera is unavailable.")
    try:
        payload, metadata = runtime.detector.adapter.get_latest_preview()
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    headers = _no_cache_headers()
    headers.update(
        {
            "X-ICS-Physical-Camera": metadata["device_id"],
            "X-ICS-Camera-Role": "science",
            "X-ICS-Logical-Channel": logical_channel,
            "X-ICS-Shared-Capture": "true",
        }
    )
    return Response(payload, media_type="image/png", headers=headers)


@router.get("/camera/{channel}/latest.jpg", include_in_schema=False)
def get_science_channel_latest(channel: str, runtime: RuntimeDep) -> Response:
    logical_channel = channel.upper()
    if logical_channel not in {"B", "G", "R"}:
        raise HTTPException(status_code=404, detail="Unknown logical camera channel.")
    return _science_channel_response(runtime, logical_channel)
