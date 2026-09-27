"""Parse deterministic browser navigation phrases into shared intents."""

from __future__ import annotations

import re

from gesture_control.actions import Intent, IntentType

_NAVIGATION_PHRASES: dict[str, IntentType] = {
    "next tab": IntentType.NEXT_TAB,
    "next browser tab": IntentType.NEXT_TAB,
    "switch tab": IntentType.NEXT_TAB,
    "switch to next tab": IntentType.NEXT_TAB,
    "go to next tab": IntentType.NEXT_TAB,
    "move to next tab": IntentType.NEXT_TAB,
    "previous tab": IntentType.PREVIOUS_TAB,
    "previous browser tab": IntentType.PREVIOUS_TAB,
    "prior tab": IntentType.PREVIOUS_TAB,
    "last tab": IntentType.PREVIOUS_TAB,
    "switch to previous tab": IntentType.PREVIOUS_TAB,
    "go to previous tab": IntentType.PREVIOUS_TAB,
    "move to previous tab": IntentType.PREVIOUS_TAB,
    "new tab": IntentType.NEW_TAB,
    "open a new tab": IntentType.NEW_TAB,
    "open new tab": IntentType.NEW_TAB,
    "close tab": IntentType.CLOSE_TAB,
    "close current web": IntentType.CLOSE_TAB,
    "close current website": IntentType.CLOSE_TAB,
    "close current page": IntentType.CLOSE_TAB,
    "close current tab": IntentType.CLOSE_TAB,
    "close browser tab": IntentType.CLOSE_TAB,
    "close current browser tab": IntentType.CLOSE_TAB,
    "close this tab": IntentType.CLOSE_TAB,
    "go back": IntentType.GO_BACK,
    "back": IntentType.GO_BACK,
    "go back a page": IntentType.GO_BACK,
    "page back": IntentType.GO_BACK,
    "go forward": IntentType.GO_FORWARD,
    "forward": IntentType.GO_FORWARD,
    "go forward a page": IntentType.GO_FORWARD,
    "page forward": IntentType.GO_FORWARD,
    "reload": IntentType.RELOAD_PAGE,
    "reload page": IntentType.RELOAD_PAGE,
    "reload current page": IntentType.RELOAD_PAGE,
    "reload current website": IntentType.RELOAD_PAGE,
    "reload current tab": IntentType.RELOAD_PAGE,
    "refresh": IntentType.RELOAD_PAGE,
    "refresh page": IntentType.RELOAD_PAGE,
    "refresh current page": IntentType.RELOAD_PAGE,
    "refresh current website": IntentType.RELOAD_PAGE,
    "refresh current tab": IntentType.RELOAD_PAGE,
    "reopen closed tab": IntentType.REOPEN_TAB,
    "reopen last tab": IntentType.REOPEN_TAB,
    "restore closed tab": IntentType.REOPEN_TAB,
    "undo close tab": IntentType.REOPEN_TAB,
}
_OBSERVED_ASR_ALIASES: dict[str, str] = {
    "next lets tap": "next tab",
    "next tap": "next tab",
    "next time": "next tab",
    "open next time": "next tab",
    "next step": "next tab",
    "next up": "next tab",
    "previous tap": "previous tab",
    "prev tab": "previous tab",
    "prev tap": "previous tab",
    "last tap": "previous tab",
    "close tap": "close tab",
    "closed tap": "close tab",
    "closed tab": "close tab",
    "close tabs": "close tab",
    "close step": "close tab",
    "closed step": "close tab",
    "close amazon": "close tab",
    "closed amazon": "close tab",
    "close reddit": "close tab",
    "closed reddit": "close tab",
    "close google": "close tab",
    "closed google": "close tab",
    "close chatgpt": "close tab",
    "closed chatgpt": "close tab",
    "close claude": "close tab",
    "closed claude": "close tab",
}
_APOSTROPHES = str.maketrans("", "", "'’")


def parse_browser_navigation_command(transcript: str) -> Intent | None:
    """Parse an exact browser navigation phrase.

    Matching is case-insensitive and collapses whitespace. Only complete
    phrases from the fixed grammar are accepted, so unknown extra words are
    rejected.

    Args:
        transcript: Raw voice-style command text.

    Returns:
        The matching browser navigation intent, or ``None``.
    """
    words_only = re.sub(r"[^\w\s]", " ", transcript.casefold().translate(_APOSTROPHES))
    normalized = " ".join(words_only.split())
    normalized = _OBSERVED_ASR_ALIASES.get(normalized, normalized)
    intent_type = _NAVIGATION_PHRASES.get(normalized)
    if intent_type is None:
        return None
    return Intent(intent_type)
