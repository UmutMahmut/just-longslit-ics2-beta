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
    previous = os.environ.get("ICS_BETA_DATA_ROOT")
    os.environ["ICS_BETA_DATA_ROOT"] = str(
        tmp_path_factory.mktemp("ics-beta-data")
    )
    yield
    if previous is None:
        os.environ.pop("ICS_BETA_DATA_ROOT", None)
    else:
        os.environ["ICS_BETA_DATA_ROOT"] = previous
