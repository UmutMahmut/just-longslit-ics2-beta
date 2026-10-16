from pydantic import BaseModel, ConfigDict, Field


class CameraSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gain: int | None = Field(default=None, ge=0)
    offset: int | None = Field(default=None, ge=0)
    binning: int | None = Field(default=None, ge=1, le=4)
    width: int | None = Field(default=None, ge=16)
    height: int | None = Field(default=None, ge=16)
    preview_exposure_ms: float | None = Field(default=None, gt=0, le=10000, allow_inf_nan=False)
    cooler_enabled: bool | None = None
    cooler_target_c: int | None = None
