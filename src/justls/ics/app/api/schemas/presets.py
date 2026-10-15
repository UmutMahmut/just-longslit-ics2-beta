from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PresetApplyReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    confirmed: bool = False
