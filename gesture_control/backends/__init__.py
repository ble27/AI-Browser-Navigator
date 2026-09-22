"""The only operating-system-specific layer in this codebase.

Defines the ``InputBackend`` interface (move the cursor, click, scroll, send
keys, switch applications, ...) and provides one adapter per platform:

- macOS -- ``pynput``/``pyautogui`` (Quartz under the hood).
- Windows -- ``pynput``/``pyautogui`` (Win32 under the hood).
- Linux X11 -- ``pynput``/``pyautogui`` (Xlib under the hood).
- Linux Wayland -- ``ydotool``/``ydotoold`` (uinput-based), since Wayland
  blocks synthetic input by design.

Every adapter MUST respect the global safe-pause state before injecting any
input -- see the safety-critical invariant in ``AGENTS.md``.
"""

from gesture_control.backends.base import InputBackend, SafePause

__all__ = ["InputBackend", "SafePause"]
