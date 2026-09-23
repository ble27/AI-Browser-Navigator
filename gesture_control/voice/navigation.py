"""Parse deterministic browser navigation phrases into shared intents."""

from __future__ import annotations

from gesture_control.actions import Intent, IntentType

_NAVIGATION_PHRASES: dict[str, IntentType] = {
    "next tab": IntentType.NEXT_TAB,
    "switch tab": IntentType.NEXT_TAB,
    "previous tab": IntentType.PREVIOUS_TAB,
    "new tab": IntentType.NEW_TAB,
    "close tab": IntentType.CLOSE_TAB,
    "go back": IntentType.GO_BACK,
    "back": IntentType.GO_BACK,
    "go forward": IntentType.GO_FORWARD,
    "forward": IntentType.GO_FORWARD,
    "reload": IntentType.RELOAD_PAGE,
    "refresh": IntentType.RELOAD_PAGE,
}


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
    normalized = " ".join(transcript.split()).casefold()
    intent_type = _NAVIGATION_PHRASES.get(normalized)
    if intent_type is None:
        return None
    return Intent(intent_type)
