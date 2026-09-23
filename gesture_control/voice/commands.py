"""Combine deterministic voice-style command parsers."""

from __future__ import annotations

from gesture_control.actions import Intent
from gesture_control.voice.browser import parse_browser_command
from gesture_control.voice.navigation import parse_browser_navigation_command


def parse_command(transcript: str) -> Intent | None:
    """Parse one supported deterministic command.

    Args:
        transcript: Raw voice-style command text.

    Returns:
        An open-URL or browser-navigation intent, or ``None`` when no
        deterministic grammar recognizes the complete phrase.
    """
    navigation_intent = parse_browser_navigation_command(transcript)
    if navigation_intent is not None:
        return navigation_intent
    return parse_browser_command(transcript)
