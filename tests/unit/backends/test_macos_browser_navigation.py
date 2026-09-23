"""Hardware-free shortcut tests for macOS browser navigation."""

from __future__ import annotations

import pytest
from gesture_control.backends.base import BrowserAction, InputBackend
from gesture_control.backends.macos import MacOSInputBackend


def _backend_with_shortcut_recorder() -> tuple[MacOSInputBackend, list[tuple[str, ...]]]:
    """Build a macOS backend without constructing real mouse/keyboard controllers."""
    backend = object.__new__(MacOSInputBackend)
    InputBackend.__init__(backend)
    shortcuts: list[tuple[str, ...]] = []
    backend._shortcut_sender = shortcuts.append
    return backend, shortcuts


@pytest.mark.parametrize(
    ("action", "shortcut"),
    [
        (BrowserAction.PREVIOUS_TAB, ("cmd", "alt", "left")),
        (BrowserAction.NEXT_TAB, ("cmd", "alt", "right")),
        (BrowserAction.NEW_TAB, ("cmd", "t")),
        (BrowserAction.CLOSE_TAB, ("cmd", "w")),
        (BrowserAction.GO_BACK, ("cmd", "[")),
        (BrowserAction.GO_FORWARD, ("cmd", "]")),
        (BrowserAction.RELOAD_PAGE, ("cmd", "r")),
    ],
)
def test_macos_browser_action_uses_fixed_shortcut(
    action: BrowserAction,
    shortcut: tuple[str, ...],
) -> None:
    """Each typed browser action should emit exactly its fixed macOS chord."""
    backend, shortcuts = _backend_with_shortcut_recorder()

    backend.navigate_browser(action)

    assert shortcuts == [shortcut]


@pytest.mark.parametrize("action", list(BrowserAction))
def test_safe_pause_blocks_every_browser_shortcut(action: BrowserAction) -> None:
    """No browser action may reach the fake keyboard while safe-pause is active."""
    backend, shortcuts = _backend_with_shortcut_recorder()
    backend.safe_pause.toggle()

    backend.navigate_browser(action)

    assert shortcuts == []
