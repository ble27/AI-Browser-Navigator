#!/usr/bin/env python3
"""Install or uninstall the user-level macOS Chrome Native Messaging host."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from collections.abc import Sequence
from pathlib import Path

HOST_NAME = "com.ai_gestures.page_bridge"
EXTENSION_ID_PATTERN = re.compile(r"[a-p]{32}")


def chrome_manifest_path(home: Path) -> Path:
    """Return Chrome's user-level native host manifest path.

    Args:
        home: User home directory.

    Returns:
        Native Messaging host manifest path for Google Chrome on macOS.
    """
    return (
        home
        / "Library"
        / "Application Support"
        / "Google"
        / "Chrome"
        / "NativeMessagingHosts"
        / f"{HOST_NAME}.json"
    )


def launcher_path(home: Path) -> Path:
    """Return the installed executable launcher path.

    Args:
        home: User home directory.

    Returns:
        Private per-user launcher path.
    """
    return home / "Library" / "Application Support" / "AI Gestures Tool" / "native-host" / HOST_NAME


def install(extension_id: str, *, home: Path, python: Path) -> tuple[Path, Path]:
    """Install the launcher and Chrome host manifest.

    Args:
        extension_id: Explicit ID copied from Chrome's extensions page.
        home: User home directory.
        python: Current virtual environment's Python executable.

    Returns:
        ``(manifest_path, launcher_path)`` after successful installation.

    Raises:
        ValueError: If the extension ID is not a valid Chrome extension ID.
        FileNotFoundError: If the selected Python executable does not exist.
    """
    if EXTENSION_ID_PATTERN.fullmatch(extension_id) is None:
        raise ValueError("extension ID must be exactly 32 letters in the range a-p")
    # ``.venv/bin/python`` is normally a symlink to the base interpreter.
    # Resolve it only to verify that it exists; Chrome must execute the venv
    # path itself so Python loads that environment's installed packages.
    selected_python = python.expanduser()
    selected_python.resolve(strict=True)
    if not selected_python.is_absolute():
        selected_python = selected_python.absolute()
    installed_launcher = launcher_path(home)
    manifest = chrome_manifest_path(home)
    installed_launcher.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    launcher = (
        "#!/bin/sh\n"
        f"exec {shlex.quote(str(selected_python))} "
        '-m gesture_control.browser.native_host "$@"\n'
    )
    _atomic_write(installed_launcher, launcher, mode=0o700)
    manifest_data = {
        "name": HOST_NAME,
        "description": "AI Gestures local active-page bridge",
        "path": str(installed_launcher),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }
    _atomic_write(
        manifest,
        json.dumps(manifest_data, indent=2, sort_keys=True) + "\n",
        mode=0o600,
    )
    return manifest, installed_launcher


def uninstall(*, home: Path) -> tuple[Path, Path]:
    """Remove only the known manifest and launcher files.

    Args:
        home: User home directory.

    Returns:
        Paths targeted for removal.
    """
    manifest = chrome_manifest_path(home)
    installed_launcher = launcher_path(home)
    manifest.unlink(missing_ok=True)
    installed_launcher.unlink(missing_ok=True)
    return manifest, installed_launcher


def _atomic_write(path: Path, contents: str, *, mode: int) -> None:
    """Atomically replace a small installer-owned text file."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(contents, encoding="utf-8")
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    """Build the installer command-line parser.

    Returns:
        Parser with install and uninstall subcommands.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    install_parser = subparsers.add_parser("install", help="install the native host")
    install_parser.add_argument(
        "--extension-id",
        required=True,
        help="32-character unpacked extension ID copied from chrome://extensions",
    )
    subparsers.add_parser("uninstall", help="remove the native host")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the native host installer CLI.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Process exit status.
    """
    args = build_parser().parse_args(argv)
    home = Path.home()
    try:
        if args.command == "install":
            manifest, installed_launcher = install(
                args.extension_id,
                home=home,
                python=Path(sys.executable),
            )
            print(f"Installed launcher: {installed_launcher}")
            print(f"Installed Chrome manifest: {manifest}")
            print("Restart Chrome to reconnect the native host.")
        else:
            manifest, installed_launcher = uninstall(home=home)
            print(f"Removed if present: {manifest}")
            print(f"Removed if present: {installed_launcher}")
    except (OSError, ValueError) as exc:
        print(f"Native host installer: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
