"""Exercise Windows pause/resume and console isolation without touching live AI."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows game mode")
ROOT = Path(__file__).resolve().parents[2]


def test_pause_resume_and_recovery(tmp_path):
    result = subprocess.run([
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
        str(ROOT / "tests/windows/test_cs2_game_mode.ps1"), "-TempDir", str(tmp_path),
    ], capture_output=True, text=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("extra_console_process", [False, True])
def test_console_interrupt_is_isolated(tmp_path, extra_console_process):
    python = sys._base_executable
    marker = tmp_path / "ready.json"
    stopped = tmp_path / "stopped"
    code = """
import json, os, signal, subprocess, sys, time
from pathlib import Path
done = False
def stop(*args):
    global done
    done = True
signal.signal(signal.SIGINT, stop)
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']) if sys.argv[3] == 'True' else None
Path(sys.argv[1]).write_text(json.dumps({'pid': os.getpid(), 'child': child.pid if child else None}))
try:
    while not done:
        time.sleep(0.05)
    Path(sys.argv[2]).write_text('graceful')
finally:
    if child:
        child.terminate()
        child.wait()
"""
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    child = subprocess.Popen([python, "-c", code, str(marker), str(stopped), str(extra_console_process)],
                             creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup)
    extra_pid = None
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.exists(), "Test child did not start"
        extra_pid = json.loads(marker.read_text())["child"]
        approved = tmp_path / "approved.json"
        approved.write_text(json.dumps([{"pid": child.pid, "path": python}]))
        result = subprocess.run([python, str(ROOT / "scripts/stop-ai-console.py"), str(child.pid), str(approved)],
                                capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        if extra_console_process:
            assert result.returncode != 0
            assert child.poll() is None, "Unrelated console membership was not protected"
            assert not stopped.exists()
        else:
            assert result.returncode == 0, result.stdout + result.stderr
            assert child.wait(timeout=10) == 0
            assert stopped.read_text() == "graceful"
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)
        if extra_pid:
            try:
                os.kill(extra_pid, signal.SIGTERM)
            except OSError:
                pass
