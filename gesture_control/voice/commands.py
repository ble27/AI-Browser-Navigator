"""Combine deterministic voice-style command parsers."""

from __future__ import annotations

from gesture_control.actions import Intent, IntentType
from gesture_control.voice.browser import parse_browser_command
from gesture_control.voice.desktop import (
    parse_chrome_omnibox_focus_command,
    parse_focused_page_field_command,
    parse_key_command,
    parse_type_command,
)
from gesture_control.voice.navigation import parse_browser_navigation_command
from gesture_control.voice.scroll import parse_scroll_command
from gesture_control.voice.search import parse_search_command


def parse_command(
    transcript: str,
    utterance_duration_s: float | None = None,
    *,
    scroll_pages: int | None = None,
) -> Intent | None:
    """Parse one supported deterministic command.

    Args:
        transcript: Raw voice-style command text.
        utterance_duration_s: Optional captured audio duration used to scale
            plain scroll commands only.
        scroll_pages: Optional fixed page count for a plain scroll. Explicit
            scroll phrases ignore it.

    Returns:
        A supported desktop or browser intent, or ``None`` when no
        deterministic grammar recognizes the complete phrase.
    """
    omnibox_focus = parse_chrome_omnibox_focus_command(transcript)
    if omnibox_focus is not None:
        return omnibox_focus
    field_action = parse_focused_page_field_command(transcript)
    if field_action is not None:
        return field_action
    key_intent = parse_key_command(transcript)
    if key_intent is not None:
        return key_intent
    type_request = parse_type_command(transcript)
    if type_request is not None and not type_request.has_target:
        return Intent(IntentType.TYPE_FOCUSED, text=type_request.text)
    navigation_intent = parse_browser_navigation_command(transcript)
    if navigation_intent is not None:
        return navigation_intent
    scroll_intent = parse_scroll_command(
        transcript,
        utterance_duration_s,
        default_pages=scroll_pages,
    )
    if scroll_intent is not None:
        return scroll_intent
    search_intent = parse_search_command(transcript)
    if search_intent is not None:
        return search_intent
    return parse_browser_command(transcript)
