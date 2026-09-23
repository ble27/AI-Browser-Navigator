"""Combine deterministic voice-style command parsers."""

from __future__ import annotations

from gesture_control.actions import Intent
from gesture_control.voice.browser import parse_browser_command
from gesture_control.voice.navigation import parse_browser_navigation_command
from gesture_control.voice.scroll import parse_scroll_command
from gesture_control.voice.search import parse_search_command


def parse_command(
    transcript: str,
    utterance_duration_s: float | None = None,
) -> Intent | None:
    """Parse one supported deterministic command.

    Args:
        transcript: Raw voice-style command text.
        utterance_duration_s: Optional captured audio duration used to scale
            plain scroll commands only.

    Returns:
        An open-URL or browser-navigation intent, or ``None`` when no
        deterministic grammar recognizes the complete phrase.
    """
    navigation_intent = parse_browser_navigation_command(transcript)
    if navigation_intent is not None:
        return navigation_intent
    scroll_intent = parse_scroll_command(transcript, utterance_duration_s)
    if scroll_intent is not None:
        return scroll_intent
    search_intent = parse_search_command(transcript)
    if search_intent is not None:
        return search_intent
    return parse_browser_command(transcript)
