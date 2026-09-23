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
        (BrowserAction.REOPEN_TAB, ("cmd", "shift", "t")),
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


def test_macos_search_uses_literal_injectable_query_seam() -> None:
    """Search should pass the query unchanged to the fixed omnibox injector."""
    backend = object.__new__(MacOSInputBackend)
    InputBackend.__init__(backend)
    searches: list[str] = []
    backend._search_sender = searches.append

    backend.search_web("cats; $(not code)")

    assert searches == ["cats; $(not code)"]


def test_macos_scroll_converts_signed_pages_to_fixed_notches() -> None:
    """Each signed page unit should map to five native vertical notches."""
    backend = object.__new__(MacOSInputBackend)
    InputBackend.__init__(backend)
    scrolls: list[int] = []
    backend._scroll_sender = scrolls.append

    backend.scroll(-3)
    backend.scroll(2)

    assert scrolls == [-15, 10]


def test_safe_pause_blocks_search_and_scroll_injection() -> None:
    """Safe-pause must block both newly added synthetic-input paths."""
    backend = object.__new__(MacOSInputBackend)
    InputBackend.__init__(backend)
    searches: list[str] = []
    scrolls: list[int] = []
    backend._search_sender = searches.append
    backend._scroll_sender = scrolls.append
    backend.safe_pause.toggle()

    backend.search_web("blocked")
    backend.scroll(-3)

    assert searches == []
    assert scrolls == []
