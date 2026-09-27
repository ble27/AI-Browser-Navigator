"""Resolve voice commands against the active Chrome page snapshot."""

from __future__ import annotations

import threading
import time
from difflib import SequenceMatcher

from gesture_control.actions import Intent, IntentType
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
        "highlight",
        "hit",
        "left",
        "look",
        "lookup",
        "mouse",
        "open",
        "pick",
        "press",
        "push",
        "put",
        "response",
        "search",
        "select",
        "submit",
        "tap",
        "the",
        "type",
        "write",
    }
)
_SEARCH_PREFIXES = frozenset({"look", "lookup", "search"})
# These prefixes are also used by browser-wide grammars; a missing bridge must
# fall through instead of hard-failing (e.g. ``open amazon``).
_BRIDGE_OPTIONAL_PREFIXES = _SEARCH_PREFIXES | frozenset({"open"})
_SNAPSHOT_CACHE_TTL_S = 2.0

_CLICK_VERBS = frozenset(
    {
        "click",
        "press",
        "tap",
        "choose",
        "activate",
        "hit",
        "pick",
        "push",
        "open",
    }
)
_CLICK_SKIP = frozenset({"on", "the", "a", "an"})
# Spoken targets → alternate accessible-name tokens seen on real sites.
_TARGET_ALIASES: dict[str, tuple[str, ...]] = {
    "orders": ("orders", "your orders", "returns & orders", "account & lists"),
}
_RANK_MIN_SCORE = 0.55
_RANK_MARGIN = 0.12
# ChromePageBridge's default connect timeout is several seconds; the executor's
# readiness loop polls at READY_POLL_INTERVAL_S (0.25s) and expects a fast
# "still disconnected" answer, not a multi-second block on every iteration.
_CURRENT_URL_POLL_TIMEOUT_S = 0.3


class PageCommandUnavailableError(RuntimeError):
    """Raised when an explicit page command cannot reach the Chrome bridge."""


def _token_set(text: str) -> set[str]:
    return {
        part for part in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if part
    }


def _rank_click_target(
    spoken_target: str,
    elements: tuple[PageElement, ...],
) -> Intent | None:
    """Soft-rank clickable elements against a spoken target label.

    Args:
        spoken_target: Words after the click verb (e.g. ``orders``).
        elements: Snapshot elements with local ``eN`` ids.

    Returns:
        A ``CLICK_ELEMENT`` intent when one candidate clearly wins, else
        ``None`` (fail closed).
    """
    target = " ".join(spoken_target.split()).casefold().strip(".,!?")
    if not target:
        return None
    aliases = _TARGET_ALIASES.get(target, (target,))
    query_tokens: set[str] = set()
    for alias in aliases:
        query_tokens |= _token_set(alias)
    if not query_tokens:
        return None

    scored: list[tuple[float, str]] = []
    for element in elements:
        if element.role not in {"button", "link", "checkbox"}:
            continue
        name_tokens = _token_set(element.name)
        if not name_tokens:
            continue
        overlap = len(query_tokens & name_tokens) / len(query_tokens)
        ratio = SequenceMatcher(None, target, element.name.casefold()).ratio()
        # Prefer alias/token overlap; ratio breaks near-ties on short labels.
        score = max(overlap, ratio * 0.85)
        if target in element.name.casefold():
            score = max(score, 0.9)
        scored.append((score, element.element_id))
    if not scored:
        return None
    scored.sort(reverse=True)
    best_score, best_id = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    if best_score < _RANK_MIN_SCORE:
        return None
    if (best_score - second) < _RANK_MARGIN and second >= _RANK_MIN_SCORE:
        return None
    return Intent(IntentType.CLICK_ELEMENT, target_id=best_id)


def _spoken_click_target(transcript: str) -> str | None:
    tokens = transcript.split()
    if not tokens:
        return None
    folded = [token.casefold().strip(".,!?") for token in tokens]
    if folded[0] == "mouse" and len(folded) > 1 and folded[1] == "click":
        folded = folded[1:]
    if folded[0] == "left" and len(folded) > 1 and folded[1] == "click":
        folded = folded[1:]
    if folded[0] not in _CLICK_VERBS:
        return None
    rest = folded[1:]
    while rest and rest[0] in _CLICK_SKIP:
        rest = rest[1:]
    if rest and rest[-1] in {"button", "link"}:
        rest = rest[:-1]
    return " ".join(rest) if rest else None


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

    def current_url(self) -> str | None:
        """Return the active tab URL, or ``None`` when the bridge is down.

        Used from the executor's readiness poll loop
        (``READY_POLL_INTERVAL_S`` cadence), so this uses a short bridge
        timeout: the default connect timeout would otherwise block each
        poll for several seconds while the bridge is disconnected.
        """
        try:
            return self._take_snapshot(timeout=_CURRENT_URL_POLL_TIMEOUT_S).url
        except BridgeError:
            return None

    def resolve(self, transcript: str) -> Intent | None:
        """Resolve one page-directed phrase.

        Search phrases fall back to omnibox search when the bridge is absent
        or the page has no unique search field. Explicit click/focus/type
        phrases report a disconnected bridge instead of silently pretending
        they were dispatched. When exact matching fails for a click verb,
        soft-rank accessible names (e.g. ``orders``) with a confidence floor.

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
            if first_word in _BRIDGE_OPTIONAL_PREFIXES:
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
        exact = resolve_page_command(collapsed, elements)
        if exact is not None:
            return exact
        spoken = _spoken_click_target(collapsed)
        if spoken is None:
            return None
        return _rank_click_target(spoken, elements)

    def _take_snapshot(self, *, timeout: float | None = None) -> PageSnapshot:
        """Return a fresh or briefly cached page snapshot.

        Args:
            timeout: Optional bridge-call timeout override. ``None`` uses the
                bridge's own default (a longer, one-shot connect wait).
        """
        with self._lock:
            cached = self._cached
            cached_at = self._cached_at
        if cached is not None and (time.monotonic() - cached_at) <= _SNAPSHOT_CACHE_TTL_S:
            with self._lock:
                self._cached = None
            return cached
        snapshot = self._bridge.snapshot(timeout=timeout)
        with self._lock:
            self._cached = None
        return snapshot
