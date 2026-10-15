from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from justls.ics.application.dispatcher import DispatchResult


def build_api_error_detail(
    *,
    code: str,
    message: str,
    **extra: Any,
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "code": code,
        "message": message,
    }
    detail.update(extra)
    return detail


def raise_api_error(
    *,
    status_code: int,
    code: str,
    message: str,
    **extra: Any,
) -> None:
    raise HTTPException(
        status_code=status_code,
        detail=build_api_error_detail(
            code=code,
            message=message,
            **extra,
        ),
    )


def _extract_error_code_and_message(error: Any, default_code: str) -> tuple[str, str]:
    if isinstance(error, dict):
        code = str(error.get("code") or default_code)
        message = error.get("message")

        if isinstance(message, str) and message:
            return code, message

        return code, "Command failed."

    if isinstance(error, str) and error:
        return default_code, error

    return default_code, "Command failed."


def raise_dispatch_failure(
    result: DispatchResult,
    *,
    default_code: str = "command_failed",
) -> None:
    payload = result.payload or {}
    error = payload.get("error")

    code, message = _extract_error_code_and_message(error, default_code)

    raise_api_error(
        status_code=400,
        code=code,
        message=message,
    )
