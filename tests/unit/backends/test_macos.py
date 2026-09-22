"""Tests for safety gates in the macOS input backend."""

from __future__ import annotations

from gesture_control.backends.base import InputBackend
from gesture_control.backends.macos import MacOSInputBackend


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
