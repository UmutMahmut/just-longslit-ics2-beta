import os
import shutil
import subprocess
from pathlib import Path
import pytest


def test_sequence_buttons_follow_background_completion():
    node = os.environ.get('ICS_TEST_NODE') or shutil.which('node')
    if not node:
        pytest.skip('Node is required for the frontend runtime regression')
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([node, 'tests/ui/scripts/sequence_state.cjs'], cwd=root, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr

def test_camera_settings_form_sends_changes_and_shows_readback():
    node = os.environ.get('ICS_TEST_NODE') or shutil.which('node')
    if not node:
        pytest.skip('Node is required for the frontend runtime regression')
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([node, 'tests/ui/scripts/acquisition_settings.cjs'], cwd=root, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
