from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OutputLocationResponse(BaseModel):
    """Where saved science frames are written.

    ``data_root`` is the folder that receives ``<root>/<YYYYMMDD>/<obs-id>/``;
    ``writable`` is the service's best-effort check at response time, not a
    guarantee that a later write will succeed (the disk may fill up).
    ``recent_roots`` is the last handful of selections, newest first; the UI
    uses it to power a datalist so the operator does not have to retype the
    same path twice.
    """

    model_config = ConfigDict(extra="forbid")

    data_root: str = ""
    exists: bool = False
    writable: bool = False
    message: str | None = None
    recent_roots: list[str] = Field(default_factory=list)


class OutputLocationUpdateReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_root: str = Field(..., min_length=1)
