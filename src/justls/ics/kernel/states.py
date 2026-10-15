from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunMode(str, Enum):
    SIM = "sim"
    REAL = "real"


class ControlState(str, Enum):
    INITIALIZING = "initializing"
    DISCONNECTED = "disconnected"
    IDLE = "idle"
    BUSY = "busy"
    FAULT = "fault"


class ExposureState(str, Enum):
    READY_TO_ARM = "ready_to_arm"
    ARMED = "armed"
    EXPOSING = "exposing"
    READING_OUT = "reading_out"
    COMPLETED = "completed"
    ABORTED = "aborted"
    DISCARDED = "discarded"
    FAILED = "failed"


class CommandSource(str, Enum):
    INTERNAL = "internal"
    UI = "ui"
    API = "api"
    OCS = "ocs"
    SCRIPT = "script"

@dataclass(slots=True)
class SubsystemState:
    name: str
    state: ControlState = ControlState.INITIALIZING
    connected: bool = False
    updated_at: datetime = field(default_factory=utc_now)
    message: str = ""

    def mark_connected(self, connected: bool, *, message: str = "") -> None:
        self.connected = connected
        if not connected and self.state != ControlState.FAULT:
            self.state = ControlState.DISCONNECTED
        self.message = message
        self.updated_at = utc_now()

    def set_state(self, state: ControlState, *, message: str = "") -> None:
        self.state = state
        self.message = message
        self.updated_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "connected": self.connected,
            "updated_at": self.updated_at.isoformat(),
            "message": self.message,
        }


@dataclass(slots=True)
class SystemStateSnapshot:
    run_mode: RunMode
    overall_state: ControlState
    exposure_state: ExposureState
    system: SubsystemState
    slit: SubsystemState
    lamps: SubsystemState
    detector: SubsystemState
    health: SubsystemState
    updated_at: datetime = field(default_factory=utc_now)

    def iter_subsystems(self) -> tuple[SubsystemState, ...]:
        return (
            self.system,
            self.slit,
            self.lamps,
            self.detector,
            self.health,
        )

    def recompute_overall_state(self) -> None:
        subsystems = self.iter_subsystems()

        if any(subsystem.state == ControlState.FAULT for subsystem in subsystems):
            self.overall_state = ControlState.FAULT
            return

        if any(not subsystem.connected for subsystem in subsystems):
            self.overall_state = ControlState.DISCONNECTED
            return

        if any(subsystem.state == ControlState.BUSY for subsystem in subsystems):
            self.overall_state = ControlState.BUSY
            return

        if any(subsystem.state == ControlState.INITIALIZING for subsystem in subsystems):
            self.overall_state = ControlState.INITIALIZING
            return

        self.overall_state = ControlState.IDLE

    def refresh_timestamp(self) -> None:
        self.recompute_overall_state()
        self.updated_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_mode": self.run_mode.value,
            "overall_state": self.overall_state.value,
            "exposure_state": self.exposure_state.value,
            "updated_at": self.updated_at.isoformat(),
            "subsystems": {
                "system": self.system.to_dict(),
                "slit": self.slit.to_dict(),
                "lamps": self.lamps.to_dict(),
                "detector": self.detector.to_dict(),
                "health": self.health.to_dict(),
            },
        }

def build_initial_state(run_mode: RunMode) -> SystemStateSnapshot:
    return SystemStateSnapshot(
        run_mode=run_mode,
        overall_state=ControlState.DISCONNECTED,
        exposure_state=ExposureState.READY_TO_ARM,
        system=SubsystemState(name="system"),
        slit=SubsystemState(name="slit"),
        lamps=SubsystemState(name="lamps"),
        detector=SubsystemState(name="detector"),
        health=SubsystemState(name="health"),
    )