from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CHANNEL_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]{0,15}$")


class DetectorChannelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    camera_role: str | None = None
    source_camera_id: str | None = None


def default_detector_channels() -> dict[str, DetectorChannelConfig]:
    return {
        channel: DetectorChannelConfig(
            enabled=False,
            camera_role=f"science_{channel.lower()}",
        )
        for channel in ("B", "G", "R")
    }


class DetectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_name: str = "default"
    trigger_mode: Literal["internal", "external", "simulated"] = "internal"
    readout_mode: str = "normal"
    shared_physical_camera: bool = False
    channels: dict[str, DetectorChannelConfig] = Field(
        default_factory=default_detector_channels
    )

    @field_validator("channels", mode="before")
    @classmethod
    def normalize_channels(cls, raw: Any) -> Any:
        if not isinstance(raw, dict):
            return raw
        normalized = {str(name).strip().upper(): value for name, value in raw.items()}
        if len(normalized) != len(raw):
            raise ValueError("detector channel names must be unique")
        if any(not CHANNEL_NAME_PATTERN.fullmatch(name) for name in normalized):
            raise ValueError(
                "detector channel names must begin with A-Z and contain only "
                "A-Z, 0-9, underscore, or hyphen"
            )
        return normalized

    def to_dict(self) -> dict:
        return self.model_dump()


def build_default_detector_config() -> DetectorConfig:
    return DetectorConfig()


def build_beta_detector_config(
    camera_id: str,
    *,
    logical_channels: tuple[str, ...] = ("B", "G", "R"),
    profile_name: str = "campus-beta-shared-camera",
    shared_physical_camera: bool = True,
) -> DetectorConfig:
    return DetectorConfig(
        profile_name=profile_name,
        trigger_mode="simulated",
        shared_physical_camera=shared_physical_camera,
        channels={
            channel: DetectorChannelConfig(
                enabled=True,
                camera_role=(
                    "science"
                    if len(logical_channels) == 1
                    else f"science_{channel.lower()}"
                ),
                source_camera_id=camera_id,
            )
            for channel in logical_channels
        },
    )
