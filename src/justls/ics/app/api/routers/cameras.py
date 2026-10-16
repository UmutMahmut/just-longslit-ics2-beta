from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from justls.ics.domain.detector.acquisition_settings import CameraSettingsUpdate
from justls.ics.kernel.errors import ICSException
from justls.ics.kernel.states import ControlState

from justls.ics.app.api.dependencies import RuntimeDep
from justls.ics.kernel.errors import InvalidStateError


router = APIRouter(tags=["cameras"])


logger = logging.getLogger(__name__)


def _camera_driver(runtime, role):
    adapter = None
    if role == "science" and runtime.detector is not None:
        adapter = runtime.detector.adapter
    elif role == "slit":
        adapter = runtime.slit_camera
    if adapter is None:
        raise HTTPException(503, "Camera is unavailable; inspect camera status and logs.")
    return adapter.driver


@router.get("/api/v1/cameras/{role}/settings")
def get_settings(role: Literal["science", "slit"], runtime: RuntimeDep):
    return _camera_driver(runtime, role).get_settings()


@router.put("/api/v1/cameras/{role}/settings")
def set_settings(role: Literal["science", "slit"], req: CameraSettingsUpdate, runtime: RuntimeDep):
    with runtime.sequence_lock:
        try:
            runtime.require_open()
            reason = runtime.reload_block_reason()
            if reason:
                raise InvalidStateError(reason)
            driver = _camera_driver(runtime, role)
            updates = req.model_dump(exclude_none=True)
            result = driver.configure_settings(updates) if updates else driver.get_settings()
            logger.info("Camera settings applied role=%s updates=%s effective=%s", role, updates, result)
            return result
        except ICSException as exc:
            raise HTTPException(409 if isinstance(exc, InvalidStateError) else 400, str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Camera settings failed role=%s", role)
            if role == "science" and runtime.detector is not None:
                runtime.detector.mark_failed()
                runtime.set_subsystem_state("detector", ControlState.FAULT, message=f"Settings failed: {exc}; reload cameras")
            elif role == "slit" and runtime.slit_camera is not None:
                runtime.slit_camera.stop_preview()
            raise HTTPException(503, f"Settings failed: {exc}; reload cameras before continuing.") from exc


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
    except (TimeoutError, OSError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
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
        try:
            return runtime.slit_camera.start_preview()
        except (RuntimeError, TimeoutError, OSError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc


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
