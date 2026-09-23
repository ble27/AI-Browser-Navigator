"""Resolve voice commands against the active Chrome page snapshot."""

from __future__ import annotations

from gesture_control.actions import Intent
from gesture_control.browser.bridge import BridgeError, ChromePageBridge
from gesture_control.voice.page import PageElement, resolve_page_command

_PAGE_COMMAND_PREFIXES = frozenset(
    {
        "activate",
        "choose",
        "click",
        "enter",
        "fill",
        "focus",
        "look",
        "lookup",
        "press",
        "put",
        "search",
        "select",
        "tap",
        "type",
    }
)
_SEARCH_PREFIXES = frozenset({"look", "lookup", "search"})


class PageCommandUnavailableError(RuntimeError):
    """Raised when an explicit page command cannot reach the Chrome bridge."""


class LivePageCommandResolver:
    """Resolve candidate phrases using interactive elements from active Chrome."""

    def __init__(self, bridge: ChromePageBridge) -> None:
        """Create a resolver for one running bridge.

        Args:
            bridge: App-side connection to the first-party Chrome extension.
        """
        self._bridge = bridge

    def resolve(self, transcript: str) -> Intent | None:
        """Resolve one page-directed phrase.

        Search phrases fall back to omnibox search when the bridge is absent
        or the page has no unique search field. Explicit click/focus/type
        phrases report a disconnected bridge instead of silently pretending
        they were dispatched.

        Args:
            transcript: Raw local speech transcript.

        Returns:
            A page intent, or ``None`` when this is not a page command or when
            search should fall back to browser-wide search.

        Raises:
            PageCommandUnavailableError: If an explicit page mutation was
                requested while the extension/native host is disconnected.
        """
        collapsed = " ".join(transcript.split())
        if not collapsed:
            return None
        first_word = collapsed.split(maxsplit=1)[0].casefold().strip(".,!?")
        if first_word not in _PAGE_COMMAND_PREFIXES:
            return None
        try:
            snapshot = self._bridge.snapshot()
        except BridgeError as exc:
            if first_word in _SEARCH_PREFIXES:
                return None
            raise PageCommandUnavailableError(str(exc)) from exc
        elements = tuple(
            PageElement(
                element_id=element.element_id,
                role=element.role,
                name=element.name,
            )
            for element in snapshot.elements
        )
        return resolve_page_command(collapsed, elements)
