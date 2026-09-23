"""Tests for deterministic signed scrolling and duration scaling."""

from __future__ import annotations

import pytest
from gesture_control.actions import Intent, IntentType
from gesture_control.voice.commands import parse_command


@pytest.mark.parametrize(
    ("phrase", "amount"),
    [
        ("page up", 1),
        ("page down", -1),
        ("scroll a little up", 1),
        ("scroll down a small bit", -1),
        ("scroll large up", 6),
        ("scroll down a lot", -6),
        ("scroll up 4 pages", 4),
        ("scroll ten pages down", -10),
        ("scroll to top", 10),
        ("bottom of page", -10),
    ],
)
def test_scroll_modifiers_produce_signed_page_units(phrase: str, amount: int) -> None:
    """Positive page units scroll up; negative page units scroll down."""
    assert parse_command(phrase) == Intent(IntentType.SCROLL, amount=amount)


@pytest.mark.parametrize(
    ("duration_s", "amount"),
    [(0.2, -3), (3.1, -4), (7.0, -7), (99.0, -10)],
)
def test_plain_scroll_scales_and_caps_from_audio_duration(
    duration_s: float,
    amount: int,
) -> None:
    """Only a plain scroll should derive bounded magnitude from audio duration."""
    assert parse_command("scroll down", duration_s) == Intent(IntentType.SCROLL, amount=amount)


def test_held_text_does_not_replace_duration_as_magnitude_source() -> None:
    """Repeated terminal letters are tolerated but do not set magnitude."""
    assert parse_command("scroll downnnnn", 4.2) == Intent(IntentType.SCROLL, amount=-5)


@pytest.mark.parametrize("phrase", ["page down", "scroll down 2 pages", "scroll down a lot"])
def test_explicit_scroll_modifiers_win_over_duration(phrase: str) -> None:
    """Duration must not change page, numeric, or qualitative modifiers."""
    expected = {
        "page down": -1,
        "scroll down 2 pages": -2,
        "scroll down a lot": -6,
    }
    assert parse_command(phrase, 10.0) == Intent(IntentType.SCROLL, amount=expected[phrase])


@pytest.mark.parametrize(
    "phrase",
    ["scroll", "scroll sideways", "scroll down 0 pages", "scroll down 11 pages"],
)
def test_invalid_scroll_phrases_are_rejected(phrase: str) -> None:
    """Unknown directions and out-of-range counts must not produce intents."""
    assert parse_command(phrase) is None


@pytest.mark.parametrize("duration_s", [-0.1, float("inf"), float("nan")])
def test_invalid_scroll_duration_is_rejected(duration_s: float) -> None:
    """Duration input must be finite and non-negative."""
    with pytest.raises(ValueError, match="finite and non-negative"):
        parse_command("scroll down", duration_s)
