from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CAMERA_CONFIG_ENV = "ICS_BETA_CAMERA_CONFIG"
DATA_ROOT_ENV = "ICS_BETA_DATA_ROOT"
PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CAMERA_CONFIG_PATH = PROJECT_ROOT / "config" / "cameras.sim.json"
CHANNEL_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]{0,15}$")


class CameraDeviceConfig(BaseModel):
    """Physical camera identity and device-level acquisition defaults."""

    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1)
    driver: Literal["simulated", "zwo"] = "simulated"
    manufacturer: str | None = None
    model: str | None = None
    serial: str | None = None
    width: int = Field(default=640, ge=16)
    height: int = Field(default=480, ge=16)
    bit_depth: Literal[8, 10, 12, 14, 16] = 16
    gain: float = Field(default=100.0, ge=0)
    preview_exposure_ms: float = Field(default=100.0, gt=0)


class CameraRoleBinding(BaseModel):
    """Deployment-specific assignment of a physical device to an ICS role."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["science", "slit"]
    device_id: str = Field(min_length=1)
    logical_channels: list[str] = Field(default_factory=list)
    shared_capture: bool = False

    @field_validator("logical_channels")
    @classmethod
    def normalize_logical_channels(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().upper() for value in values]
        if any(not CHANNEL_NAME_PATTERN.fullmatch(value) for value in normalized):
            raise ValueError(
                "logical channel names must begin with A-Z and contain only "
                "A-Z, 0-9, underscore, or hyphen"
            )
        if len(normalized) != len(set(normalized)):
            raise ValueError("logical channel names must be unique within a role")
        return normalized


def _default_devices() -> list[CameraDeviceConfig]:
    return [
        CameraDeviceConfig(
            device_id="science-camera-01",
            manufacturer="SIMULATED",
        ),
        CameraDeviceConfig(
            device_id="slit-camera-01",
            manufacturer="SIMULATED",
            bit_depth=8,
        ),
    ]


def _default_role_bindings() -> list[CameraRoleBinding]:
    return [
        CameraRoleBinding(
            role="science",
            device_id="science-camera-01",
            logical_channels=["B", "G", "R"],
            shared_capture=True,
        ),
        CameraRoleBinding(
            role="slit",
            device_id="slit-camera-01",
        ),
    ]


class CameraSystemConfig(BaseModel):
    """Schema v2 camera topology with legacy v1 input migration."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    profile_name: str = "campus-beta-sim"
    detector_profile_name: str | None = None
    data_root: str = "var/data"
    devices: list[CameraDeviceConfig] = Field(default_factory=_default_devices)
    role_bindings: list[CameraRoleBinding] = Field(
        default_factory=_default_role_bindings
    )

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_v1(cls, raw: Any) -> Any:
        if not isinstance(raw, dict) or "devices" in raw or "role_bindings" in raw:
            return raw
        if "science_camera" not in raw:
            return raw

        migrated = dict(raw)
        logical_channels = migrated.pop(
            "logical_science_channels", ["B", "G", "R"]
        )
        science = dict(migrated.pop("science_camera"))
        slit_raw = migrated.pop("slit_camera", None)
        science.pop("role", None)

        devices = [science]
        bindings = [
            {
                "role": "science",
                "device_id": science["device_id"],
                "logical_channels": logical_channels,
                "shared_capture": len(logical_channels) > 1,
            }
        ]
        if slit_raw is not None:
            slit = dict(slit_raw)
            slit.pop("role", None)
            devices.append(slit)
            bindings.append(
                {
                    "role": "slit",
                    "device_id": slit["device_id"],
                }
            )

        migrated["schema_version"] = 2
        migrated["devices"] = devices
        migrated["role_bindings"] = bindings
        return migrated

    @model_validator(mode="after")
    def validate_topology(self) -> "CameraSystemConfig":
        device_ids = [device.device_id for device in self.devices]
        if len(device_ids) != len(set(device_ids)):
            raise ValueError("camera device_id values must be unique")

        roles = [binding.role for binding in self.role_bindings]
        if len(roles) != len(set(roles)):
            raise ValueError("camera roles may be bound at most once")
        if "science" not in roles:
            raise ValueError("a science-camera role binding is required")

        known_devices = set(device_ids)
        for binding in self.role_bindings:
            if binding.device_id not in known_devices:
                raise ValueError(
                    f"camera role {binding.role!r} references unknown device_id "
                    f"{binding.device_id!r}"
                )
            if binding.role == "science" and not binding.logical_channels:
                raise ValueError("the science role must define logical_channels")
            if binding.role == "slit" and binding.logical_channels:
                raise ValueError("the slit role must not define logical_channels")
            if len(binding.logical_channels) > 1 and not binding.shared_capture:
                raise ValueError(
                    "a physical camera feeding multiple logical channels must use "
                    "shared_capture=true"
                )
        return self

    def binding_for(self, role: Literal["science", "slit"]) -> CameraRoleBinding | None:
        return next(
            (binding for binding in self.role_bindings if binding.role == role),
            None,
        )

    def device_for(self, role: Literal["science", "slit"]) -> CameraDeviceConfig | None:
        binding = self.binding_for(role)
        if binding is None:
            return None
        return next(
            device for device in self.devices if device.device_id == binding.device_id
        )

    @property
    def science_binding(self) -> CameraRoleBinding:
        binding = self.binding_for("science")
        if binding is None:  # protected by validate_topology
            raise RuntimeError("science-camera role binding is unavailable")
        return binding

    @property
    def slit_binding(self) -> CameraRoleBinding | None:
        return self.binding_for("slit")

    @property
    def science_camera(self) -> CameraDeviceConfig:
        device = self.device_for("science")
        if device is None:  # protected by validate_topology
            raise RuntimeError("science-camera device is unavailable")
        return device

    @property
    def slit_camera(self) -> CameraDeviceConfig | None:
        return self.device_for("slit")

    @property
    def logical_science_channels(self) -> list[str]:
        return list(self.science_binding.logical_channels)


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
