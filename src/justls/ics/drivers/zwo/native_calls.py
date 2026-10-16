"""Bound native waits and quarantine a DLL after an unresolved native call.

A timed-out ctypes call cannot be interrupted safely in Python. Its arguments
stay owned by the daemon worker until it returns. All SDK objects loading the
same real DLL share this gate; after timeout no new calls, including close or
rebind, enter that DLL in this process. Recovery requires a service restart.
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Callable, Any

SDK_HARDWARE_TIMEOUT_S = 8.0


class ZwoHardwareTimeoutError(TimeoutError):
    def __init__(self, op_label: str, timeout_s: float) -> None:
        self.op_label = op_label
        self.timeout_s = timeout_s
        super().__init__(f"{op_label} did not return within {timeout_s:g}s; SDK quarantined; restart the service")


class ZwoSdkQuarantinedError(RuntimeError):
    pass


@dataclass
class _Call:
    label: str
    fn: Callable
    done: threading.Event = field(default_factory=threading.Event)
    value: Any = None
    error: BaseException | None = None


class NativeCallGate:
    def __init__(self, timeout_s: float = SDK_HARDWARE_TIMEOUT_S) -> None:
        self.timeout_s = timeout_s
        self._lock = threading.Lock()
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._quarantined: str | None = None

    def _run(self) -> None:
        while True:
            call = self._queue.get()
            try:
                call.value = call.fn()
            except BaseException as exc:
                call.error = exc
            finally:
                call.done.set()

    def call(self, label: str, fn: Callable):
        with self._lock:
            if self._quarantined:
                raise ZwoSdkQuarantinedError(self._quarantined)
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="zwo-native", daemon=True)
                self._thread.start()
            call = _Call(label, fn)
            self._queue.put(call)
            if not call.done.wait(self.timeout_s):
                error = ZwoHardwareTimeoutError(label, self.timeout_s)
                self._quarantined = str(error)
                raise error
            if call.error is not None:
                if isinstance(call.error, OSError):
                    self._quarantined = f"Native SDK failure: {call.error}; restart the service"
                raise call.error
            return call.value


class GuardedLibrary:
    def __init__(self, library, gate: NativeCallGate) -> None:
        self._library = library
        self._gate = gate

    def __getattr__(self, name):
        native = getattr(self._library, name)

        def invoke(*args):
            # The closure owns ctypes pointer/buffer objects even after timeout.
            return self._gate.call(name, lambda: native(*args))

        return invoke


_gates: dict[str, NativeCallGate] = {}
_gates_lock = threading.Lock()


def shared_gate(path: str) -> NativeCallGate:
    with _gates_lock:
        return _gates.setdefault(path, NativeCallGate())


def _run_with_watchdog(op_label, fn, *, timeout_s=SDK_HARDWARE_TIMEOUT_S):
    """Standalone helper for compatibility; production gates persist per DLL."""
    return NativeCallGate(timeout_s).call(op_label, fn)
