import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != 'nt', reason='PowerShell Windows launcher')
def test_launcher_rejects_occupied_port_without_killing_owner():
    shell = shutil.which('pwsh') or shutil.which('powershell')
    if shell is None:
        pytest.skip('PowerShell unavailable')
    root = Path(__file__).resolve().parents[2]
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        port = listener.getsockname()[1]
        result = subprocess.run([
            shell, '-NoProfile', '-File', str(root / 'start_ics.ps1'),
            '-Python', sys.executable, '-Config', 'config/cameras.sim.json',
            '-ForceSim', '-NoBrowser', '-Port', str(port),
        ], cwd=root, capture_output=True, timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode != 0
        assert b'occupied' in result.stdout + result.stderr
        with socket.create_connection(('127.0.0.1', port), timeout=2):
            pass
