"""Application service for the operator-declared instrument context."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from justls.ics.domain.setup.instrument import InstrumentContext
from justls.ics.infra.instrument_context import (
    load_instrument_context,
    save_instrument_context,
)


class InstrumentContextService:
    """Read/update the attended declaration of telescope+spectrograph state.

    Updates are validated, stamped (operator + UTC timestamp) and persisted
    atomically; the FITS writer picks them up on the next saved frame.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def get_context(self) -> InstrumentContext:
        if not self._path.is_file():
            return InstrumentContext()
        return load_instrument_context(self._path)

    def get_context_payload(self) -> dict[str, Any]:
        return self.get_context().to_dict()

    def save_context_payload(self, payload: Mapping[str, Any]) -> InstrumentContext:
        context = InstrumentContext.from_dict(payload)
        context.stamp(declared_by=context.declared_by or None)
        save_instrument_context(self._path, context)
        return context

    def reload_context(self) -> InstrumentContext:
        context = load_instrument_context(self._path)
        return context
