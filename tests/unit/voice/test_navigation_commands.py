"""Tests for deterministic browser navigation voice-style commands."""

from __future__ import annotations

import pytest

from gesture_control.actions import Intent, IntentType
from gesture_control.voice.commands import parse_command
from gesture_control.voice.navigation import parse_browser_navigation_command


@pytest.mark.parametrize(
    ("phrase", "intent_type"),
    [
        ("next tab", IntentType.NEXT_TAB),
        ("switch tab", IntentType.NEXT_TAB),
        ("previous tab", IntentType.PREVIOUS_TAB),
        ("new tab", IntentType.NEW_TAB),
        ("close tab", IntentType.CLOSE_TAB),
        ("go back", IntentType.GO_BACK),
        ("back", IntentType.GO_BACK),
        ("go forward", IntentType.GO_FORWARD),
        ("forward", IntentType.GO_FORWARD),
        ("reload", IntentType.RELOAD_PAGE),
        ("refresh", IntentType.RELOAD_PAGE),
    ],
)
def test_navigation_phrase_resolves_to_intent(phrase: str, intent_type: IntentType) -> None:
    """Every phrase in the MVP grammar should resolve exactly."""
    assert parse_browser_navigation_command(phrase) == Intent(intent_type)


def test_navigation_matching_ignores_case_and_collapses_whitespace() -> None:
    """Transcript formatting should not change an exact phrase match."""
    assert parse_browser_navigation_command("  GO   Forward ") == Intent(IntentType.GO_FORWARD)


@pytest.mark.parametrize("phrase", ["next tab now", "please reload", "tab"])
def test_navigation_parser_rejects_extra_or_unknown_words(phrase: str) -> None:
    """The deterministic grammar must reject words outside fixed phrases."""
    assert parse_browser_navigation_command(phrase) is None


def test_combined_parser_keeps_open_url_commands() -> None:
    """The combined command parser should preserve the existing URL grammar."""
    assert parse_command("open cursor webpage") == Intent(
        IntentType.OPEN_URL, url="https://cursor.com"
    )


def test_combined_parser_accepts_navigation_commands() -> None:
    """The combined parser should expose browser navigation grammar."""
    assert parse_command("refresh") == Intent(IntentType.RELOAD_PAGE)
