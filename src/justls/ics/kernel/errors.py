from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ErrorCode(str, Enum):
    OK = "ok"
    INVALID_PARAM = "invalid_param"
    INVALID_STATE = "invalid_state"
    BUSY = "busy"
    TIMEOUT = "timeout"
    DEVICE_DISCONNECTED = "device_disconnected"
    DEVICE_FAULT = "device_fault"
    INTERLOCK_BLOCKED = "interlock_blocked"
    CONFIRMATION_REQUIRED = "confirmation_required"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class ErrorInfo:
    code: ErrorCode
    message: str
    subsystem: str | None = None
    retriable: bool = False
    details: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "subsystem": self.subsystem,
            "retriable": self.retriable,
            "details": self.details,
            "created_at": self.created_at.isoformat(),
        }


class ICSException(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        subsystem: str | None = None,
        retriable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.info = ErrorInfo(
            code=code,
            message=message,
            subsystem=subsystem,
            retriable=retriable,
            details=details or {},
        )

    @property
    def code(self) -> ErrorCode:
        return self.info.code

    def to_dict(self) -> dict[str, Any]:
        return self.info.to_dict()


class InvalidParamError(ICSException):
    def __init__(self, message: str, *, subsystem: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            ErrorCode.INVALID_PARAM,
            message,
            subsystem=subsystem,
            retriable=False,
            details=details,
        )


class InvalidStateError(ICSException):
    def __init__(self, message: str, *, subsystem: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            ErrorCode.INVALID_STATE,
            message,
            subsystem=subsystem,
            retriable=False,
            details=details,
        )


class BusyError(ICSException):
    def __init__(self, message: str = "Subsystem is busy.", *, subsystem: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            ErrorCode.BUSY,
            message,
            subsystem=subsystem,
            retriable=True,
            details=details,
        )


class DeviceDisconnectedError(ICSException):
    def __init__(self, message: str = "Device is disconnected.", *, subsystem: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            ErrorCode.DEVICE_DISCONNECTED,
            message,
            subsystem=subsystem,
            retriable=True,
            details=details,
        )


class DeviceFaultError(ICSException):
    def __init__(self, message: str = "Device is in fault state.", *, subsystem: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            ErrorCode.DEVICE_FAULT,
            message,
            subsystem=subsystem,
            retriable=False,
            details=details,
        )


class InterlockBlockedError(ICSException):
    def __init__(self, message: str = "Operation blocked by interlock.", *, subsystem: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            ErrorCode.INTERLOCK_BLOCKED,
            message,
            subsystem=subsystem,
            retriable=False,
            details=details,
        )


class UnsupportedError(ICSException):
    def __init__(self, message: str = "Operation is unsupported.", *, subsystem: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            ErrorCode.UNSUPPORTED,
            message,
            subsystem=subsystem,
            retriable=False,
            details=details,
        )