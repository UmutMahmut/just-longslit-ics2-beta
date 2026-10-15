from __future__ import annotations

import sys
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# These env vars can dramatically change runtime behaviour (which camera
# config is loaded, whether the ZWO SDK is touched, whether the runtime
# runs in safe mode). A developer with one of these set in their shell is
# the legitimate target audience for the corresponding feature, but tests
# are *not* — a stray ``ICS_BETA_CAMERA_CONFIG`` in a developer's
# environment must not silently turn a hardware-free unit test into one
# that requires the real ZWO cameras. We therefore clear them at the
# start of the test session and restore whatever was there afterwards so
# the test process leaves the operator's shell untouched.
ENV_VARS_TO_ISOLATE = (
    "ICS_BETA_CAMERA_CONFIG",
    "ICS_BETA_FORCE_SIM",
    "ICS_BETA_HOTPLUG_INTERVAL_S",
    "ICS_ZWO_SDK_LIBRARY",
)


@pytest.fixture(scope="session", autouse=True)
def _isolate_beta_runtime_env():
    saved = {key: os.environ.pop(key, None) for key in ENV_VARS_TO_ISOLATE}
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(scope="session", autouse=True)
def _isolated_beta_data_root(tmp_path_factory):
    state_root = tmp_path_factory.mktemp("ics-beta-state")
    previous = os.environ.get("ICS_BETA_DATA_ROOT")
    previous_setup = os.environ.get("JUSTLS_SETUP_CONTEXT_PATH")
    previous_sequence = os.environ.get("JUSTLS_SEQUENCE_STATE_PATH")
    os.environ["ICS_BETA_DATA_ROOT"] = str(
        tmp_path_factory.mktemp("ics-beta-data")
    )
    os.environ["JUSTLS_SETUP_CONTEXT_PATH"] = str(
        state_root / "setup_context.json"
    )
    os.environ["JUSTLS_SEQUENCE_STATE_PATH"] = str(
        state_root / "sequence_execution.json"
    )
    yield
    if previous is None:
        os.environ.pop("ICS_BETA_DATA_ROOT", None)
    else:
        os.environ["ICS_BETA_DATA_ROOT"] = previous
    if previous_setup is None:
        os.environ.pop("JUSTLS_SETUP_CONTEXT_PATH", None)
    else:
        os.environ["JUSTLS_SETUP_CONTEXT_PATH"] = previous_setup
    if previous_sequence is None:
        os.environ.pop("JUSTLS_SEQUENCE_STATE_PATH", None)
    else:
        os.environ["JUSTLS_SEQUENCE_STATE_PATH"] = previous_sequence


@pytest.fixture(autouse=True)
def _auto_readout_disabled_by_default(monkeypatch):
    """Keep the existing command-lifecycle tests deterministic.

    Tests that explicitly exercise automatic readout opt in by setting
    JUSTLS_AUTO_READOUT_ENABLED=1 themselves.
    """
    monkeypatch.setenv("JUSTLS_AUTO_READOUT_ENABLED", "0")
    yield


@pytest.fixture(autouse=True)
def _clean_operator_state_between_tests():
    paths = [
        Path(os.environ["JUSTLS_SETUP_CONTEXT_PATH"]),
        Path(os.environ["JUSTLS_SEQUENCE_STATE_PATH"]),
    ]
    for path in paths:
        path.unlink(missing_ok=True)
    yield
    for path in paths:
        path.unlink(missing_ok=True)
