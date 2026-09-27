"""Tests for offline voice commands that open a named site in Chrome.

These tests specify ``parse_browser_command`` only. They intentionally stay red
until ``IntentType.OPEN_URL``, ``Intent.url``, and the browser parser exist.
"""

from __future__ import annotations

import pytest
from gesture_control.actions import Intent, IntentType
from gesture_control.voice.browser import parse_browser_command


def test_open_cursor_webpage_resolves_to_cursor_site() -> None:
    """``open cursor webpage`` should open the Cursor homepage over HTTPS."""
    intent = parse_browser_command("open cursor webpage")

    assert intent == Intent(IntentType.OPEN_URL, url="https://cursor.com")


def test_open_the_cursor_website_is_case_insensitive() -> None:
    """Optional ``the`` and mixed case should still resolve to Cursor."""
    intent = parse_browser_command("Open the Cursor website")

    assert intent == Intent(IntentType.OPEN_URL, url="https://cursor.com")


def test_open_apple_website_resolves_to_apple_site() -> None:
    """``open apple website`` should open Apple's homepage over HTTPS."""
    intent = parse_browser_command("open apple website")

    assert intent == Intent(IntentType.OPEN_URL, url="https://www.apple.com")


def test_open_the_apple_webpage_allows_optional_the() -> None:
    """``webpage`` with optional ``the`` should still resolve to Apple."""
    intent = parse_browser_command("open the Apple webpage")

    assert intent == Intent(IntentType.OPEN_URL, url="https://www.apple.com")


def test_open_https_url_literal_passes_through() -> None:
    """An explicit https URL after ``open`` should become an OPEN_URL intent."""
    intent = parse_browser_command("open https://example.com/docs")

    assert intent == Intent(IntentType.OPEN_URL, url="https://example.com/docs")


def test_leading_and_trailing_whitespace_is_ignored() -> None:
    """Surrounding whitespace must not change a valid open-site command."""
    intent = parse_browser_command("  open cursor webpage  ")

    assert intent == Intent(IntentType.OPEN_URL, url="https://cursor.com")


def test_unknown_site_name_returns_none() -> None:
    """Unknown site names must not invent a domain or search fallback."""
    assert parse_browser_command("open my bank") is None


def test_http_url_is_rejected() -> None:
    """Only https URL literals are accepted; plain http must return None."""
    assert parse_browser_command("open http://example.com") is None


def test_javascript_scheme_is_rejected() -> None:
    """``javascript:`` URLs must never become an OPEN_URL intent."""
    assert parse_browser_command("open javascript:alert(1)") is None


def test_file_scheme_is_rejected() -> None:
    """``file:`` URLs must never become an OPEN_URL intent."""
    assert parse_browser_command("open file:///etc/passwd") is None


def test_unrelated_transcript_returns_none() -> None:
    """A non-open transcript is outside this parser's responsibility."""
    assert parse_browser_command("click") is None


def test_empty_transcript_returns_none() -> None:
    """An empty transcript must not produce an intent."""
    assert parse_browser_command("") is None


def test_open_alone_returns_none() -> None:
    """``open`` with no site or URL must return None."""
    assert parse_browser_command("open") is None


def test_open_cursor_site_resolves_to_cursor_site() -> None:
    """Spoken ``site`` is a synonym of webpage/website for Cursor."""
    intent = parse_browser_command("open cursor site")

    assert intent == Intent(IntentType.OPEN_URL, url="https://cursor.com")


def test_terminal_whisper_punctuation_is_ignored_for_site_aliases() -> None:
    """Sentence punctuation should not become part of a spoken site name."""
    assert parse_browser_command("Open cursor.") == Intent(
        IntentType.OPEN_URL, url="https://cursor.com"
    )


def test_https_url_with_userinfo_is_rejected() -> None:
    """HTTPS URLs that embed credentials must not become an OPEN_URL intent."""
    assert parse_browser_command("open https://user:pass@example.com") is None


@pytest.mark.parametrize(
    "transcript",
    [
        "open https://127.0.0.1/",
        "open https://localhost/",
        "open https://192.168.1.1/",
        "open https://[::1]/",
        "open https://evil.com:0/",
        "open https://evil.com:99999/",
        "open https://exa mple.com",
        "open https://example.com\\@evil.com",
        "open https://-bad.com",
        "open https://bad-.com",
        "open google.internal",
        "open google.local",
        "open 192.168.0.1",
    ],
)
def test_private_hosts_and_malformed_https_literals_are_rejected(transcript: str) -> None:
    assert parse_browser_command(transcript) is None
