"""Persistence for the operator-selected data root.

By default every saved frame lands under the ``data_root`` compiled into the
camera configuration (``var/data``), and that can only be overridden with the
``ICS_BETA_DATA_ROOT`` environment variable — which is fine for a lab box but
useless on a night when the observer wants the night's frames on a specific
disk or in a dated folder.

The selected root is therefore a first-class, operator-settable setting: it is
stored in ``.justls/output_location.json`` (mirroring the instrument-context
declaration) so that

- the API/UI can read and change it while the service is running, and
- the choice survives a restart without touching the config or the environment.

The same file also keeps a short ``recent_roots`` list so the UI can offer a
datalist of the last handful of paths the operator has used, which is the
closest thing to a folder picker a stock HTML form can give us.

Loading is deliberately fault-tolerant: a missing or corrupt file means "not
chosen yet" and falls back to the configured default rather than breaking
startup.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

OUTPUT_LOCATION_PATH_ENV = "JUSTLS_OUTPUT_LOCATION_PATH"
DEFAULT_OUTPUT_LOCATION_PATH = Path(".justls") / "output_location.json"
_DATA_ROOT_KEY = "data_root"
_RECENT_KEY = "recent_roots"
MAX_RECENT_ROOTS = 10


def get_output_location_path() -> Path:
    raw_path = os.getenv(OUTPUT_LOCATION_PATH_ENV)
    if raw_path and raw_path.strip():
        return Path(raw_path.strip())
    return DEFAULT_OUTPUT_LOCATION_PATH


def load_output_location(path: Path) -> str | None:
    """Return the persisted data root, or ``None`` when none is stored.

    A missing or corrupt file is not an error: the caller falls back to the
    configured default. A stored value that is not a non-empty string is
    treated the same way.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    raw = payload.get(_DATA_ROOT_KEY)
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip()


def load_recent_roots(path: Path) -> list[str]:
    """Return the persisted list of recently-used data roots (newest first).

    Garbage values are silently dropped; the caller is expected to treat the
    result as a UI hint, not as authoritative state.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    raw = payload.get(_RECENT_KEY)
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    cleaned: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            continue
        candidate = entry.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        cleaned.append(candidate)
        if len(cleaned) >= MAX_RECENT_ROOTS:
            break
    return cleaned


def _prune_recent(entries: list[str], current: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    if current:
        ordered.append(current)
        seen.add(current)
    for entry in entries:
        if entry in seen:
            continue
        seen.add(entry)
        ordered.append(entry)
        if len(ordered) >= MAX_RECENT_ROOTS:
            break
    return ordered


def save_output_location(
    path: Path,
    data_root: str,
    *,
    recent_roots: list[str] | None = None,
) -> list[str]:
    """Atomically persist the selected data root (temp file + replace).

    The current selection is promoted to the head of ``recent_roots`` so the
    UI's datalist can offer one-click re-use of the last handful of paths.
    Returns the trimmed recent-roots list actually written to disk.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = _prune_recent(list(recent_roots or []), data_root)
    payload = json.dumps(
        {_DATA_ROOT_KEY: data_root, _RECENT_KEY: merged},
        indent=2,
        ensure_ascii=False,
    )
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        stream.write(payload)
        temporary = Path(stream.name)
    os.replace(temporary, path)
    return merged
