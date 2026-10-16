"""Operator-facing control over where science frames are written.

Saving is opt-in per exposure (the "Save science frames to disk" tickbox), but
until now the destination itself was fixed at process start by the
configuration or the ``ICS_BETA_DATA_ROOT`` environment variable. An observer
who wants tonight's frames in ``D:\\observations\\20261014`` had to restart the
service with a different environment.

This service makes the destination a runtime setting: it validates the folder,
creates it when needed, applies it to the live runtime (so the very next readout
uses it) and persists it for the next start.
"""

from __future__ import annotations

import os
from pathlib import Path

from justls.ics.infra.output_location import (
    get_output_location_path,
    load_output_location,
    load_recent_roots,
    save_output_location,
)


class OutputLocationError(ValueError):
    """The requested data root cannot be used."""


class OutputLocationService:
    def __init__(self, runtime, path: Path | None = None) -> None:
        self._runtime = runtime
        self._path = path if path is not None else get_output_location_path()

    # -- read ---------------------------------------------------------------
    def get_payload(self) -> dict[str, object]:
        return self._describe(self._current_raw(), self._recent())

    def _current_raw(self) -> str:
        # The runtime is authoritative while the service is up: it reflects the
        # last applied choice even before it hits disk.
        raw = getattr(self._runtime, "data_root", None)
        if raw:
            return str(raw)
        return load_output_location(self._path) or ""

    def _recent(self) -> list[str]:
        return load_recent_roots(self._path)

    def _describe(self, raw: str, recent: list[str]) -> dict[str, object]:
        if not raw:
            return {
                "data_root": "",
                "exists": False,
                "writable": False,
                "message": "no output directory selected; using the configured default",
                "recent_roots": recent,
            }
        root = Path(raw)
        exists = root.is_dir()
        writable = exists and os.access(root, os.W_OK)
        if not exists:
            message = "output directory does not exist yet; it is created on apply"
        elif not writable:
            message = "output directory is not writable"
        else:
            message = "output directory ready"
        return {
            "data_root": str(root),
            "exists": exists,
            "writable": writable,
            "message": message,
            "recent_roots": recent,
        }

    # -- write --------------------------------------------------------------
    def set_data_root(self, raw: str) -> dict[str, object]:
        candidate = self._validate(raw)
        self._runtime.set_data_root(candidate)
        # The current selection is promoted to the head of the recent list;
        # the service keeps up to MAX_RECENT_ROOTS unique paths so the UI
        # datalist stays useful across a long observing run.
        recent = save_output_location(
            self._path,
            str(candidate),
            recent_roots=self._recent(),
        )
        return self._describe(str(candidate), recent)

    def _validate(self, raw: str) -> Path:
        if not isinstance(raw, str) or not raw.strip():
            raise OutputLocationError("data_root must be a non-empty path.")
        if "\x00" in raw:
            raise OutputLocationError("data_root must not contain NUL characters.")

        candidate = Path(raw.strip()).expanduser()
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        else:
            candidate = candidate.resolve()

        if candidate.exists() and not candidate.is_dir():
            raise OutputLocationError(
                f"output location exists but is not a directory: {candidate}"
            )

        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OutputLocationError(
                f"output directory could not be created: {candidate} ({exc})"
            ) from exc

        if not os.access(candidate, os.W_OK):
            raise OutputLocationError(
                f"output directory is not writable: {candidate}"
            )
        return candidate
