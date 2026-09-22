"""macOS synthetic mouse input and the global M2 safe-pause hotkey."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from gesture_control.backends.base import InputBackend, SafePause

_SAFE_PAUSE_HOTKEY = "<ctrl>+<alt>+<cmd>+p"


class _HotkeyListener(Protocol):
    """The pynput listener surface needed by :class:`SafePauseHotkey`."""

    def start(self) -> None:
        """Start listening without blocking."""

    def stop(self) -> None:
        """Stop listening."""


class MacOSInputBackend(InputBackend):
    """Inject mouse input through pynput on macOS."""

    def __init__(self, safe_pause: SafePause | None = None) -> None:
        """Create a macOS mouse controller.

        Args:
            safe_pause: A gate shared with the global pause hotkey.
        """
        super().__init__(safe_pause=safe_pause)
        from pynput import mouse

        self._mouse = mouse.Controller()
        self._left_button = mouse.Button.left

    def screen_size(self) -> tuple[int, int]:
        """Return the primary screen dimensions in pixels."""
        import pyautogui

        size = pyautogui.size()
        return size.width, size.height

    def move_to(self, x: int, y: int) -> None:
        """Move the pointer if the safe-pause gate permits input injection."""
        if not self.safe_pause.is_paused:
            self._mouse.position = (x, y)

    def click_left(self) -> None:
        """Click the primary mouse button if the safe-pause gate permits it."""
        if not self.safe_pause.is_paused:
            self._mouse.click(self._left_button)


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
