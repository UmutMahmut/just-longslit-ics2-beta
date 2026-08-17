from __future__ import annotations

import sys
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


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
