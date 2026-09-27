"""Parse deterministic web-search phrases into shared intents."""

from __future__ import annotations

from gesture_control.actions import Intent, IntentType
from gesture_control.voice.spans import extract_search_span


def parse_search_command(transcript: str) -> Intent | None:
    """Parse a fixed web-search phrase.

    Args:
        transcript: Raw voice-style command text.

    Returns:
        A ``SEARCH_WEB`` intent carrying literal query text, or ``None`` when
        the complete phrase does not match the deterministic grammar.
    """
    span = extract_search_span(transcript)
    if span is None:
        return None
    return Intent(IntentType.SEARCH_WEB, text=span.query)
