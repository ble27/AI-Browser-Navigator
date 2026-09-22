"""Platform-independent input backend contract and safe-pause state."""

from __future__ import annotations

from abc import ABC, abstractmethod
from threading import Lock


class SafePause:
    """Thread-safe global gate for every synthetic-input operation."""

    def __init__(self, paused: bool = False) -> None:
        """Create a safe-pause gate.

        Args:
            paused: Initial state. ``True`` blocks all input injection.
        """
        self._paused = paused
        self._lock = Lock()

    @property
    def is_paused(self) -> bool:
        """Return whether synthetic input is currently blocked."""
        with self._lock:
            return self._paused

    def toggle(self) -> bool:
        """Toggle the gate and return its new paused state."""
        with self._lock:
            self._paused = not self._paused
            return self._paused


class InputBackend(ABC):
    """The sole interface through which actions inject OS input.

    Every concrete implementation must check :attr:`safe_pause` immediately
    before injecting input. This preserves the safety invariant even when a
    caller accidentally dispatches an action after the user pauses tracking.
    """

    def __init__(self, safe_pause: SafePause | None = None) -> None:
        """Initialize the input backend's shared safety gate.

        Args:
            safe_pause: A gate shared with the global pause hotkey.
        """
        self.safe_pause = safe_pause or SafePause()

    @abstractmethod
    def screen_size(self) -> tuple[int, int]:
        """Return the primary display width and height in pixels."""

    @abstractmethod
    def move_to(self, x: int, y: int) -> None:
        """Move the cursor unless input injection is paused.

        Args:
            x: Target horizontal screen coordinate.
            y: Target vertical screen coordinate.
        """

    @abstractmethod
    def click_left(self) -> None:
        """Click the primary mouse button unless input injection is paused."""
