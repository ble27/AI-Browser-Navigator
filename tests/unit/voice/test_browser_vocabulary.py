"""Tests for the expanded deterministic browser voice vocabulary."""

from __future__ import annotations

import pytest
from gesture_control.actions import Intent, IntentType
from gesture_control.voice.commands import parse_command


@pytest.mark.parametrize(
    ("phrase", "kind"),
    [
        ("Close current web.", IntentType.CLOSE_TAB),
        ("close current website", IntentType.CLOSE_TAB),
        ("close current page", IntentType.CLOSE_TAB),
        ("close current tab", IntentType.CLOSE_TAB),
        ("close browser tab", IntentType.CLOSE_TAB),
        ("switch to next tab", IntentType.NEXT_TAB),
        ("go to previous tab", IntentType.PREVIOUS_TAB),
        ("refresh current page", IntentType.RELOAD_PAGE),
        ("reload current website", IntentType.RELOAD_PAGE),
        ("restore closed tab", IntentType.REOPEN_TAB),
    ],
)
def test_navigation_aliases_are_explicit_and_tolerant(
    phrase: str,
    kind: IntentType,
) -> None:
    """Supported complete phrases should tolerate case and punctuation."""
    assert parse_command(phrase) == Intent(kind)


@pytest.mark.parametrize(
    ("phrase", "url"),
    [
        ("open Amazon", "https://www.amazon.com"),
        ("open Google website", "https://www.google.com"),
        ("visit YouTube", "https://www.youtube.com"),
        ("go to GitHub", "https://github.com"),
        ("open Cursor", "https://cursor.com"),
        ("visit Apple site", "https://www.apple.com"),
        ("open Reddit", "https://www.reddit.com"),
        ("visit Wikipedia", "https://www.wikipedia.org"),
        ("open Netflix", "https://www.netflix.com"),
        ("go to Twitter", "https://x.com"),
        ("open example.com", "https://example.com"),
        ("go to docs.example.co.uk", "https://docs.example.co.uk"),
        ("visit example.com/docs", "https://example.com/docs"),
    ],
)
def test_open_site_aliases_and_public_bare_domains(phrase: str, url: str) -> None:
    """Allowlisted names and valid dotted domains should become HTTPS URLs."""
    assert parse_command(phrase) == Intent(IntentType.OPEN_URL, url=url)


@pytest.mark.parametrize(
    "phrase",
    [
        "open unknownword",
        "open localhost",
        "open localhost.local",
        "open server.internal",
        "open 127.0.0.1",
        "open 192.168.1.2",
        "open [::1]",
        "open user:pass@example.com",
        "open https://user:pass@example.com",
        "open http://example.com",
        "open file:///tmp/test",
        "open javascript:alert(1)",
        "open example .com",
        "open -bad.example",
        "open example.c",
        "open github first result",
        "open google first link",
        "open amazon orders",
    ],
)
def test_open_site_rejects_unsafe_or_non_domain_inputs(phrase: str) -> None:
    """Unsafe URL forms and arbitrary words must not become open intents."""
    assert parse_command(phrase) is None


@pytest.mark.parametrize(
    ("phrase", "query"),
    [
        ("search for accessibility tools", "accessibility tools"),
        ("look up Python pynput", "Python pynput"),
        ("lookup weather tomorrow", "weather tomorrow"),
        ("google exact phrase!", "exact phrase!"),
        ("find local-first software online", "local-first software"),
    ],
)
def test_search_phrases_preserve_literal_query(phrase: str, query: str) -> None:
    """Search commands should carry query text without interpreting it."""
    assert parse_command(phrase) == Intent(IntentType.SEARCH_WEB, text=query)


@pytest.mark.parametrize(
    "phrase",
    ["search for", "look up", "lookup", "google", "find online", "find cats nearby"],
)
def test_incomplete_search_phrases_are_rejected(phrase: str) -> None:
    """A search intent always requires a complete fixed form and non-empty text."""
    assert parse_command(phrase) is None
