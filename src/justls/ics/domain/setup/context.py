from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping
import re


_ROOT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_DATE_PREFIX_RE = re.compile(r"^\d{8}$")


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _clean_text(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_root_name(value: str | None) -> str:
    root_name = _clean_text(value)
    if not root_name:
        raise ValueError("root_name must not be empty")
    if len(root_name) > 64:
        raise ValueError("root_name must be at most 64 characters")
    if not _ROOT_NAME_RE.match(root_name):
        raise ValueError(
            "root_name must start with an alphanumeric character and contain "
            "only alphanumeric characters, underscores, or hyphens"
        )
    return root_name


def _normalize_date_prefix(value: str | None) -> str:
    date_prefix = _clean_text(value).upper()
    if not date_prefix:
        raise ValueError("date_prefix must not be empty")
    if date_prefix == "AUTO":
        return date_prefix
    if not _DATE_PREFIX_RE.match(date_prefix):
        raise ValueError("date_prefix must be AUTO or an explicit YYYYMMDD token")
    return date_prefix


def _normalize_next_frame_index(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError("next_frame_index must be a positive integer")
    try:
        frame_index = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("next_frame_index must be a positive integer") from exc
    if frame_index < 1:
        raise ValueError("next_frame_index must be >= 1")
    return frame_index


def _coerce_observing_date(value: date | str | None) -> date:
    if value is None:
        return utc_today()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if _DATE_PREFIX_RE.match(cleaned):
            return date(
                year=int(cleaned[0:4]),
                month=int(cleaned[4:6]),
                day=int(cleaned[6:8]),
            )
        return date.fromisoformat(cleaned)
    raise ValueError("observing_date must be a date, ISO date string, YYYYMMDD, or None")


@dataclass(slots=True)
class SessionDataContext:
    observers: str = ""
    project_id: str = ""
    pi_name: str = ""
    support_operator: str = ""
    root_name: str = "justls"
    date_prefix: str = "AUTO"
    comment: str = ""
    next_frame_index: int = 1
    data_directory: str = ""

    def __post_init__(self) -> None:
        self.observers = _clean_text(self.observers)
        self.project_id = _clean_text(self.project_id)
        self.pi_name = _clean_text(self.pi_name)
        self.support_operator = _clean_text(self.support_operator)
        self.root_name = _normalize_root_name(self.root_name)
        self.date_prefix = _normalize_date_prefix(self.date_prefix)
        self.comment = _clean_text(self.comment)
        self.next_frame_index = _normalize_next_frame_index(self.next_frame_index)
        self.data_directory = _clean_text(self.data_directory)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SessionDataContext":
        return cls(
            observers=payload.get("observers", ""),
            project_id=payload.get("project_id", ""),
            pi_name=payload.get("pi_name", ""),
            support_operator=payload.get("support_operator", ""),
            root_name=payload.get("root_name", "justls"),
            date_prefix=payload.get("date_prefix", "AUTO"),
            comment=payload.get("comment", ""),
            next_frame_index=payload.get("next_frame_index", 1),
            data_directory=payload.get("data_directory", ""),
        )

    def resolved_date_prefix(self, observing_date: date | str | None = None) -> str:
        if self.date_prefix != "AUTO":
            return self.date_prefix
        return _coerce_observing_date(observing_date).strftime("%Y%m%d")

    def next_frame_token(self, observing_date: date | str | None = None) -> str:
        return f"{self.resolved_date_prefix(observing_date)}-{self.next_frame_index:04d}"

    def file_stem_preview(self, observing_date: date | str | None = None) -> str:
        date_token = self.resolved_date_prefix(observing_date)
        return f"{self.root_name}_{date_token}_{self.next_frame_index:04d}"

    def fits_filename_preview(self, observing_date: date | str | None = None) -> str:
        return f"{self.file_stem_preview(observing_date)}.fits"

    def data_preview(self, observing_date: date | str | None = None) -> dict[str, str]:
        return {
            "next_frame_token": self.next_frame_token(observing_date),
            "file_stem": self.file_stem_preview(observing_date),
            "fits_filename": self.fits_filename_preview(observing_date),
            "data_directory": self.data_directory,
        }

    def to_persisted_dict(self) -> dict[str, Any]:
        return {
            "observers": self.observers,
            "project_id": self.project_id,
            "pi_name": self.pi_name,
            "support_operator": self.support_operator,
            "root_name": self.root_name,
            "date_prefix": self.date_prefix,
            "comment": self.comment,
            "next_frame_index": self.next_frame_index,
            "data_directory": self.data_directory,
        }

    def to_dict(self, observing_date: date | str | None = None) -> dict[str, Any]:
        return {
            **self.to_persisted_dict(),
            **self.data_preview(observing_date),
        }
