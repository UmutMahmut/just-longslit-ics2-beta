from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SlitReq(BaseModel):
    width_um: float = Field(..., gt=0)


class SlitAngleReq(BaseModel):
    angle_deg: float = Field(..., ge=-90, le=90)


class LampReq(BaseModel):
    on: bool


class CalibrationModeReq(BaseModel):
    mode: Literal["science", "calibration"]


class CalibrationLampReq(BaseModel):
    lamp: Literal["flat", "arc_hgar", "arc_ne"]
    enabled: bool = True