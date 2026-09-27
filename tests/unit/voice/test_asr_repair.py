"""Unit tests for context-gated brand ASR repair (S0b)."""

from __future__ import annotations

import pytest
from gesture_control.voice.asr_repair import repair_command_text
from gesture_control.voice.commands import parse_command


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Open Cloud.", "Open claude"),
        ("open cloud", "open claude"),
        ("Open-cloud", "Open claude"),
        ("Opened Claude", "open Claude"),
        ("Open-clawed", "Open claude"),
        ("Opened color", "open claude"),
        ("Asked Chatibiti", "ask chatgpt"),
        ("Open up an A.", "Open openai"),
        ("open up an a", "open openai"),
        ("OpenOpene.", "open openai"),
        ("openopene", "open openai"),
        ("ask cloud what is two plus two", "ask claude what is two plus two"),
        ("ask clod what is two plus two", "ask claude what is two plus two"),
        ("go to cloud", "go to claude"),
        ("browse to chat gpt", "browse to chatgpt"),
        ("open chat gpt", "open chatgpt"),
        ("open ai", "open openai"),
        ("open a i", "open openai"),
        ("  Open   Cloud  ", "Open claude"),
        # Fuzzy closed-vocab (no exact-table entry required).
        ("open gemeni", "open gemini"),
        ("open amazin", "open amazon"),
    ],
)
def test_observed_misses_repair_to_brands(raw: str, expected: str) -> None:
    """Measured spike misses and planned siblings become brand tokens."""
    assert repair_command_text(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "type cloud storage",
        "search for cloud hosting",
        "open up the menu",
        "type hello world",
        "scroll down",
        "next tab",
        "click orders",
        "press enter",
        "open notes",
        "search for headphones",
        "go back",
    ],
)
def test_non_brand_and_gated_phrases_are_unchanged(raw: str) -> None:
    """Literal text and non-target verbs must not be rewritten."""
    assert repair_command_text(raw) == raw


def test_empty_and_punctuation_only() -> None:
    """Blank input normalizes to an empty string."""
    assert repair_command_text("") == ""
    assert repair_command_text("   ") == ""
    assert repair_command_text("...") == ""


def test_trailing_punctuation_stripped_without_repair() -> None:
    """Normalization alone strips terminal sentence punctuation."""
    assert repair_command_text("next tab.") == "next tab"
    assert repair_command_text("scroll down!") == "scroll down"


@pytest.mark.parametrize(
    "phrase",
    [
        "search for headphones",
        "scroll down",
        "next tab",
        "go back",
        "click orders",
        "press enter",
        "type hello world",
        "open notes",
    ],
)
def test_non_brand_parse_command_unchanged_by_repair(phrase: str) -> None:
    """S0b regression: repair must not change non-brand grammar outcomes."""
    assert parse_command(repair_command_text(phrase)) == parse_command(phrase)


def test_compound_and_delimiter_preserved() -> None:
    """Fuzzy repair must not eat clause delimiters in compound commands."""
    assert repair_command_text("open amazon and click orders") == "open amazon and click orders"
    assert repair_command_text("open amazin and scroll down") == "open amazon and scroll down"


def test_already_correct_brand_stays_parseable() -> None:
    """Correct transcripts are not mangled into something unusable."""
    assert repair_command_text("open reddit") == "open reddit"
    assert repair_command_text("ask claude what is two plus two").startswith("ask claude")
