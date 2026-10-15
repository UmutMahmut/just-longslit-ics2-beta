from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ObservatoryContextState(str, Enum):
    READY = "ready"
    UNKNOWN = "unknown"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class ObservatoryComponentContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: ObservatoryContextState = ObservatoryContextState.UNAVAILABLE
    connected: bool = False
    stale: bool = False
    message: str
    updated_at_utc: str | None = None

    @classmethod
    def unavailable(cls, message: str) -> "ObservatoryComponentContext":
        return cls(
            state=ObservatoryContextState.UNAVAILABLE,
            connected=False,
            stale=False,
            message=message,
            updated_at_utc=utc_now_iso(),
        )


class ObservatoryTargetContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_name: str | None = None
    ra_deg: float | None = None
    dec_deg: float | None = None
    source: str = "not_supplied"
    message: str = "No OCS/TCS target context has been supplied."


class ObservatoryContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = "ics-local-placeholder"
    run_mode: str
    writable: bool = False
    target: ObservatoryTargetContext = Field(default_factory=ObservatoryTargetContext)
    ocs: ObservatoryComponentContext
    tcs: ObservatoryComponentContext
    telescope: ObservatoryComponentContext
    dome: ObservatoryComponentContext
    weather: ObservatoryComponentContext
    guider: ObservatoryComponentContext
    updated_at_utc: str = Field(default_factory=utc_now_iso)

    @classmethod
    def default_unavailable(cls, *, run_mode: str) -> "ObservatoryContext":
        return cls(
            run_mode=run_mode,
            writable=False,
            ocs=ObservatoryComponentContext.unavailable(
                "OCS integration is not implemented yet."
            ),
            tcs=ObservatoryComponentContext.unavailable(
                "TCS readiness is not implemented yet."
            ),
            telescope=ObservatoryComponentContext.unavailable(
                "Read-only telescope context is not connected."
            ),
            dome=ObservatoryComponentContext.unavailable(
                "Dome context is not connected."
            ),
            weather=ObservatoryComponentContext.unavailable(
                "Weather context is not connected."
            ),
            guider=ObservatoryComponentContext.unavailable(
                "Guider context is not connected."
            ),
        )
