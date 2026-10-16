"""Persistence helpers for the operator-declared instrument context.

The declared context lives in a small JSON file (default
``.justls/instrument_context.json``) so that:

- the API layer can read/update it (attended declaration entry point), and
- the FITS writer can stamp every saved frame with the *current* declared
  state without coupling the kernel runtime to the API layer.

Loading is deliberately fault-tolerant for the capture path: a missing or
corrupt declaration file must never block a science exposure — it simply
yields no instrument cards.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from justls.ics.domain.setup.instrument import InstrumentContext

INSTRUMENT_CONTEXT_PATH_ENV = "JUSTLS_INSTRUMENT_CONTEXT_PATH"
DEFAULT_INSTRUMENT_CONTEXT_PATH = Path(".justls") / "instrument_context.json"


def get_instrument_context_path() -> Path:
    raw_path = os.getenv(INSTRUMENT_CONTEXT_PATH_ENV)
    if raw_path and raw_path.strip():
        return Path(raw_path.strip())
    return DEFAULT_INSTRUMENT_CONTEXT_PATH


def load_instrument_context(path: Path) -> InstrumentContext:
    """Load and validate the declaration; raises ``ValueError`` if corrupt."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("instrument context file must contain a JSON object")
    return InstrumentContext.from_dict(payload)


def save_instrument_context(path: Path, context: InstrumentContext) -> None:
    """Atomically persist the declaration (temp file + replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        context.to_persisted_dict(),
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


def load_instrument_fits_cards(path: Path) -> dict[str, Any]:
    """FITS cards for the capture path; never raises.

    A missing/corrupt declaration file means "no instrument metadata
    declared yet", not "fail the exposure".
    """
    try:
        return load_instrument_context(path).to_fits_cards()
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
