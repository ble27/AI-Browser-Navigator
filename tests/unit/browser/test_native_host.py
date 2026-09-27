"""Tests for Native Messaging host startup behavior."""

from __future__ import annotations

from pathlib import Path

from gesture_control.browser import native_host


class _Socket:
    """Socket fake that records close calls and can fail one connect."""

    def __init__(self, failures: list[bool]) -> None:
        self._failures = failures
        self.closed = False

    def connect(self, _path: str) -> None:
        """Fail until the configured app socket becomes available."""
        if self._failures.pop(0):
            raise FileNotFoundError("socket not ready")

    def close(self) -> None:
        """Record closing a failed connection."""
        self.closed = True


def test_connect_to_app_socket_retries_startup_race(monkeypatch: object) -> None:
    """Host stays alive when Chrome starts it before the app socket exists."""
    failures = [True, False]
    sockets: list[_Socket] = []
    sleeps: list[float] = []

    def make_socket(_family: int, _kind: int) -> _Socket:
        """Create a fake Unix socket."""
        fake = _Socket(failures)
        sockets.append(fake)
        return fake

    monkeypatch.setattr(native_host.socket, "socket", make_socket)  # type: ignore[union-attr]
    monkeypatch.setattr(native_host.time, "sleep", sleeps.append)  # type: ignore[union-attr]

    connected = native_host.connect_to_app_socket(Path("/tmp/page_bridge.sock"))

    assert connected is sockets[1]
    assert sockets[0].closed is True
    assert sleeps == [0.1]
