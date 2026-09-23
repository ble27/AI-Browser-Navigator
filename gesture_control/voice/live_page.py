"""Resolve voice commands against the active Chrome page snapshot."""

from __future__ import annotations

import threading
import time

from gesture_control.actions import Intent
from gesture_control.browser.bridge import BridgeError, ChromePageBridge, PageSnapshot
from gesture_control.voice.page import PageElement, resolve_page_command

_PAGE_COMMAND_PREFIXES = frozenset(
    {
        "activate",
        "answer",
        "check",
        "choose",
        "click",
        "enter",
        "fill",
        "focus",
        "look",
        "lookup",
        "press",
        "put",
        "response",
        "search",
        "select",
        "submit",
        "tap",
        "the",
        "type",
    }
)
_SEARCH_PREFIXES = frozenset({"look", "lookup", "search"})
_SNAPSHOT_CACHE_TTL_S = 2.0


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
        self._lock = threading.Lock()
        self._cached: PageSnapshot | None = None
        self._cached_at = 0.0

    def warm(self) -> None:
        """Prefetch a snapshot so resolve can overlap with transcription."""
        try:
            snapshot = self._bridge.snapshot()
        except BridgeError:
            return
        with self._lock:
            self._cached = snapshot
            self._cached_at = time.monotonic()

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
            snapshot = self._take_snapshot()
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

    def _take_snapshot(self) -> PageSnapshot:
        """Return a fresh or briefly cached page snapshot."""
        with self._lock:
            cached = self._cached
            cached_at = self._cached_at
        if cached is not None and (time.monotonic() - cached_at) <= _SNAPSHOT_CACHE_TTL_S:
            with self._lock:
                self._cached = None
            return cached
        snapshot = self._bridge.snapshot()
        with self._lock:
            self._cached = None
        return snapshot
