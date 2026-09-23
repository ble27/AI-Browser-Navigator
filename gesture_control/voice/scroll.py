"""Parse deterministic scrolling commands with bounded duration scaling."""

from __future__ import annotations

import math
import re

from gesture_control.actions import Intent, IntentType

DEFAULT_SCROLL_PAGES = 3
LARGE_SCROLL_PAGES = 6
MAX_SCROLL_PAGES = 10
_NUMBER_WORDS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_DIRECTION_PATTERN = r"(?P<direction>up|down)"
_EXPLICIT_PAGES = re.compile(
    rf"^scroll {_DIRECTION_PATTERN} "
    r"(?P<count>[1-9]|10|one|two|three|four|five|six|seven|eight|nine|ten) pages?$"
)
_EXPLICIT_PAGES_FIRST = re.compile(
    r"^scroll (?P<count>[1-9]|10|one|two|three|four|five|six|seven|eight|nine|ten) "
    rf"pages? {_DIRECTION_PATTERN}$"
)


def parse_scroll_command(
    transcript: str,
    utterance_duration_s: float | None = None,
) -> Intent | None:
    """Parse a scroll command into signed page units.

    Positive amounts mean up and negative amounts mean down. A plain
    ``scroll up``/``scroll down`` scales from three through ten pages using
    captured utterance duration. Explicit size/page modifiers always win.

    Args:
        transcript: Raw voice-style command text.
        utterance_duration_s: Optional captured audio duration. Used only for
            a plain scroll command.

    Returns:
        A bounded non-zero ``SCROLL`` intent, or ``None`` for unknown text.

    Raises:
        ValueError: If ``utterance_duration_s`` is negative or non-finite.
    """
    if utterance_duration_s is not None and (
        not math.isfinite(utterance_duration_s) or utterance_duration_s < 0
    ):
        raise ValueError("utterance_duration_s must be finite and non-negative.")

    normalized = _normalize(transcript)
    edge_amounts = {
        "scroll to top": MAX_SCROLL_PAGES,
        "go to top": MAX_SCROLL_PAGES,
        "top of page": MAX_SCROLL_PAGES,
        "scroll to bottom": -MAX_SCROLL_PAGES,
        "go to bottom": -MAX_SCROLL_PAGES,
        "bottom of page": -MAX_SCROLL_PAGES,
    }
    if normalized in edge_amounts:
        return Intent(IntentType.SCROLL, amount=edge_amounts[normalized])

    explicit_match = _EXPLICIT_PAGES.fullmatch(normalized) or _EXPLICIT_PAGES_FIRST.fullmatch(
        normalized
    )
    if explicit_match is not None:
        count_text = explicit_match.group("count")
        count = int(count_text) if count_text.isdigit() else _NUMBER_WORDS[count_text]
        return _scroll_intent(explicit_match.group("direction"), count)

    modifier_patterns: tuple[tuple[re.Pattern[str], int], ...] = (
        (
            re.compile(rf"^scroll (?:a )?(?:small|little)(?: bit)? {_DIRECTION_PATTERN}$"),
            1,
        ),
        (
            re.compile(rf"^scroll {_DIRECTION_PATTERN} (?:a )?(?:small|little)(?: bit)?$"),
            1,
        ),
        (
            re.compile(rf"^scroll (?:a )?(?:large|big) {_DIRECTION_PATTERN}$"),
            LARGE_SCROLL_PAGES,
        ),
        (
            re.compile(rf"^scroll {_DIRECTION_PATTERN} (?:a )?(?:large|big|lot)$"),
            LARGE_SCROLL_PAGES,
        ),
        (
            re.compile(rf"^scroll a lot {_DIRECTION_PATTERN}$"),
            LARGE_SCROLL_PAGES,
        ),
    )
    for pattern, pages in modifier_patterns:
        match = pattern.fullmatch(normalized)
        if match is not None:
            return _scroll_intent(match.group("direction"), pages)

    page_match = re.fullmatch(r"page (?P<direction>up|down)", normalized)
    if page_match is not None:
        return _scroll_intent(page_match.group("direction"), 1)

    plain_match = re.fullmatch(r"scroll (?P<direction>up|down)", normalized)
    if plain_match is None:
        return None
    pages = _duration_scaled_pages(utterance_duration_s)
    return _scroll_intent(plain_match.group("direction"), pages)


def _normalize(transcript: str) -> str:
    """Normalize punctuation, whitespace, and textual held directions."""
    words_only = re.sub(r"[^\w\s]", " ", transcript.casefold())
    normalized = " ".join(words_only.split())
    held_match = re.fullmatch(r"scroll (dow[n]+|up+)", normalized)
    if held_match is None:
        return normalized
    direction = "down" if held_match.group(1).startswith("down") else "up"
    return f"scroll {direction}"


def _duration_scaled_pages(utterance_duration_s: float | None) -> int:
    """Convert optional audio duration to a bounded plain-scroll magnitude."""
    if utterance_duration_s is None:
        return DEFAULT_SCROLL_PAGES
    return min(MAX_SCROLL_PAGES, max(DEFAULT_SCROLL_PAGES, math.ceil(utterance_duration_s)))


def _scroll_intent(direction: str, pages: int) -> Intent:
    """Build a signed scroll intent from a normalized direction and magnitude."""
    sign = 1 if direction == "up" else -1
    return Intent(IntentType.SCROLL, amount=sign * pages)
