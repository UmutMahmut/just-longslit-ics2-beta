from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from justls.ics.app.api.dependencies import RuntimeDep


router = APIRouter(tags=["cameras"])


def _no_cache_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    }


@router.get("/api/v1/cameras/status")
def get_camera_status(runtime: RuntimeDep) -> dict:
    return runtime.get_camera_status_dict()


@router.get("/camera/slit/latest.jpg", include_in_schema=False)
def get_slit_camera_preview(runtime: RuntimeDep) -> Response:
    if runtime.slit_camera is None:
        raise HTTPException(status_code=503, detail="Slit camera is unavailable.")
    payload, metadata = runtime.slit_camera.get_preview()
    headers = _no_cache_headers()
    headers.update(
        {
            "X-ICS-Camera-ID": metadata["device_id"],
            "X-ICS-Camera-Role": "slit",
            "X-ICS-Frame-Sequence": str(metadata["sequence"]),
        }
    )
    return Response(payload, media_type="image/jpeg", headers=headers)


@router.get("/camera/{channel}/latest.jpg", include_in_schema=False)
def get_shared_science_preview(channel: str, runtime: RuntimeDep) -> Response:
    logical_channel = channel.upper()
    if logical_channel not in {"B", "G", "R"}:
        raise HTTPException(status_code=404, detail="Unknown logical camera channel.")
    if runtime.detector is None:
        raise HTTPException(status_code=503, detail="Science camera is unavailable.")
    payload, metadata = runtime.detector.adapter.get_latest_preview()
    headers = _no_cache_headers()
    headers.update(
        {
            "X-ICS-Physical-Camera": metadata["device_id"],
            "X-ICS-Logical-Channel": logical_channel,
            "X-ICS-Shared-Capture": "true",
        }
    )
    return Response(payload, media_type="image/png", headers=headers)
