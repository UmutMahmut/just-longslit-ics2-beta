from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DetectorChannelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    camera_role: str | None = None
    source_camera_id: str | None = None


class DetectorChannelsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    B: DetectorChannelConfig = Field(
        default_factory=lambda: DetectorChannelConfig(
            enabled=False,
            camera_role="science_b",
        )
    )
    G: DetectorChannelConfig = Field(
        default_factory=lambda: DetectorChannelConfig(
            enabled=False,
            camera_role="science_g",
        )
    )
    R: DetectorChannelConfig = Field(
        default_factory=lambda: DetectorChannelConfig(
            enabled=False,
            camera_role="science_r",
        )
    )


class DetectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_name: str = "default"
    trigger_mode: Literal["internal", "external", "simulated"] = "internal"
    readout_mode: str = "normal"
    shared_physical_camera: bool = False
    channels: DetectorChannelsConfig = Field(default_factory=DetectorChannelsConfig)

    def to_dict(self) -> dict:
        return self.model_dump()


def build_default_detector_config() -> DetectorConfig:
    return DetectorConfig()


def build_beta_detector_config(camera_id: str) -> DetectorConfig:
    return DetectorConfig(
        profile_name="campus-beta-shared-camera",
        trigger_mode="simulated",
        shared_physical_camera=True,
        channels=DetectorChannelsConfig(
            B=DetectorChannelConfig(
                enabled=True,
                camera_role="science_b",
                source_camera_id=camera_id,
            ),
            G=DetectorChannelConfig(
                enabled=True,
                camera_role="science_g",
                source_camera_id=camera_id,
            ),
            R=DetectorChannelConfig(
                enabled=True,
                camera_role="science_r",
                source_camera_id=camera_id,
            ),
        ),
    )
