from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run_installer(
    repo_root: Path, home: Path, *arguments: str
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    return subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "manage_chrome_native_host.py"),
            *arguments,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_installer_writes_allowlisted_manifest_and_executable_launcher(tmp_path: Path) -> None:
    repo_root = Path(__file__).parents[3]
    extension_id = "a" * 32

    result = _run_installer(
        repo_root,
        tmp_path,
        "install",
        "--extension-id",
        extension_id,
    )

    assert result.returncode == 0, result.stderr
    manifest_path = (
        tmp_path
        / "Library/Application Support/Google/Chrome/NativeMessagingHosts"
        / "com.ai_gestures.page_bridge.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    launcher = Path(manifest["path"])
    assert manifest["allowed_origins"] == [f"chrome-extension://{extension_id}/"]
    assert manifest["type"] == "stdio"
    assert launcher.is_file()
    assert os.access(launcher, os.X_OK)
    launcher_text = launcher.read_text(encoding="utf-8")
    assert str(Path(sys.executable)) in launcher_text
    assert "-m gesture_control.browser.native_host" in launcher_text

    uninstall_result = _run_installer(repo_root, tmp_path, "uninstall")

    assert uninstall_result.returncode == 0, uninstall_result.stderr
    assert not manifest_path.exists()
    assert not launcher.exists()


def test_installer_rejects_invalid_extension_id(tmp_path: Path) -> None:
    repo_root = Path(__file__).parents[3]

    result = _run_installer(
        repo_root,
        tmp_path,
        "install",
        "--extension-id",
        "not-an-extension-id",
    )

    assert result.returncode == 2
    assert "32 letters" in result.stderr
