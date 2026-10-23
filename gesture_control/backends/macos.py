"""macOS synthetic mouse input and the global M2 safe-pause hotkey."""

from __future__ import annotations

import ipaddress
import re
import subprocess
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlparse

from gesture_control.backends.base import (
    BrowserAction,
    FocusedPageFieldAction,
    InputBackend,
    LaunchableApp,
    PressableKey,
    SafePause,
)
from gesture_control.voice.stream_contracts import MAX_TYPED_CHARS

if TYPE_CHECKING:
    from gesture_control.browser.bridge import PageSnapshot

_SAFE_PAUSE_HOTKEY = "<ctrl>+<alt>+<cmd>+p"
_CHROME_SHORTCUTS: dict[BrowserAction, tuple[str, ...]] = {
    BrowserAction.PREVIOUS_TAB: ("cmd", "alt", "left"),
    BrowserAction.NEXT_TAB: ("cmd", "alt", "right"),
    BrowserAction.NEW_TAB: ("cmd", "t"),
    BrowserAction.CLOSE_TAB: ("cmd", "w"),
    BrowserAction.GO_BACK: ("cmd", "["),
    BrowserAction.GO_FORWARD: ("cmd", "]"),
    BrowserAction.RELOAD_PAGE: ("cmd", "r"),
    BrowserAction.REOPEN_TAB: ("cmd", "shift", "t"),
}
_SCROLL_NOTCHES_PER_PAGE = 5
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)


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


# The Web Speech control page's own <title>; navigation must never send its
# browser shortcuts to this separate Chrome app window.
_VOICE_CONTROL_WINDOW_HINT = "Gesture Control"


def _frontmost_window_title() -> str | None:
    """Return the frontmost process name and window title via AppleScript."""
    result = subprocess.run(
        [
            "osascript",
            "-e",
            (
                'tell application "System Events"\n'
                "set p to first application process whose frontmost is true\n"
                "set procName to name of p\n"
                "try\n"
                "set winName to name of front window of p\n"
                "on error\n"
                'set winName to "<no window>"\n'
                "end try\n"
                'return procName & " | " & winName\n'
                "end tell"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or None


def _browsing_chrome_window_is_focused() -> bool:
    """Return whether a normal Google Chrome browsing window owns focus.

    Returns:
        ``True`` only when the frontmost window is Google Chrome and is not
        the separate Web Speech control page.
    """
    frontmost = _frontmost_window_title()
    if frontmost is None:
        return False
    process, _, title = frontmost.partition(" | ")
    return (
        process == "Google Chrome"
        and bool(title)
        and _VOICE_CONTROL_WINDOW_HINT.casefold() not in title.casefold()
    )


def _voice_control_window_is_focused() -> bool:
    """Return whether the voice pill window currently owns keyboard focus."""
    frontmost = _frontmost_window_title()
    if frontmost is None:
        return False
    process, _, title = frontmost.partition(" | ")
    return process == "Google Chrome" and _VOICE_CONTROL_WINDOW_HINT.casefold() in title.casefold()


# Shortcut tokens -> pynput ``Key`` member names. pynput names the main Mac
# Return key ``enter`` (virtual key 0x24); the keypad Enter key is 0x4C and does
# not submit most text fields, so spoken "enter" / "return" must use this one.
# Named keys must be listed: pynput rejects multi-character strings such as
# "backspace", which silently broke backspace, tab, and escape presses.
_PYNPUT_KEY_NAMES = {
    "cmd": "cmd",
    "alt": "alt",
    "shift": "shift",
    "left": "left",
    "right": "right",
    "enter": "enter",
    "return": "enter",
    "backspace": "backspace",
    "tab": "tab",
    "escape": "esc",
}
# "Delete line" as a person does it: jump to the end of the line, select back
# to its start, delete the selection.
_DELETE_LINE_CHORDS: tuple[tuple[str, ...], ...] = (
    ("cmd", "right"),
    ("cmd", "shift", "left"),
    ("backspace",),
)


def _pynput_key(name: str) -> object:
    """Resolve one shortcut token to a pynput key or a literal character.

    Args:
        name: Symbolic name from a shortcut tuple. ``return`` is the main
            Return key.

    Returns:
        A pynput key, or the original character when ``name`` is not special.
    """
    from pynput import keyboard

    key_name = _PYNPUT_KEY_NAMES.get(name)
    if key_name is None:
        return name
    return getattr(keyboard.Key, key_name)


def _send_pynput_shortcut(keys: tuple[str, ...]) -> None:
    """Press and release one fixed shortcut through pynput.

    Args:
        keys: Ordered symbolic modifier/key names.
    """
    from pynput import keyboard

    controller = keyboard.Controller()
    resolved_keys = [_pynput_key(key) for key in keys]
    pressed: list[object] = []
    try:
        for key in resolved_keys:
            controller.press(key)
            pressed.append(key)
    finally:
        # Release whatever went down so a failed press cannot leave Command
        # held for the rest of the session.
        for key in reversed(pressed):
            controller.release(key)


def _search_web_with_pynput(text: str) -> None:
    """Focus Chrome's omnibox, type literal text, and submit it.

    Args:
        text: Literal search query to type.
    """
    from pynput import keyboard

    controller = keyboard.Controller()
    controller.press(keyboard.Key.cmd)
    controller.press("l")
    controller.release("l")
    controller.release(keyboard.Key.cmd)
    controller.type(text)
    controller.press(keyboard.Key.enter)
    controller.release(keyboard.Key.enter)


def _scroll_with_pynput(notches: int) -> None:
    """Inject one fixed signed vertical scroll through pynput.

    Args:
        notches: Positive values scroll up and negative values scroll down.
    """
    from pynput import mouse

    mouse.Controller().scroll(0, notches)


def _is_safe_https_url(url: str) -> bool:
    """Return whether a URL targets a public HTTPS hostname without credentials."""
    if any(character.isspace() for character in url) or "\\" in url:
        return False
    parsed = urlparse(url)
    if parsed.scheme.casefold() != "https" or not parsed.netloc:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    try:
        parsed_port = parsed.port
    except ValueError:
        return False
    if parsed_port is not None and not 1 <= parsed_port <= 65_535:
        return False
    hostname = parsed.hostname
    if hostname is None:
        return False
    host = hostname.rstrip(".").casefold()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return False
    if host == "localhost" or host.endswith((".internal", ".local", ".localhost")):
        return False
    labels = host.split(".")
    return (
        len(labels) >= 2
        and all(_HOST_LABEL.fullmatch(label) for label in labels)
        and len(labels[-1]) >= 2
        and (labels[-1].isalpha() or labels[-1].startswith("xn--"))
    )


class _MissingPageBridge:
    """Page actions used until a Chrome bridge is connected.

    Click and type stay explicit failures so a missing extension cannot look
    like a successful click. Snapshot fails the same way so page-first search
    can fall back to the omnibox.
    """

    def snapshot(self, timeout: float | None = None) -> PageSnapshot:
        """Refuse snapshots when no bridge is connected.

        Args:
            timeout: Ignored. Present for Protocol compatibility.

        Raises:
            RuntimeError: Always. The Chrome page bridge is not connected.
        """
        del timeout
        raise RuntimeError("No Chrome page bridge is connected; cannot snapshot the page.")

    def click(self, target_id: str, timeout: float | None = None) -> None:
        """Refuse a page click when no bridge is connected.

        Args:
            target_id: Indexed element id that would have been clicked.
            timeout: Ignored. Present for Protocol compatibility.

        Raises:
            RuntimeError: Always. The Chrome page bridge is not connected.
        """
        del target_id, timeout
        raise RuntimeError("No Chrome page bridge is connected; cannot click a page element.")

    def type_text(self, target_id: str, text: str, timeout: float | None = None) -> None:
        """Refuse typing when no bridge is connected.

        Args:
            target_id: Indexed element id that would have received text.
            text: Characters that would have been typed.
            timeout: Ignored. Present for Protocol compatibility.

        Raises:
            RuntimeError: Always. The Chrome page bridge is not connected.
        """
        del target_id, text, timeout
        raise RuntimeError("No Chrome page bridge is connected; cannot type into a page element.")

    def focus(self, target_id: str, timeout: float | None = None) -> None:
        """Refuse page focus when no bridge is connected."""
        del target_id, timeout
        raise RuntimeError("No Chrome page bridge is connected; cannot focus a page element.")

    def type_and_submit(self, target_id: str, text: str, timeout: float | None = None) -> None:
        """Refuse page submission when no bridge is connected."""
        del target_id, text, timeout
        raise RuntimeError("No Chrome page bridge is connected; cannot submit page text.")

    def edit_focused_field(
        self, action: FocusedPageFieldAction, timeout: float | None = None
    ) -> None:
        """Refuse a focused-field edit when no bridge is connected."""
        del action, timeout
        raise RuntimeError("No Chrome page bridge is connected; cannot edit a page field.")


class PageBridge(Protocol):
    """Fixed page operations a Chrome bridge may perform."""

    def snapshot(self, timeout: float | None = None) -> PageSnapshot:
        """Return the active-tab interactive element index."""

    def click(self, target_id: str, timeout: float | None = None) -> None:
        """Activate the element with this index id."""

    def type_text(self, target_id: str, text: str, timeout: float | None = None) -> None:
        """Insert literal text into the element with this index id."""

    def focus(self, target_id: str, timeout: float | None = None) -> None:
        """Focus the element with this index id."""

    def type_and_submit(self, target_id: str, text: str, timeout: float | None = None) -> None:
        """Insert and submit literal text through this element."""

    def edit_focused_field(
        self, action: FocusedPageFieldAction, timeout: float | None = None
    ) -> None:
        """Apply a guarded edit to the active search field or page composer."""


class MacOSInputBackend(InputBackend):
    """Inject mouse input through pynput on macOS."""

    _voice_window_is_focused: Callable[[], bool] = staticmethod(_voice_control_window_is_focused)

    def __init__(
        self,
        safe_pause: SafePause | None = None,
        opener: Callable[[str], None] | None = None,
        page_bridge: PageBridge | None = None,
        shortcut_sender: Callable[[tuple[str, ...]], None] | None = None,
        search_sender: Callable[[str], None] | None = None,
        scroll_sender: Callable[[int], None] | None = None,
        navigation_target_is_focused: Callable[[], bool] | None = None,
    ) -> None:
        """Create a macOS mouse controller.

        Args:
            safe_pause: A gate shared with the global pause hotkey.
            opener: Optional URL opener used by :meth:`open_url`. Defaults to
                launching Google Chrome with ``open -a``.
            page_bridge: Optional in-page click/type bridge. Defaults to a
                bridge that refuses page actions until Chrome is connected.
            shortcut_sender: Optional keyboard shortcut injector used by
                :meth:`navigate_browser`. Defaults to pynput.
            search_sender: Optional fixed omnibox search injector. Defaults to
                pynput.
            scroll_sender: Optional signed native-notch injector. Defaults to
                pynput.
            navigation_target_is_focused: Optional check that a normal browsing
                Chrome window already has focus. Navigation is ignored when
                the Web Speech control window or another app is frontmost.
        """
        super().__init__(safe_pause=safe_pause)
        from pynput import mouse

        self._mouse = mouse.Controller()
        self._left_button = mouse.Button.left
        self._last_position: tuple[int, int] | None = None
        self._opener = opener if opener is not None else _open_url_in_google_chrome
        self._page_bridge = page_bridge if page_bridge is not None else _MissingPageBridge()
        self._shortcut_sender = (
            shortcut_sender if shortcut_sender is not None else _send_pynput_shortcut
        )
        self._search_sender = (
            search_sender if search_sender is not None else _search_web_with_pynput
        )
        self._scroll_sender = scroll_sender if scroll_sender is not None else _scroll_with_pynput
        self._navigation_target_is_focused = (
            navigation_target_is_focused
            if navigation_target_is_focused is not None
            else _browsing_chrome_window_is_focused
        )

    def screen_size(self) -> tuple[int, int]:
        """Return the primary screen dimensions in pixels."""
        import pyautogui

        # Moves go through pynput, but pyautogui's default 0.1 s pause would
        # still delay any future path that touches it (and screen_size itself
        # is cheap either way once PAUSE is zero).
        pyautogui.PAUSE = 0
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
        # Revalidate at the injection boundary so hand-built Intents cannot
        # bypass the voice parser's scheme, credential, or host restrictions.
        if not _is_safe_https_url(url):
            return
        self._opener(url)

    def navigate_browser(self, action: BrowserAction) -> None:
        """Send a fixed Google Chrome navigation shortcut when input is enabled.

        The command only applies to an already focused normal Chrome browsing
        window. It never changes focus to choose a target, and ignores the
        command while the Web Speech control window is frontmost.

        Args:
            action: Typed browser navigation operation.
        """
        if self.safe_pause.is_paused:
            return
        if not self._navigation_target_is_focused():
            return
        self._shortcut_sender(_CHROME_SHORTCUTS[action])

    def focus_chrome_omnibox(self) -> None:
        """Focus Chrome's omnibox when a normal browsing window is focused."""
        if self.safe_pause.is_paused:
            return
        if not self._navigation_target_is_focused():
            return
        self._shortcut_sender(("cmd", "l"))

    def search_web(self, text: str) -> None:
        """Search the active page when possible, otherwise the Chrome omnibox.

        Prefers a unique on-page search textbox, or a unique search button that
        reveals one (apple.com-style). Falls back to the omnibox injector when
        the page bridge is absent or the page has no unique search control.

        Args:
            text: Literal query text to type and submit.
        """
        if self.safe_pause.is_paused or not text:
            return
        from gesture_control.browser.site_search import try_site_search

        if try_site_search(self._page_bridge, text):
            return
        self._search_sender(text)

    def scroll(self, amount: int) -> None:
        """Scroll a fixed number of native notches per signed page unit.

        Positive page units scroll up and negative page units scroll down.

        Args:
            amount: Non-zero signed page count.
        """
        if self.safe_pause.is_paused or amount == 0:
            return
        self._scroll_sender(amount * _SCROLL_NOTCHES_PER_PAGE)

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

    def focus_element(self, target_id: str) -> None:
        """Focus an indexed page element when the gate is open."""
        if self.safe_pause.is_paused:
            return
        self._page_bridge.focus(target_id)

    def edit_focused_page_field(self, action: FocusedPageFieldAction) -> None:
        """Edit only a supported active search field or page composer.

        Args:
            action: Fixed operation validated again by the content script.

        Raises:
            ValueError: If the page bridge is absent or rejects the active field.
        """
        if self.safe_pause.is_paused:
            return
        if action is FocusedPageFieldAction.DELETE_LINE:
            self._delete_line_with_keys()
            return
        try:
            self._page_bridge.edit_focused_field(action)
        except RuntimeError as exc:
            raise ValueError(str(exc)) from exc

    def _delete_line_with_keys(self) -> None:
        """Delete the caret's line with the same keys a person would press.

        Raises:
            ValueError: If the voice window, not the page, has keyboard focus.
        """
        if self._voice_window_is_focused():
            raise ValueError("Click into the line you want to delete first")
        for chord in _DELETE_LINE_CHORDS:
            self._shortcut_sender(chord)

    def submit_text(self, target_id: str, text: str) -> None:
        """Type and submit through an indexed field when the gate is open."""
        if self.safe_pause.is_paused:
            return
        self._page_bridge.type_and_submit(target_id, text)

    def open_app(self, app: LaunchableApp) -> None:
        """Open or focus a native macOS application when the gate is open."""
        if self.safe_pause.is_paused:
            return
        subprocess.run(["open", "-a", app.value], check=False)

    def type_focused(self, text: str) -> None:
        """Type literal text into the focused control when the gate is open."""
        if self.safe_pause.is_paused:
            return
        if not text or len(text) > MAX_TYPED_CHARS:
            return
        if any(ord(character) < 32 or ord(character) == 127 for character in text):
            return
        from pynput import keyboard

        keyboard.Controller().type(text)

    def press_key(self, key: PressableKey) -> None:
        """Press a named key chord when the gate is open."""
        if self.safe_pause.is_paused:
            return
        chords: dict[PressableKey, tuple[str, ...]] = {
            PressableKey.ENTER: ("return",),
            PressableKey.TAB: ("tab",),
            PressableKey.ESCAPE: ("escape",),
            PressableKey.BACKSPACE: ("backspace",),
            PressableKey.NEW_ITEM: ("cmd", "n"),
            PressableKey.SELECT_ALL: ("cmd", "a"),
        }
        self._shortcut_sender(chords[key])


def frontmost_app_name() -> str | None:
    """Return the frontmost application name via AppleScript."""
    result = subprocess.run(
        [
            "osascript",
            "-e",
            (
                'tell application "System Events" to get name of first '
                "application process whose frontmost is true"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    name = result.stdout.strip()
    return name or None


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
