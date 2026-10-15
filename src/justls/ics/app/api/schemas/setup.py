from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SetupContextUpdateReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observers: str = ""
    project_id: str = ""
    pi_name: str = ""
    support_operator: str = ""
    root_name: str = "justls"
    date_prefix: str = "AUTO"
    comment: str = ""
    next_frame_index: int = Field(default=1, ge=1)
    data_directory: str = ""