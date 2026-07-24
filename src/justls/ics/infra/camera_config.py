from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CAMERA_CONFIG_ENV = "ICS_BETA_CAMERA_CONFIG"
DATA_ROOT_ENV = "ICS_BETA_DATA_ROOT"
PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CAMERA_CONFIG_PATH = PROJECT_ROOT / "config" / "cameras.sim.json"


class CameraDeviceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1)
    role: Literal["science", "slit"]
    driver: Literal["simulated", "zwo"] = "simulated"
    manufacturer: str = "ZWO"
    model: str | None = None
    serial: str | None = None
    width: int = Field(default=640, ge=16)
    height: int = Field(default=480, ge=16)
    bit_depth: Literal[8, 10, 12, 14, 16] = 16
    gain: float = Field(default=100.0, ge=0)
    preview_exposure_ms: float = Field(default=100.0, gt=0)


class CameraSystemConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_name: str = "campus-beta-sim"
    data_root: str = "var/data"
    logical_science_channels: list[Literal["B", "G", "R"]] = Field(
        default_factory=lambda: ["B", "G", "R"]
    )
    science_camera: CameraDeviceConfig = Field(
        default_factory=lambda: CameraDeviceConfig(
            device_id="science-camera-01",
            role="science",
        )
    )
    slit_camera: CameraDeviceConfig = Field(
        default_factory=lambda: CameraDeviceConfig(
            device_id="slit-camera-01",
            role="slit",
            bit_depth=8,
        )
    )

    @model_validator(mode="after")
    def validate_roles_and_channels(self) -> "CameraSystemConfig":
        if self.science_camera.role != "science":
            raise ValueError("science_camera.role must be 'science'")
        if self.slit_camera.role != "slit":
            raise ValueError("slit_camera.role must be 'slit'")
        if self.science_camera.device_id == self.slit_camera.device_id:
            raise ValueError("science and slit cameras must use different device_id values")
        if set(self.logical_science_channels) != {"B", "G", "R"}:
            raise ValueError("logical_science_channels must contain B, G, and R exactly once")
        return self


def camera_config_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser().resolve()
    env_path = os.getenv(CAMERA_CONFIG_ENV)
    if env_path and env_path.strip():
        return Path(env_path.strip()).expanduser().resolve()
    return DEFAULT_CAMERA_CONFIG_PATH


def load_camera_system_config(
    path: str | Path | None = None,
) -> tuple[CameraSystemConfig, Path]:
    resolved_path = camera_config_path(path)
    if not resolved_path.exists():
        if path is not None or os.getenv(CAMERA_CONFIG_ENV):
            raise FileNotFoundError(f"Camera configuration not found: {resolved_path}")
        return CameraSystemConfig(), resolved_path
    return (
        CameraSystemConfig.model_validate_json(
            resolved_path.read_text(encoding="utf-8")
        ),
        resolved_path,
    )


def resolve_data_root(config: CameraSystemConfig, config_path: Path) -> Path:
    env_root = os.getenv(DATA_ROOT_ENV)
    raw_root = env_root.strip() if env_root and env_root.strip() else config.data_root
    root = Path(raw_root).expanduser()
    if root.is_absolute():
        return root.resolve()
    base = PROJECT_ROOT if config_path == DEFAULT_CAMERA_CONFIG_PATH else config_path.parent
    return (base / root).resolve()
