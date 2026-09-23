"""Parse deterministic web-search phrases into shared intents."""

from __future__ import annotations

from gesture_control.actions import Intent, IntentType

_SEARCH_PREFIXES = ("search for ", "look up ", "lookup ", "google ")


def parse_search_command(transcript: str) -> Intent | None:
    """Parse a fixed web-search phrase.

    Args:
        transcript: Raw voice-style command text.

    Returns:
        A ``SEARCH_WEB`` intent carrying literal query text, or ``None`` when
        the complete phrase does not match the deterministic grammar.
    """
    collapsed = " ".join(transcript.split())
    if not collapsed:
        return None

    folded = collapsed.casefold()
    for prefix in _SEARCH_PREFIXES:
        if folded.startswith(prefix):
            query = collapsed[len(prefix) :].strip()
            return Intent(IntentType.SEARCH_WEB, text=query) if query else None

    if folded.startswith("find ") and folded.endswith(" online"):
        query = collapsed[5:-7].strip()
        return Intent(IntentType.SEARCH_WEB, text=query) if query else None
    return None
