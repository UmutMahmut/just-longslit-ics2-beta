from threading import Event

import pytest

from justls.ics.drivers.zwo.native_calls import (
    NativeCallGate, GuardedLibrary, ZwoHardwareTimeoutError, ZwoSdkQuarantinedError,
)


def test_timeout_quarantines_every_caller_even_after_late_return():
    release = Event()
    finished = Event()
    gate = NativeCallGate(timeout_s=0.03)
    calls = []

    def hung():
        try:
            release.wait(2)
            calls.append('native completed')
        finally:
            finished.set()

    try:
        with pytest.raises(ZwoHardwareTimeoutError):
            gate.call('open', hung)
        with pytest.raises(ZwoSdkQuarantinedError):
            gate.call('close', lambda: calls.append('unsafe close'))
    finally:
        release.set()
    assert finished.wait(2)
    with pytest.raises(ZwoSdkQuarantinedError):
        gate.call('rebind', lambda: calls.append('unsafe rebind'))
    assert calls == ['native completed']


def test_multiple_library_wrappers_share_quarantine():
    from types import SimpleNamespace
    release = Event()
    gate = NativeCallGate(timeout_s=0.03)
    first = GuardedLibrary(SimpleNamespace(open=lambda: release.wait(2)), gate)
    second = GuardedLibrary(SimpleNamespace(close=lambda: pytest.fail('native close entered')), gate)
    try:
        with pytest.raises(ZwoHardwareTimeoutError):
            first.open()
        with pytest.raises(ZwoSdkQuarantinedError):
            second.close()
    finally:
        release.set()


def test_native_access_violation_quarantines_session():
    gate = NativeCallGate()

    def crash():
        raise OSError('access violation')

    with pytest.raises(OSError):
        gate.call('enumerate', crash)
    with pytest.raises(ZwoSdkQuarantinedError):
        gate.call('close', lambda: pytest.fail('unsafe call'))
