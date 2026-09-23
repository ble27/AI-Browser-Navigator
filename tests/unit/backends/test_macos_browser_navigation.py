"""Hardware-free shortcut tests for macOS browser navigation."""

from __future__ import annotations

import pytest
from gesture_control.backends.base import BrowserAction, InputBackend
from gesture_control.backends.macos import MacOSInputBackend


class _RecordingKeyboard:
    """Record shortcut chords instead of injecting keyboard input."""

    def __init__(self) -> None:
        self.shortcuts: list[tuple[str, ...]] = []

    def hotkey(self, *keys: str) -> None:
        """Record one ordered keyboard chord."""
        self.shortcuts.append(keys)


def _backend_with_fake_keyboard() -> tuple[MacOSInputBackend, _RecordingKeyboard]:
    """Build a macOS backend without constructing real mouse/keyboard controllers."""
    backend = object.__new__(MacOSInputBackend)
    InputBackend.__init__(backend)
    keyboard = _RecordingKeyboard()
    backend._keyboard = keyboard
    return backend, keyboard


@pytest.mark.parametrize(
    ("action", "shortcut"),
    [
        (BrowserAction.PREVIOUS_TAB, ("command", "option", "left")),
        (BrowserAction.NEXT_TAB, ("command", "option", "right")),
        (BrowserAction.NEW_TAB, ("command", "t")),
        (BrowserAction.CLOSE_TAB, ("command", "w")),
        (BrowserAction.GO_BACK, ("command", "[")),
        (BrowserAction.GO_FORWARD, ("command", "]")),
        (BrowserAction.RELOAD_PAGE, ("command", "r")),
    ],
)
def test_macos_browser_action_uses_fixed_shortcut(
    action: BrowserAction,
    shortcut: tuple[str, ...],
) -> None:
    """Each typed browser action should emit exactly its fixed macOS chord."""
    backend, keyboard = _backend_with_fake_keyboard()

    backend.navigate_browser(action)

    assert keyboard.shortcuts == [shortcut]


@pytest.mark.parametrize("action", list(BrowserAction))
def test_safe_pause_blocks_every_browser_shortcut(action: BrowserAction) -> None:
    """No browser action may reach the fake keyboard while safe-pause is active."""
    backend, keyboard = _backend_with_fake_keyboard()
    backend.safe_pause.toggle()

    backend.navigate_browser(action)

    assert keyboard.shortcuts == []
