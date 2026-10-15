from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from justls.ics.app.api.errors import build_api_error_detail
from justls.ics.app.api.routers.detector import router as detector_router
from justls.ics.app.api.routers.health import router as health_router
from justls.ics.app.api.routers.lamps import router as lamps_router
from justls.ics.app.api.routers.observatory import router as observatory_router
from justls.ics.app.api.routers.observation import router as observation_router
from justls.ics.app.api.routers.presets import router as presets_router
from justls.ics.app.api.routers.slit import router as slit_router

app = FastAPI(
    title="JUST Long-Slit ICS 2.0",
    version="0.0.1",
    description="Rebuilt internal control kernel for JUST long-slit spectrograph ICS.",
)


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request,
    exc: RequestValidationError,
):
    return JSONResponse(
        status_code=422,
        content={
            "detail": build_api_error_detail(
                code="validation_error",
                message="Request validation failed.",
                errors=exc.errors(),
            )
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_exception(
    request: Request,
    exc: Exception,
):
    return JSONResponse(
        status_code=500,
        content={
            "detail": build_api_error_detail(
                code="internal_error",
                message="Internal server error.",
            )
        },
    )


app.include_router(health_router)
app.include_router(slit_router)
app.include_router(lamps_router)
app.include_router(observation_router)
app.include_router(observatory_router)
app.include_router(detector_router)
app.include_router(presets_router)

UI_DIR = Path(__file__).resolve().parent / "ui"
UI_ENTRY = UI_DIR / "ui_alpha_skeleton_v4.html"

if UI_DIR.exists():
    app.mount("/ui-assets", StaticFiles(directory=UI_DIR), name="ui-assets")


@app.get("/")
def read_root() -> dict:
    return {
        "message": "JUST Long-Slit ICS 2.0 is running.",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "ui": "/ui" if UI_ENTRY.exists() else None,
    }


@app.get("/ui", include_in_schema=False)
def read_ui():
    if UI_ENTRY.exists():
        return FileResponse(UI_ENTRY)
    return {
        "message": "UI entry not found.",
        "expected": str(UI_ENTRY),
    }
