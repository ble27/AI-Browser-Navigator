"""Tests for safety gates in the macOS input backend."""

from __future__ import annotations

from typing import Any

import pytest
from gesture_control.backends.base import InputBackend
from gesture_control.backends.macos import MacOSInputBackend, _open_url_in_google_chrome


class _FakeMouse:
    """Record cursor injection calls without touching the real pointer."""

    def __init__(self) -> None:
        self.position_sets = 0
        self._position: tuple[int, int] | None = None
        self.clicks: list[object] = []

    @property
    def position(self) -> tuple[int, int] | None:
        """Return the last injected pointer coordinate."""
        return self._position

    @position.setter
    def position(self, value: tuple[int, int]) -> None:
        """Record one pointer write."""
        self.position_sets += 1
        self._position = value

    def click(self, button: object) -> None:
        """Record one button click."""
        self.clicks.append(button)


def _backend_with_fake_mouse() -> tuple[MacOSInputBackend, _FakeMouse]:
    """Create a backend without initializing pynput's real macOS controller."""
    backend = object.__new__(MacOSInputBackend)
    InputBackend.__init__(backend)
    mouse = _FakeMouse()
    backend._mouse = mouse
    backend._left_button = "left"
    backend._last_position = None
    return backend, mouse


def _backend_with_recording_opener() -> tuple[MacOSInputBackend, list[str]]:
    """Create a backend whose URL opener records calls without launching Chrome."""
    backend = object.__new__(MacOSInputBackend)
    InputBackend.__init__(backend)
    opened: list[str] = []
    backend._opener = opened.append
    backend._mouse = _FakeMouse()
    backend._left_button = "left"
    backend._last_position = None
    return backend, opened


def test_macos_backend_injects_input_when_not_paused() -> None:
    """The backend should move and click while its safety gate is open."""
    backend, mouse = _backend_with_fake_mouse()

    backend.move_to(11, 22)
    backend.click_left()

    assert mouse.position == (11, 22)
    assert mouse.clicks == ["left"]


def test_macos_backend_never_injects_input_when_paused() -> None:
    """The backend's final safety check must block both moves and clicks."""
    backend, mouse = _backend_with_fake_mouse()
    backend.safe_pause.toggle()

    backend.move_to(11, 22)
    backend.click_left()

    assert mouse.position is None
    assert mouse.clicks == []


def test_macos_backend_skips_a_repeated_pointer_position() -> None:
    """A resting hand must not write the same coordinate on every frame."""
    backend, mouse = _backend_with_fake_mouse()

    backend.move_to(11, 22)
    backend.move_to(11, 22)
    backend.move_to(12, 22)

    assert mouse.position == (12, 22)
    assert mouse.position_sets == 2


def test_open_url_hands_https_url_to_the_opener() -> None:
    """An https URL should be forwarded to the injected opener unchanged."""
    backend, opened = _backend_with_recording_opener()

    backend.open_url("https://www.apple.com")

    assert opened == ["https://www.apple.com"]


def test_open_url_does_nothing_when_paused() -> None:
    """A paused backend must not open URLs even when open_url is called."""
    backend, opened = _backend_with_recording_opener()
    backend.safe_pause.toggle()

    backend.open_url("https://cursor.com")

    assert opened == []


def test_open_url_ignores_non_https_urls() -> None:
    """Non-https schemes must never reach the opener."""
    backend, opened = _backend_with_recording_opener()

    backend.open_url("http://example.com")
    backend.open_url("javascript:alert(1)")

    assert opened == []


def test_default_opener_launches_google_chrome(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default Chrome opener must call ``open -a`` with check=False."""
    backend = object.__new__(MacOSInputBackend)
    InputBackend.__init__(backend)
    backend._opener = _open_url_in_google_chrome
    backend._mouse = _FakeMouse()
    backend._left_button = "left"
    backend._last_position = None

    recorded: list[dict[str, Any]] = []

    def fake_run(argv: list[str], *, check: bool = True) -> None:
        recorded.append({"argv": list(argv), "check": check})

    monkeypatch.setattr("gesture_control.backends.macos.subprocess.run", fake_run)

    backend.open_url("https://cursor.com")

    assert recorded == [
        {
            "argv": ["open", "-a", "Google Chrome", "https://cursor.com"],
            "check": False,
        }
    ]
