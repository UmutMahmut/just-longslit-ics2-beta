"""Background hot-plug monitor for the ZWO SDK.

The ZWO vendor library can leave an open process in a bad state when a camera
is unplugged, replugged, or the host USB stack resets. We do not want the
service to silently keep an exclusive handle on a camera that the operator
just pulled, nor do we want to thrash a re-bind during an exposure.

The monitor periodically asks the SDK how many cameras it currently sees
(``ASIGetNumOfConnectedCameras``). The numbers, the timestamp of the last
check, and the timestamp of the last change are surfaced through
``/api/v1/cameras/status`` so the operator console can render a banner
("USB changed at 14:25") and prompt the user to ``POST /api/v1/cameras/reload``
to perform a controlled re-bind. We never auto-rebind because a re-bind
releases every camera handle and aborts any in-flight exposure.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional


logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class HotplugSample:
    """One observation captured by the monitor."""

    count: int
    checked_at: datetime
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "count": self.count,
            "checked_at": self.checked_at.isoformat(),
            "error": self.error,
        }


class HotplugMonitor:
    """A small watchdog thread that asks the SDK how many cameras it sees.

    The monitor is *advisory only*: it never rebinds drivers, never aborts
    exposures, and never mutates the runtime state machine. It exists so the
    operator can see "something changed under me" and decide what to do.
    """

    def __init__(
        self,
        probe: Callable[[], int],
        *,
        interval_s: float = 30.0,
        initial_count: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = utc_now,
    ) -> None:
        if interval_s <= 0:
            raise ValueError("interval_s must be positive")
        self._probe = probe
        self._interval_s = float(interval_s)
        self._clock = clock
        self._utcnow = utcnow
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        initial = self._safe_probe()
        # We do not stamp ``last_change_at`` at construction: simply observing
        # the USB bus for the first time is not a "change" from the operator's
        # point of view. A change event must come from a later ``_tick`` that
        # actually compared a freshly-probed count against the previous one.
        self._last_count: int | None = initial
        self._last_checked_at: datetime | None = self._utcnow()
        self._last_change_at: datetime | None = None
        self._last_error: str | None = None

    # -- public surface -----------------------------------------------------

    def start(self) -> None:
        """Start the background polling thread. Idempotent."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        thread = threading.Thread(
            target=self._run,
            name="ics-beta-hotplug",
            daemon=True,
        )
        self._thread = thread
        thread.start()

    def stop(self, *, timeout_s: float = 2.0) -> None:
        """Signal the background thread to stop and wait briefly."""
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=timeout_s)
        self._thread = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def sample(self) -> HotplugSample:
        with self._lock:
            return HotplugSample(
                count=-1 if self._last_count is None else int(self._last_count),
                checked_at=self._last_checked_at,
                error=self._last_error,
            )

    def status_dict(self) -> dict[str, object]:
        sample = self.sample()
        with self._lock:
            last_change = self._last_change_at.isoformat() if self._last_change_at else None
            last_count = self._last_count
        return {
            "enabled": self.is_running(),
            "interval_s": self._interval_s,
            "last_count": last_count,
            "last_check_at": sample.checked_at.isoformat(),
            "last_change_at": last_change,
            "last_error": sample.error,
        }

    # -- helpers ------------------------------------------------------------

    def _safe_probe(self) -> int | None:
        try:
            value = int(self._probe())
        except Exception as exc:  # pragma: no cover - defensive
            with self._lock:
                self._last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("hotplug probe failed: %s", exc)
            return None
        with self._lock:
            self._last_error = None
        return value

    def _tick(self) -> None:
        count = self._safe_probe()
        now = self._utcnow()
        with self._lock:
            previous = self._last_count
            self._last_checked_at = now
            if count is not None and count != previous:
                self._last_count = count
                self._last_change_at = now

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("hotplug tick crashed: %s", exc)
            # Sleep in small slices so shutdown does not have to wait the full
            # interval for the join to return.
            end = self._clock() + self._interval_s
            while not self._stop_event.is_set() and self._clock() < end:
                self._stop_event.wait(0.5)


def make_probe(sdk) -> Callable[[], int]:
    """Build a probe closure that always goes through the SDK enumeration lock.

    Passing a callable (instead of the SDK object) keeps ``HotplugMonitor``
    test-friendly: tests can swap the probe with a stub.
    """
    def _probe() -> int:
        return sdk.connected_camera_count()
    return _probe
