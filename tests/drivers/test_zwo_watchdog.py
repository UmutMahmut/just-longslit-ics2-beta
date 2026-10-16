"""Unit tests for the SDK call watchdog.

The watchdog is the safety net that prevents a stuck ZWO camera from
taking the entire uvicorn worker down. These tests exercise the
implementation directly (no real SDK required) so that future refactors
cannot silently weaken the timeout or skip it under load.
"""

from __future__ import annotations

import time

import pytest

from justls.ics.drivers.zwo.assembly import (
    SDK_HARDWARE_TIMEOUT_S,
    ZwoHardwareTimeoutError,
    _run_with_watchdog,
)


def test_watchdog_returns_value_when_call_completes_quickly() -> None:
    def fast() -> int:
        return 42

    result = _run_with_watchdog("fast", fast, timeout_s=2.0)

    assert result == 42


def test_watchdog_returns_value_when_call_raises() -> None:
    class _Boom(RuntimeError):
        pass

    def slow_error() -> None:
        raise _Boom("bad serial")

    with pytest.raises(_Boom, match="bad serial"):
        _run_with_watchdog("err", slow_error, timeout_s=2.0)


def test_watchdog_raises_timeout_when_call_hangs() -> None:
    def hangs() -> None:
        time.sleep(5.0)

    start = time.monotonic()
    with pytest.raises(ZwoHardwareTimeoutError) as excinfo:
        _run_with_watchdog("hang", hangs, timeout_s=0.2)
    elapsed = time.monotonic() - start

    assert excinfo.value.op_label == "hang"
    assert excinfo.value.timeout_s == pytest.approx(0.2)
    # Should bail out at the timeout, not after the full sleep.
    assert elapsed < 1.5, f"watchdog did not bound the call: {elapsed:.2f}s"


def test_watchdog_default_timeout_is_long_enough_for_hardware() -> None:
    # The default exists so call sites in assembly.py can rely on it; a
    # regression that shortens it would risk false positives on healthy
    # hosts. The constant is the contract.
    assert SDK_HARDWARE_TIMEOUT_S >= 2.0
    assert SDK_HARDWARE_TIMEOUT_S <= 30.0
