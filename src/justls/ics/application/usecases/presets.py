from __future__ import annotations

from justls.ics.application.usecases.preset_plan import (
    PresetCalibrationPlan,
    PresetPlan,
    PresetSlitPlan,
)
from justls.ics.domain.detector.config import DetectorConfig


def build_science_default_preset() -> PresetPlan:
    return PresetPlan(
        name="science_default",
        summary="All RGB channels enabled for nominal science-mode detector configuration.",
        category="science",
        risk_level="normal",
        requires_confirmation=False,
        detector_config=DetectorConfig.model_validate(
            {
                "profile_name": "science-default",
                "trigger_mode": "internal",
                "readout_mode": "normal",
                "channels": {
                    "B": {"enabled": True, "camera_role": "science_b"},
                    "G": {"enabled": True, "camera_role": "science_g"},
                    "R": {"enabled": True, "camera_role": "science_r"},
                },
            }
        ),
        calibration=PresetCalibrationPlan(
            mode="science",
            lamp=None,
            enabled=False,
        ),
        slit=None,
    )


def build_rgb_safe_default_preset() -> PresetPlan:
    return PresetPlan(
        name="rgb_safe_default",
        summary="Conservative RGB-safe preset with B/R enabled and G disabled.",
        category="science",
        risk_level="normal",
        requires_confirmation=False,
        detector_config=DetectorConfig.model_validate(
            {
                "profile_name": "rgb-safe-default",
                "trigger_mode": "internal",
                "readout_mode": "normal",
                "channels": {
                    "B": {"enabled": True, "camera_role": "science_b"},
                    "G": {"enabled": False, "camera_role": "science_g"},
                    "R": {"enabled": True, "camera_role": "science_r"},
                },
            }
        ),
        calibration=PresetCalibrationPlan(
            mode="science",
            lamp=None,
            enabled=False,
        ),
        slit=None,
    )


def build_engineering_all_channels_off_preset() -> PresetPlan:
    return PresetPlan(
        name="engineering_all_channels_off",
        summary="Engineering-safe preset with all RGB channels disabled.",
        category="engineering",
        risk_level="engineering",
        requires_confirmation=True,
        detector_config=DetectorConfig.model_validate(
            {
                "profile_name": "engineering-all-off",
                "trigger_mode": "simulated",
                "readout_mode": "normal",
                "channels": {
                    "B": {"enabled": False, "camera_role": "science_b"},
                    "G": {"enabled": False, "camera_role": "science_g"},
                    "R": {"enabled": False, "camera_role": "science_r"},
                },
            }
        ),
        calibration=PresetCalibrationPlan(
            mode="science",
            lamp=None,
            enabled=False,
        ),
        slit=None,
    )


def build_calib_flat_default_preset() -> PresetPlan:
    return PresetPlan(
        name="calib_flat_default",
        summary="Default flat-calibration preset with calibration mode and flat lamp enabled.",
        category="calibration",
        risk_level="high_impact",
        requires_confirmation=True,
        detector_config=DetectorConfig.model_validate(
            {
                "profile_name": "calib-flat-default",
                "trigger_mode": "internal",
                "readout_mode": "normal",
                "channels": {
                    "B": {"enabled": True, "camera_role": "science_b"},
                    "G": {"enabled": True, "camera_role": "science_g"},
                    "R": {"enabled": True, "camera_role": "science_r"},
                },
            }
        ),
        calibration=PresetCalibrationPlan(
            mode="calibration",
            lamp="flat",
            enabled=True,
        ),
        slit=None,
    )


PRESET_BUILDERS = {
    "science_default": build_science_default_preset,
    "rgb_safe_default": build_rgb_safe_default_preset,
    "engineering_all_channels_off": build_engineering_all_channels_off_preset,
    "calib_flat_default": build_calib_flat_default_preset,
}


def list_presets() -> list[dict]:
    return [build_preset_plan(name).list_item() for name in PRESET_BUILDERS]


def build_preset_plan(name: str) -> PresetPlan:
    try:
        builder = PRESET_BUILDERS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown preset: {name}") from exc
    return builder()


def build_preset_config(name: str) -> DetectorConfig:
    return build_preset_plan(name).detector_config
