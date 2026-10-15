"""Unit tests for :mod:`justls.ics.infra.hotplug`.

The monitor must:

* record a single count on construction (no need to wait for the first tick)
* notice when the SDK-visible count changes and stamp ``last_change_at``
* never auto-rebind: the only public surface is reading status
* not leak threads when ``stop()`` is called inside a tight window
* handle probe exceptions by stamping ``last_error`` without crashing
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from justls.ics.infra.hotplug import HotplugMonitor, HotplugSample, utc_now


class _CountingProbe:
    def __init__(self, *counts: int) -> None:
        self._counts = list(counts)
        self._calls = 0
        self._lock = threading.Lock()

    def __call__(self) -> int:
        with self._lock:
            if self._calls >= len(self._counts):
                return self._counts[-1]
            value = self._counts[self._calls]
            self._calls += 1
            return value

    @property
    def call_count(self) -> int:
        with self._lock:
            return self._calls


class _RaisingProbe:
    def __init__(self, message: str = "boom") -> None:
        self.message = message

    def __call__(self) -> int:
        raise RuntimeError(self.message)


def _build_clock() -> tuple[list[float], callable]:
    times = [0.0]

    def clock() -> float:
        return times[0]

    def advance(seconds: float) -> None:
        times[0] += seconds

    return times, clock


def test_construction_records_initial_count_and_timestamp() -> None:
    probe = _CountingProbe(2)
    monitor = HotplugMonitor(probe, interval_s=10.0)

    sample = monitor.sample()
    assert sample.count == 2
    assert sample.error is None
    assert isinstance(monitor.status_dict()["last_check_at"], str)
    assert monitor.status_dict()["last_count"] == 2
    # First observation is not a "change" — the monitor only stamps a change
    # event after comparing a fresh probe against the previous count.
    assert monitor.status_dict()["last_change_at"] is None


def test_change_detection_stamps_last_change_at() -> None:
    # The probe returns 2 forever. Even after multiple ticks, the change
    # detector must never stamp ``last_change_at`` because the count is
    # constant.
    probe = _CountingProbe(2)
    clock_times, clock = _build_clock()
    now_values = [
        datetime(2026, 10, 15, 14, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 15, 14, 0, 30, tzinfo=timezone.utc),
        datetime(2026, 10, 15, 14, 1, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 15, 14, 1, 30, tzinfo=timezone.utc),
    ]
    now_iter = iter(now_values)
    monitor = HotplugMonitor(
        probe, interval_s=10.0, clock=clock, utcnow=lambda: next(now_iter)
    )

    # Initial probe (construction) does not record a change.
    assert monitor.status_dict()["last_change_at"] is None

    monitor._tick()
    status = monitor.status_dict()
    assert status["last_count"] == 2
    assert status["last_change_at"] is None

    # Now probe returns 2 again; still no change.
    monitor._tick()
    assert monitor.status_dict()["last_change_at"] is None


def test_tick_creates_change_event_when_count_differs() -> None:
    # The probe first reports 2 (at construction), then 1 (at the first
    # tick). The first tick is the one that should record a change event.
    probe = _CountingProbe(2, 1)
    clock_times, clock = _build_clock()
    now_values = [
        datetime(2026, 10, 15, 14, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 15, 14, 0, 30, tzinfo=timezone.utc),
    ]
    now_iter = iter(now_values)
    monitor = HotplugMonitor(
        probe, interval_s=10.0, clock=clock, utcnow=lambda: next(now_iter)
    )

    monitor._tick()
    status = monitor.status_dict()
    assert status["last_count"] == 1
    assert status["last_change_at"] == now_values[1].isoformat()


def test_probe_exception_is_captured_in_last_error() -> None:
    probe = _RaisingProbe("USB pipe error")
    monitor = HotplugMonitor(probe, interval_s=10.0)

    monitor._tick()
    sample = monitor.sample()
    assert sample.error is not None
    assert "USB pipe error" in sample.error
    assert monitor.status_dict()["last_error"] is not None


def test_stop_terminates_background_thread_quickly() -> None:
    # Use a long interval so the test would hang for 60s without a fast stop.
    probe = _CountingProbe(2)
    monitor = HotplugMonitor(probe, interval_s=60.0)

    monitor.start()
    assert monitor.is_running()
    start = time.monotonic()
    monitor.stop(timeout_s=1.0)
    elapsed = time.monotonic() - start

    assert not monitor.is_running()
    assert elapsed < 2.0, f"stop() took {elapsed:.2f}s, should be sub-second"


def test_start_is_idempotent() -> None:
    probe = _CountingProbe(2)
    monitor = HotplugMonitor(probe, interval_s=60.0)

    monitor.start()
    first_thread = monitor._thread
    monitor.start()
    second_thread = monitor._thread
    monitor.stop()

    assert first_thread is second_thread


def test_status_dict_shape_is_stable_for_ui_consumers() -> None:
    probe = _CountingProbe(3)
    monitor = HotplugMonitor(probe, interval_s=15.0)

    status = monitor.status_dict()
    assert set(status.keys()) == {
        "enabled",
        "interval_s",
        "last_count",
        "last_check_at",
        "last_change_at",
        "last_error",
    }
    assert status["interval_s"] == 15.0


def test_zero_or_negative_interval_rejected() -> None:
    with pytest.raises(ValueError):
        HotplugMonitor(_CountingProbe(1), interval_s=0)
    with pytest.raises(ValueError):
        HotplugMonitor(_CountingProbe(1), interval_s=-1.0)
