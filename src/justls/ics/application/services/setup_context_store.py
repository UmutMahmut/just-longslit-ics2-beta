from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any, Protocol

from justls.ics.domain.setup import SessionDataContext


class SetupContextStore(Protocol):
    def load(self) -> SessionDataContext:
        ...

    def save(self, context: SessionDataContext) -> SessionDataContext:
        ...


class InMemorySetupContextStore:
    def __init__(self, context: SessionDataContext | None = None) -> None:
        self._context = self._copy_context(context or SessionDataContext())

    def load(self) -> SessionDataContext:
        return self._copy_context(self._context)

    def save(self, context: SessionDataContext) -> SessionDataContext:
        self._context = self._copy_context(context)
        return self.load()

    @staticmethod
    def _copy_context(context: SessionDataContext) -> SessionDataContext:
        return SessionDataContext.from_dict(context.to_persisted_dict())


class JsonSetupContextStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> SessionDataContext:
        if not self.path.exists():
            return SessionDataContext()

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid setup context JSON: {self.path}") from exc

        if not isinstance(payload, Mapping):
            raise ValueError(f"Setup context JSON must contain an object: {self.path}")

        return SessionDataContext.from_dict(payload)

    def save(self, context: SessionDataContext) -> SessionDataContext:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = context.to_persisted_dict()
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        tmp_path = self.path.with_name(f"{self.path.name}.tmp")
        tmp_path.write_text(text, encoding="utf-8")
        tmp_path.replace(self.path)
        return self.load()