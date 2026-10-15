from __future__ import annotations

import time

from justls.ics.application.services.exposure_auto_readout import (
    AutoReadoutScheduler,
)


class _Recorder:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> None:
        self.calls += 1


def test_scheduler_runs_callback_after_duration() -> None:
    recorder = _Recorder()
    scheduler = AutoReadoutScheduler(enabled=lambda: True, poll_interval_s=0.01)

    assert scheduler.schedule(duration_s=0.05, callback=recorder) is True
    assert scheduler.active is True

    deadline = time.monotonic() + 2.0
    while scheduler.active and time.monotonic() < deadline:
        time.sleep(0.01)

    assert recorder.calls == 1
    assert scheduler.last_error is None


def test_scheduler_cancel_prevents_callback() -> None:
    recorder = _Recorder()
    scheduler = AutoReadoutScheduler(enabled=lambda: True, poll_interval_s=0.01)

    scheduler.schedule(duration_s=0.05, callback=recorder)
    scheduler.cancel()
    time.sleep(0.15)

    assert recorder.calls == 0
    assert scheduler.active is False


def test_scheduler_disabled_does_not_schedule() -> None:
    recorder = _Recorder()
    scheduler = AutoReadoutScheduler(enabled=lambda: False)

    assert scheduler.schedule(duration_s=0.01, callback=recorder) is False
    assert scheduler.active is False
    time.sleep(0.05)
    assert recorder.calls == 0


def test_scheduler_replaces_pending_timer() -> None:
    first = _Recorder()
    second = _Recorder()
    scheduler = AutoReadoutScheduler(enabled=lambda: True, poll_interval_s=0.01)

    scheduler.schedule(duration_s=5.0, callback=first)
    scheduler.schedule(duration_s=5.0, callback=second)
    scheduler.cancel()

    assert first.calls == 0
    assert second.calls == 0


def test_scheduler_reports_callback_failure_without_raising() -> None:
    def boom() -> None:
        raise RuntimeError("camera gone")

    scheduler = AutoReadoutScheduler(enabled=lambda: True, poll_interval_s=0.01)
    scheduler.schedule(duration_s=0.02, callback=boom)

    deadline = time.monotonic() + 2.0
    while scheduler.active and time.monotonic() < deadline:
        time.sleep(0.01)

    assert scheduler.last_error is not None
    assert "camera gone" in scheduler.last_error
