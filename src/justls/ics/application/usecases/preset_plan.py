from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from justls.ics.domain.detector.config import DetectorConfig

PresetCategory = Literal["science", "calibration", "engineering"]
PresetRiskLevel = Literal["normal", "high_impact", "engineering"]


class PresetCalibrationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str
    lamp: str | None = None
    enabled: bool = False


class PresetSlitPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width_um: float | None = None
    angle_deg: float | None = None


class PresetPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    summary: str
    category: PresetCategory
    risk_level: PresetRiskLevel = "normal"
    requires_confirmation: bool = False
    detector_config: DetectorConfig
    calibration: PresetCalibrationPlan | None = None
    slit: PresetSlitPlan | None = None

    def to_dict(self) -> dict:
        return self.model_dump()

    def list_item(self) -> dict:
        """Return the public catalog metadata for this preset.

        This keeps `/api/v1/presets` aligned with the executable preset plan
        without exposing the full detector/calibration payload in the list view.
        """
        return {
            "name": self.name,
            "summary": self.summary,
            "category": self.category,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
        }
