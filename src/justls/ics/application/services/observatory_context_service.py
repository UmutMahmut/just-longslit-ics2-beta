from __future__ import annotations

from justls.ics.domain.observatory.context import ObservatoryContext
from justls.ics.kernel.runtime import Runtime


class ObservatoryContextService:
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime

    def get_context(self) -> dict:
        return ObservatoryContext.default_unavailable(
            run_mode=self.runtime.config.run_mode.value,
        ).model_dump(mode="json")
