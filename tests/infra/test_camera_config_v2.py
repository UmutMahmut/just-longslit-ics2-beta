from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from justls.ics.infra.camera_config import (
    CameraSystemConfig,
    DEFAULT_CAMERA_CONFIG_PATH,
    PROJECT_ROOT,
    load_camera_system_config,
)
from justls.ics.kernel.runtime import RuntimeAssembler, RuntimeConfig


def test_default_profile_uses_schema_v2_device_role_separation() -> None:
    config, path = load_camera_system_config()

    assert path == DEFAULT_CAMERA_CONFIG_PATH
    assert config.schema_version == 2
    assert config.science_camera.device_id == "science-camera-01"
    assert "role" not in config.science_camera.model_dump()
    assert config.science_binding.logical_channels == ["B", "G", "R"]
    assert config.science_binding.shared_capture is True
    assert config.slit_camera is not None


def test_legacy_v1_profile_is_migrated_in_memory() -> None:
    config = CameraSystemConfig.model_validate(
        {
            "profile_name": "legacy-test",
            "data_root": "var/data",
            "logical_science_channels": ["B", "G", "R"],
            "science_camera": {
                "device_id": "legacy-science",
                "role": "science",
                "driver": "simulated",
            },
            "slit_camera": {
                "device_id": "legacy-slit",
                "role": "slit",
                "driver": "simulated",
            },
        }
    )

    assert config.schema_version == 2
    assert [device.device_id for device in config.devices] == [
        "legacy-science",
        "legacy-slit",
    ]
    assert config.science_camera.device_id == "legacy-science"
    assert config.logical_science_channels == ["B", "G", "R"]


def test_single_channel_science_profile_can_omit_slit_camera(tmp_path) -> None:
    config_path = tmp_path / "single-science.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "profile_name": "generic-long-slit-test",
                "detector_profile_name": "single-science-detector",
                "data_root": "data",
                "devices": [
                    {
                        "device_id": "test-science-01",
                        "driver": "simulated",
                        "manufacturer": "TEST",
                        "width": 64,
                        "height": 32,
                        "bit_depth": 16,
                    }
                ],
                "role_bindings": [
                    {
                        "role": "science",
                        "device_id": "test-science-01",
                        "logical_channels": ["sci"],
                        "shared_capture": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    runtime = RuntimeAssembler(
        RuntimeConfig(camera_config_path=str(config_path))
    ).build()

    assert runtime.camera_config is not None
    assert runtime.camera_config.logical_science_channels == ["SCI"]
    assert runtime.slit_camera is None
    assert runtime.get_capabilities_dict()["slit_monitor_camera"] is False
    assert runtime.get_detector_config_dict()["profile_name"] == (
        "single-science-detector"
    )
    assert set(runtime.get_detector_config_dict()["channels"]) == {"SCI"}
    assert runtime.get_camera_status_dict()["bridge"] == {
        "physical_camera_id": "test-science-01",
        "logical_channels": ["SCI"],
        "shared_capture": False,
    }


def test_lhires_asi294_profile_is_explicitly_non_default() -> None:
    path = PROJECT_ROOT / "config" / "cameras.lhires-asi294.example.json"
    config, resolved = load_camera_system_config(path)

    assert resolved == path.resolve()
    assert resolved != DEFAULT_CAMERA_CONFIG_PATH
    assert config.profile_name == "test-50cm-lhires-asi294"
    assert config.science_camera.model == "ASI294MC Pro"
    assert config.logical_science_channels == ["SCI"]


def test_role_binding_must_reference_a_known_device() -> None:
    with pytest.raises(ValidationError, match="unknown device_id"):
        CameraSystemConfig.model_validate(
            {
                "schema_version": 2,
                "devices": [{"device_id": "science-01"}],
                "role_bindings": [
                    {
                        "role": "science",
                        "device_id": "missing",
                        "logical_channels": ["SCI"],
                    }
                ],
            }
        )


def test_multi_channel_binding_requires_shared_capture() -> None:
    with pytest.raises(ValidationError, match="shared_capture=true"):
        CameraSystemConfig.model_validate(
            {
                "schema_version": 2,
                "devices": [{"device_id": "science-01"}],
                "role_bindings": [
                    {
                        "role": "science",
                        "device_id": "science-01",
                        "logical_channels": ["B", "G", "R"],
                        "shared_capture": False,
                    }
                ],
            }
        )
