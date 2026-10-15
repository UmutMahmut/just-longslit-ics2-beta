"""Automatic exposure readout scheduling.

Real cameras do not wait for an operator: once the requested integration time
has elapsed the detector must be read out, otherwise the frame is lost (or, for
a camera that keeps exposing, the exposure simply never ends). The prototype
originally required an explicit ``finish`` command for every exposure, which
matched the simulator but is wrong for hardware operation.

The scheduler is deliberately tiny: it owns a single daemon thread per running
exposure and cancels it as soon as the exposure is completed by any other path
(manual finish, early stop, abort). It never touches detector state directly;
the caller supplies the completion callback.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)

AUTO_READOUT_ENV = "JUSTLS_AUTO_READOUT_ENABLED"


def auto_readout_enabled() -> bool:
    """Auto readout can be disabled for scripted/manual operation."""
    raw = os.getenv(AUTO_READOUT_ENV)
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "no", "off", "disabled"}


class AutoReadoutScheduler:
    """Runs ``callback`` once after ``duration_s`` unless cancelled."""

    def __init__(
        self,
        *,
        enabled: Callable[[], bool] = auto_readout_enabled,
        poll_interval_s: float = 0.05,
    ) -> None:
        self._enabled = enabled
        self._poll_interval_s = max(0.01, float(poll_interval_s))
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_error: str | None = None

    @property
    def active(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def schedule(
        self,
        *,
        duration_s: float,
        callback: Callable[[], None],
        description: str = "exposure",
    ) -> bool:
        """Schedule ``callback`` after ``duration_s``.

        Returns ``True`` when a timer was actually started. Only one timer is
        tracked at a time; scheduling again cancels the previous one.
        """
        duration_s = float(duration_s)
        if duration_s <= 0 or not self._enabled():
            return False

        self.cancel()
        cancel = threading.Event()
        with self._lock:
            self._cancel = cancel

        thread = threading.Thread(
            target=self._run,
            args=(duration_s, callback, cancel, description),
            name=f"auto-readout-{description}",
            daemon=True,
        )
        with self._lock:
            self._thread = thread
        thread.start()
        return True

    def cancel(self) -> None:
        with self._lock:
            cancel = self._cancel
            thread = self._thread
            self._thread = None
        if cancel is not None:
            cancel.set()
        if thread is not None and thread is not threading.current_thread():
            # Never join ourselves from inside the scheduled callback.
            thread.join(timeout=0.5)

    def _run(
        self,
        duration_s: float,
        callback: Callable[[], None],
        cancel: threading.Event,
        description: str,
    ) -> None:
        deadline = time.monotonic() + duration_s
        while not cancel.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            cancel.wait(min(self._poll_interval_s, remaining))

        if cancel.is_set():
            return

        # The camera may still be finishing its own integration; the driver's
        # finish path waits for the hardware, so call it directly.
        try:
            callback()
            self._last_error = None
        except Exception as exc:  # pragma: no cover - defensive
            self._last_error = f"{description} auto-readout failed: {exc}"
            logger.warning(self._last_error)
