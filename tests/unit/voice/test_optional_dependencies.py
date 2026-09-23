"""Regression test that voice extras remain lazy for core-only installs."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_core_and_voice_modules_import_without_optional_audio_packages() -> None:
    """Importing modules must not eagerly import sounddevice or faster-whisper."""
    repo_root = Path(__file__).resolve().parents[3]
    script = """
import builtins

real_import = builtins.__import__

def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name.split(".", 1)[0] in {"sounddevice", "faster_whisper"}:
        raise ModuleNotFoundError(f"blocked optional dependency: {name}")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = guarded_import

import gesture_control
import gesture_control.app
import gesture_control.voice
import gesture_control.voice.agent
import gesture_control.voice.audio
import gesture_control.voice.transcription
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
