"""Automatic exposure readout scheduling.

The detector owns integration timing. This task requests readout after the
requested duration; it does not assume that a delayed readout loses a frame.

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
        self._threads: set[threading.Thread] = set()

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
            self._threads.add(thread)
            # Starting under the lock prevents cancel/join seeing an unstarted thread.
            thread.start()
        return True

    def cancel(self) -> None:
        with self._lock:
            cancel = self._cancel
            self._thread = None
        if cancel is not None:
            cancel.set()
        # A caller may hold the Runtime transition lock needed by the callback.
        # Cancellation must never join that callback while holding this lock.

    def join(self, timeout_s: float = 2.0) -> None:
        deadline = time.monotonic() + timeout_s
        with self._lock:
            threads = tuple(self._threads)
        for thread in threads:
            if thread is not threading.current_thread():
                thread.join(max(0.0, deadline - time.monotonic()))
        with self._lock:
            self._threads = {thread for thread in self._threads if thread.is_alive()}

    def _run(
        self,
        duration_s: float,
        callback: Callable[[], None],
        cancel: threading.Event,
        description: str,
    ) -> None:
        try:
            self._wait_and_run(duration_s, callback, cancel, description)
        finally:
            with self._lock:
                self._threads.discard(threading.current_thread())

    def _wait_and_run(self, duration_s, callback, cancel, description) -> None:
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
