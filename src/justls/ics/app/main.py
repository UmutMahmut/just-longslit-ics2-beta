from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from justls.ics.app.api.errors import build_api_error_detail
from justls.ics.app.api.routers.cameras import router as cameras_router
from justls.ics.app.api.routers.detector import router as detector_router
from justls.ics.app.api.routers.health import router as health_router
from justls.ics.app.api.routers.instrument import router as instrument_router
from justls.ics.app.api.routers.lamps import router as lamps_router
from justls.ics.app.api.routers.observatory import router as observatory_router
from justls.ics.app.api.routers.observation import router as observation_router
from justls.ics.app.api.routers.presets import router as presets_router
from justls.ics.app.api.routers.setup import router as setup_router
from justls.ics.app.api.routers.slit import router as slit_router
from justls.ics.app.api.routers.system import router as system_router

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    from justls.ics.infra.logging import configure_logging
    configure_logging()
    try:
        yield
    finally:
        # Also release cameras when a lifespan consumer exits with an error.
        from justls.ics.kernel.runtime import shutdown_runtime
        shutdown_runtime()


app = FastAPI(
    title="ICS Beta",
    version="0.1.0",
    description="Campus telescope camera and long-slit workflow integration branch.",
    lifespan=lifespan,
)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    incoming = request.headers.get("X-Request-ID")
    request_id = incoming.strip() if incoming and incoming.strip() else uuid.uuid4().hex

    request.state.request_id = request_id

    response = await call_next(request)
    if request.method != "GET" or response.status_code >= 400:
        logger.info("request=%s method=%s path=%s status=%s", request_id,
                    request.method, request.url.path, response.status_code)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request,
    exc: RequestValidationError,
):
    request_id = getattr(request.state, "request_id", None)

    response = JSONResponse(
        status_code=422,
        content={
            "detail": build_api_error_detail(
                code="validation_error",
                message="Request validation failed.",
                errors=jsonable_encoder(exc.errors(), custom_encoder={Exception: str}),
            )
        },
    )
    if request_id:
        response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def handle_unexpected_exception(
    request: Request,
    exc: Exception,
):
    request_id = getattr(request.state, "request_id", None)

    logger.exception(
        "Unhandled exception. request_id=%s path=%s",
        request_id,
        request.url.path,
        exc_info=exc,
    )

    response = JSONResponse(
        status_code=500,
        content={
            "detail": build_api_error_detail(
                code="internal_error",
                message="Internal server error.",
                request_id=request_id,
            )
        },
    )
    if request_id:
        response.headers["X-Request-ID"] = request_id
    return response


app.include_router(health_router)
app.include_router(setup_router)
app.include_router(instrument_router)
app.include_router(slit_router)
app.include_router(lamps_router)
app.include_router(observation_router)
app.include_router(observatory_router)
app.include_router(detector_router)
app.include_router(presets_router)
app.include_router(cameras_router)
app.include_router(system_router)

UI_DIR = Path(__file__).resolve().parent / "ui"
UI_ENTRY = UI_DIR / "ui_alpha_skeleton_v5.html"
UI_V6_ENTRY = UI_DIR / "ui_operational_v6.html"
UI_V7_ENTRY = UI_DIR / "ui_operational_v7.html"
UI_PHASE_2D6_ADAPTER = "/ui-assets/v5/phase2d6_operational_status.js"
UI_V7_RUNTIME_STATUS = "/ui-assets/v7/runtime_status.js?v=3.0-transition"
UI_V7_SETUP_RUNTIME = "/ui-assets/v7/setup_runtime.js?v=3.0b-lite"
UI_V7_INSTRUMENT_RUNTIME = "/ui-assets/v7/instrument_runtime.js?v=3.0-transition"
UI_V7_PRESET_RUNTIME = "/ui-assets/v7/preset_runtime.js"
UI_V7_OBSERVE_RUNTIME = "/ui-assets/v7/observe_runtime.js?v=3.3-manual-fixes"
UI_V7_OBSERVE_GUARD = "/ui-assets/v7/observe_guard.js"
UI_V7_CAMERA_RUNTIME = "/ui-assets/v7/camera_runtime.js?v=3.3-manual-fixes"
UI_V7_ACQUISITION_SETTINGS = "/ui-assets/v7/acquisition_settings.js?v=manual-observation-fixes"
UI_V7_SEQUENCE_RUNTIME = "/ui-assets/v7/sequence_runtime.js?v=3.3-manual-fixes"

PHASE_2D6_V5_ADAPTER_ENABLED_ENV = "JUSTLS_UI_PHASE2D6_ADAPTER_ENABLED"
PHASE_2D6_V6_ENABLED_ENV = "JUSTLS_UI_V6_ENABLED"
PHASE_2D8_V7_ENABLED_ENV = "JUSTLS_UI_V7_ENABLED"
PHASE_2D8_V7_RUNTIME_ENABLED_ENV = "JUSTLS_UI_V7_RUNTIME_ENABLED"
PHASE_2D8_V7_RUNTIME_STATUS_ENABLED_ENV = "JUSTLS_UI_V7_RUNTIME_STATUS_ENABLED"
PHASE_2D8_V7_SETUP_RUNTIME_ENABLED_ENV = "JUSTLS_UI_V7_SETUP_RUNTIME_ENABLED"
PHASE_2D8_V7_INSTRUMENT_RUNTIME_ENABLED_ENV = "JUSTLS_UI_V7_INSTRUMENT_RUNTIME_ENABLED"
PHASE_2D8_V7_PRESET_RUNTIME_ENABLED_ENV = "JUSTLS_UI_V7_PRESET_RUNTIME_ENABLED"
PHASE_2D8_V7_OBSERVE_RUNTIME_ENABLED_ENV = "JUSTLS_UI_V7_OBSERVE_RUNTIME_ENABLED"
PHASE_2D8_V7_OBSERVE_GUARD_ENABLED_ENV = "JUSTLS_UI_V7_OBSERVE_GUARD_ENABLED"

if UI_DIR.exists():
    app.mount("/ui-assets", StaticFiles(directory=UI_DIR), name="ui-assets")

# 添加相机图像的静态文件挂载
CAMERA_DIR = Path(__file__).resolve().parent / "api" / "v1" / "camera"
if CAMERA_DIR.exists():
    app.mount("/camera", StaticFiles(directory=CAMERA_DIR), name="camera")


def env_flag(name: str, *, default: bool = True) -> bool:
    """Read a simple boolean environment flag.

    Operators can set the variable to 0/false/no/off to disable the feature, or
    1/true/yes/on to enable it.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def phase_2d6_v5_adapter_enabled() -> bool:
    return env_flag(PHASE_2D6_V5_ADAPTER_ENABLED_ENV, default=True)


def phase_2d6_v6_enabled() -> bool:
    return env_flag(PHASE_2D6_V6_ENABLED_ENV, default=True)


def phase_2d8_v7_enabled() -> bool:
    return env_flag(PHASE_2D8_V7_ENABLED_ENV, default=True)


def phase_2d8_v7_runtime_enabled() -> bool:
    # v7 runtime is now the default operator workflow. Operators can still set
    # JUSTLS_UI_V7_RUNTIME_ENABLED=0 to force the static shell.
    return env_flag(PHASE_2D8_V7_RUNTIME_ENABLED_ENV, default=True)


def phase_2d8_v7_runtime_status_enabled() -> bool:
    # When the v7 runtime master gate is enabled, status is the first and safest
    # runtime module to restore during Phase 2.8-G.
    return env_flag(PHASE_2D8_V7_RUNTIME_STATUS_ENABLED_ENV, default=True)

def phase_2d8_v7_setup_runtime_enabled() -> bool:
    return env_flag(PHASE_2D8_V7_SETUP_RUNTIME_ENABLED_ENV, default=True)

def phase_2d8_v7_instrument_runtime_enabled() -> bool:
    return env_flag(PHASE_2D8_V7_INSTRUMENT_RUNTIME_ENABLED_ENV, default=True)


def phase_2d8_v7_preset_runtime_enabled() -> bool:
    return env_flag(PHASE_2D8_V7_PRESET_RUNTIME_ENABLED_ENV, default=True)


def phase_2d8_v7_observe_runtime_enabled() -> bool:
    return env_flag(PHASE_2D8_V7_OBSERVE_RUNTIME_ENABLED_ENV, default=True)


def phase_2d8_v7_observe_guard_enabled() -> bool:
    return env_flag(PHASE_2D8_V7_OBSERVE_GUARD_ENABLED_ENV, default=True)


def phase_2d8_v7_runtime_module_flags() -> dict[str, bool]:
    if not phase_2d8_v7_runtime_enabled():
        return {
            "status": False,
            "setup": False,
            "instrument": False,
            "presets": False,
            "observe": False,
            "observe_guard": False,
        }
    return {
        "status": phase_2d8_v7_runtime_status_enabled(),
        "setup": phase_2d8_v7_setup_runtime_enabled(),
        "instrument": phase_2d8_v7_instrument_runtime_enabled(),
        "presets": phase_2d8_v7_preset_runtime_enabled(),
        "observe": phase_2d8_v7_observe_runtime_enabled(),
        "observe_guard": phase_2d8_v7_observe_guard_enabled(),
    }


def phase_2d8_v7_runtime_scripts() -> tuple[str, ...]:
    flags = phase_2d8_v7_runtime_module_flags()
    scripts: list[str] = []
    if flags["status"]:
        scripts.append(UI_V7_RUNTIME_STATUS)
    if flags["setup"]:
        scripts.append(UI_V7_SETUP_RUNTIME)
    if flags["instrument"]:
        scripts.append(UI_V7_INSTRUMENT_RUNTIME)
    if flags["presets"]:
        scripts.append(UI_V7_PRESET_RUNTIME)
    if flags["observe"]:
        scripts.append(UI_V7_OBSERVE_RUNTIME)
    if flags["observe_guard"]:
        scripts.append(UI_V7_OBSERVE_GUARD)
    if flags["observe"]:
        scripts.append(UI_V7_SEQUENCE_RUNTIME)
        scripts.append(UI_V7_ACQUISITION_SETTINGS)
    if phase_2d8_v7_runtime_enabled():
        scripts.append(UI_V7_CAMERA_RUNTIME)
    return tuple(scripts)


def inject_script_tag(html: str, script_src: str) -> str:
    tag = f'<script src="{script_src}" defer></script>'
    if tag in html:
        return html
    if "</body>" in html:
        return html.replace("</body>", f"  {tag}\n</body>")
    return f"{html}\n{tag}\n"


def inject_phase_2d6_ui_adapter(html: str) -> str:
    """Attach the Phase 2.6 operational-status adapter to the static v5 UI."""
    return inject_script_tag(html, UI_PHASE_2D6_ADAPTER)


def serve_v7_html() -> HTMLResponse | dict[str, str]:
    if not phase_2d8_v7_enabled():
        raise HTTPException(status_code=404, detail="Operational UI v7 is disabled.")
    return serve_html(
        UI_V7_ENTRY,
        extra_scripts=phase_2d8_v7_runtime_scripts(),
    )


def serve_html(
    path: Path,
    *,
    inject_adapter: bool = False,
    extra_scripts: tuple[str, ...] = (),
):
    if path.exists():
        html = path.read_text(encoding="utf-8")
        if inject_adapter:
            html = inject_phase_2d6_ui_adapter(html)
        for script_src in extra_scripts:
            html = inject_script_tag(html, script_src)
        return HTMLResponse(html)
    return {
        "message": "UI entry not found.",
        "expected": str(path),
    }


@app.get("/")
def read_root() -> dict:
    return {
        "message": "ICS Beta is running.",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "ui": "/ui" if UI_V7_ENTRY.exists() and phase_2d8_v7_enabled() else ("/ui/v5" if UI_ENTRY.exists() else None),
        "ui_v5": "/ui/v5" if UI_ENTRY.exists() else None,
        "ui_legacy": "/ui/legacy" if UI_ENTRY.exists() else None,
        "ui_v6": "/ui/v6" if UI_V6_ENTRY.exists() and phase_2d6_v6_enabled() else None,
        "ui_v7": "/ui/v7" if UI_V7_ENTRY.exists() and phase_2d8_v7_enabled() else None,
        "ui_default": "v7" if UI_V7_ENTRY.exists() and phase_2d8_v7_enabled() else "v5",
        "ui_default_note": "v7 is the default operator-console prototype; v5 remains available at /ui/v5 and /ui/legacy.",
        "ui_safety_switches": {
            "phase2d6_v5_adapter_enabled": phase_2d6_v5_adapter_enabled(),
            "phase2d6_v6_enabled": phase_2d6_v6_enabled(),
            "phase2d8_v7_enabled": phase_2d8_v7_enabled(),
            "phase2d8_v7_runtime_enabled": phase_2d8_v7_runtime_enabled(),
            "phase2d8_v7_runtime_modules": phase_2d8_v7_runtime_module_flags(),
        },
    }


@app.get("/ui", include_in_schema=False)
def read_ui():
    return serve_v7_html()


@app.get("/ui/v5", include_in_schema=False)
def read_ui_v5():
    return serve_html(UI_ENTRY, inject_adapter=phase_2d6_v5_adapter_enabled())


@app.get("/ui/legacy", include_in_schema=False)
def read_ui_legacy():
    return serve_html(UI_ENTRY, inject_adapter=phase_2d6_v5_adapter_enabled())


@app.get("/ui/v6", include_in_schema=False)
def read_ui_v6():
    if not phase_2d6_v6_enabled():
        raise HTTPException(status_code=404, detail="Operational UI v6 is disabled.")
    return serve_html(UI_V6_ENTRY)


@app.get("/ui/v7", include_in_schema=False)
def read_ui_v7():
    return serve_v7_html()
