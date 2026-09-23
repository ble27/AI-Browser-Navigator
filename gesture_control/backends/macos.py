"""macOS synthetic mouse input and the global M2 safe-pause hotkey."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Protocol
from urllib.parse import urlparse

from gesture_control.backends.base import InputBackend, SafePause

_SAFE_PAUSE_HOTKEY = "<ctrl>+<alt>+<cmd>+p"


class _HotkeyListener(Protocol):
    """The pynput listener surface needed by :class:`SafePauseHotkey`."""

    def start(self) -> None:
        """Start listening without blocking."""

    def stop(self) -> None:
        """Stop listening."""


def _open_url_in_google_chrome(url: str) -> None:
    """Open ``url`` in Google Chrome via macOS ``open -a``.

    Args:
        url: Absolute https URL to hand to Chrome.
    """
    # ``open -a "Google Chrome"`` pins Chrome specifically; the default
    # ``open url`` / webbrowser path would use the user's default browser.
    subprocess.run(["open", "-a", "Google Chrome", url], check=False)


class _MissingPageBridge:
    """Page actions used until a Chrome bridge is connected.

    Click and type stay explicit failures so a missing extension cannot look
    like a successful click.
    """

    def click(self, target_id: str) -> None:
        """Refuse a page click when no bridge is connected.

        Args:
            target_id: Indexed element id that would have been clicked.

        Raises:
            RuntimeError: Always. The Chrome page bridge is not connected.
        """
        del target_id
        raise RuntimeError("No Chrome page bridge is connected; cannot click a page element.")

    def type_text(self, target_id: str, text: str) -> None:
        """Refuse typing when no bridge is connected.

        Args:
            target_id: Indexed element id that would have received text.
            text: Characters that would have been typed.

        Raises:
            RuntimeError: Always. The Chrome page bridge is not connected.
        """
        del target_id, text
        raise RuntimeError("No Chrome page bridge is connected; cannot type into a page element.")


class PageBridge(Protocol):
    """Fixed page operations a Chrome bridge may perform."""

    def click(self, target_id: str) -> None:
        """Activate the element with this index id."""

    def type_text(self, target_id: str, text: str) -> None:
        """Insert literal text into the element with this index id."""


class MacOSInputBackend(InputBackend):
    """Inject mouse input through pynput on macOS."""

    def __init__(
        self,
        safe_pause: SafePause | None = None,
        opener: Callable[[str], None] | None = None,
        page_bridge: PageBridge | None = None,
    ) -> None:
        """Create a macOS mouse controller.

        Args:
            safe_pause: A gate shared with the global pause hotkey.
            opener: Optional URL opener used by :meth:`open_url`. Defaults to
                launching Google Chrome with ``open -a``.
            page_bridge: Optional in-page click/type bridge. Defaults to a
                bridge that refuses page actions until Chrome is connected.
        """
        super().__init__(safe_pause=safe_pause)
        from pynput import mouse

        self._mouse = mouse.Controller()
        self._left_button = mouse.Button.left
        self._last_position: tuple[int, int] | None = None
        self._opener = opener if opener is not None else _open_url_in_google_chrome
        self._page_bridge = page_bridge if page_bridge is not None else _MissingPageBridge()

    def screen_size(self) -> tuple[int, int]:
        """Return the primary screen dimensions in pixels."""
        import pyautogui

        size = pyautogui.size()
        return size.width, size.height

    def move_to(self, x: int, y: int) -> None:
        """Move the pointer if the safe-pause gate permits input injection."""
        if self.safe_pause.is_paused:
            return
        # pynput writes the pointer through the window server. Repeating the
        # same coordinate every frame, which happens while the hand is still,
        # adds avoidable latency jitter to the next real move.
        if self._last_position == (x, y):
            return
        self._mouse.position = (x, y)
        self._last_position = (x, y)

    def click_left(self) -> None:
        """Click the primary mouse button if the safe-pause gate permits it."""
        if not self.safe_pause.is_paused:
            self._mouse.click(self._left_button)

    def open_url(self, url: str) -> None:
        """Open an https URL in Google Chrome if the safe-pause gate permits it.

        Args:
            url: Absolute URL to open. Non-https schemes and URLs without a
                network location are ignored.
        """
        if self.safe_pause.is_paused:
            return
        parsed = urlparse(url)
        # https-only: reject http/javascript/file and other schemes so voice
        # open-URL never launches arbitrary local or script handlers.
        if parsed.scheme.casefold() != "https" or not parsed.netloc:
            return
        # Also reject userinfo so a hand-built Intent cannot bypass the parser.
        if parsed.username is not None or parsed.password is not None:
            return
        self._opener(url)

    def click_element(self, target_id: str) -> None:
        """Click an indexed page element when the safe-pause gate is open.

        Args:
            target_id: Id from the page index, such as ``e1``.
        """
        if self.safe_pause.is_paused:
            return
        self._page_bridge.click(target_id)

    def type_text(self, target_id: str, text: str) -> None:
        """Type literal text into an indexed field when the gate is open.

        Args:
            target_id: Id of the textbox from the page index.
            text: Characters to insert. Never evaluated as code.
        """
        if self.safe_pause.is_paused:
            return
        self._page_bridge.type_text(target_id, text)


class SafePauseHotkey:
    """Own the non-blocking global hotkey that toggles synthetic input."""

    def __init__(
        self,
        safe_pause: SafePause,
        on_toggle: Callable[[bool], None] | None = None,
    ) -> None:
        """Create, but do not start, the global safe-pause hotkey.

        Args:
            safe_pause: The input gate to toggle.
            on_toggle: Optional callback receiving the new paused state.
        """
        self._safe_pause = safe_pause
        self._on_toggle = on_toggle
        self._listener: _HotkeyListener | None = None

    def start(self) -> None:
        """Start listening for the safe-pause hotkey.

        Raises:
            RuntimeError: If a listener has already been started.
        """
        if self._listener is not None:
            raise RuntimeError("Safe-pause hotkey is already running.")
        from pynput import keyboard

        self._listener = keyboard.GlobalHotKeys({_SAFE_PAUSE_HOTKEY: self._toggle})
        self._listener.start()

    def stop(self) -> None:
        """Stop the hotkey listener if it has been started."""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def __enter__(self) -> SafePauseHotkey:
        """Start the listener on context-manager entry."""
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Stop the listener on context-manager exit."""
        self.stop()

    def _toggle(self) -> None:
        """Toggle safe pause from pynput's listener thread."""
        paused = self._safe_pause.toggle()
        if self._on_toggle is not None:
            self._on_toggle(paused)
