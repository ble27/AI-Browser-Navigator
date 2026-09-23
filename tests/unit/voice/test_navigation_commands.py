"""Contract tests for deterministic browser-navigation voice commands."""

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
        ("reload page", IntentType.RELOAD_PAGE),
        ("refresh", IntentType.RELOAD_PAGE),
        ("reopen closed tab", IntentType.REOPEN_TAB),
    ],
)
def test_navigation_phrase_resolves_to_intent(phrase: str, intent_type: IntentType) -> None:
    """Every phrase in the MVP grammar should resolve exactly."""
    assert parse_browser_navigation_command(phrase) == Intent(intent_type)


@pytest.mark.parametrize(
    ("transcript", "kind"),
    [
        ("  NeXt\t TAB  ", IntentType.NEXT_TAB),
        ("\nPREVIOUS   tab\n", IntentType.PREVIOUS_TAB),
        ("  Go \t FoRwArD ", IntentType.GO_FORWARD),
        (" ReFrEsH ", IntentType.RELOAD_PAGE),
    ],
)
def test_parse_browser_navigation_casefolds_and_collapses_whitespace(
    transcript: str,
    kind: IntentType,
) -> None:
    """Case and runs of whitespace should not affect an exact command."""
    assert parse_browser_navigation_command(transcript) == Intent(kind)


@pytest.mark.parametrize(
    "transcript",
    [
        "",
        "next",
        "tab",
        "switch",
        "previous",
        "new",
        "close",
        "go",
        "next tab please",
        "please next tab",
        "new tabs",
        "close all tabs",
        "go back now",
        "back page",
        "go forwards",
        "refresh chrome",
        "unknown words",
    ],
)
def test_parse_browser_navigation_rejects_extra_or_unknown_words(
    transcript: str,
) -> None:
    """The fixed grammar must not accept partial, embellished, or unknown text."""
    assert parse_browser_navigation_command(transcript) is None


def test_combined_parser_keeps_open_url_commands() -> None:
    """The combined command parser should preserve the existing URL grammar."""
    assert parse_command("open cursor webpage") == Intent(
        IntentType.OPEN_URL, url="https://cursor.com"
    )


def test_combined_parser_accepts_navigation_commands() -> None:
    """The combined parser should expose browser navigation grammar."""
    assert parse_command("refresh") == Intent(IntentType.RELOAD_PAGE)


@pytest.mark.parametrize(
    "transcript",
    [
        "Next, let's tap.",
        "next time.",
        "next tap.",
        "Open next time.",
    ],
)
def test_observed_whisper_next_tab_variants_are_narrowly_normalized(
    transcript: str,
) -> None:
    """Known tiny.en substitutions should still select the next tab."""
    assert parse_command(transcript) == Intent(IntentType.NEXT_TAB)


def test_observed_whisper_close_tab_variant_is_normalized() -> None:
    """The common tab-to-tap substitution should preserve close-tab intent."""
    assert parse_command("close tap.") == Intent(IntentType.CLOSE_TAB)
