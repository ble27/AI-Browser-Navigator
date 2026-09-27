"""Adversarial tests for Chrome snapshot URL allowlisting and payload bounds."""

from __future__ import annotations

import pytest
from gesture_control.browser.bridge import (
    BridgeError,
    _is_allowed_snapshot_url,
    _parse_seo_meta,
    _parse_snapshot,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/path",
        "HTTPS://Example.COM/path",
        "http://127.0.0.1:8765/seo_fixture.html",
        "http://localhost:8765/apple_fixture.html",
        "HTTP://127.0.0.1/",
        "Http://LocalHost/x",
    ],
)
def test_allowed_snapshot_urls_accept_https_and_exact_loopback(url: str) -> None:
    assert _is_allowed_snapshot_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://evil.com/",
        "http://127.0.0.1.evil.com/",
        "http://127.0.0.1@evil.com/",
        "http://127.0.0.1%2eevil.com/",
        "http://localhost.evil.com/",
        "http://localhost@evil.com/",
        "http://localhost%2eevil.com/",
        "http://127.0.0.1.attacker.com/",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,hi",
        "https://",
        "",
        "ftp://127.0.0.1/",
        "http://192.168.0.1/",
        "http://[::1]/",
    ],
)
def test_snapshot_url_allowlist_rejects_spoofs_and_non_loopback_http(url: str) -> None:
    assert not _is_allowed_snapshot_url(url)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"url": "https://x", "title": "t"},
        {"url": "https://x", "title": "t", "elements": [], "extra": 1},
        {"url": "http://evil.com", "title": "t", "elements": []},
        {"url": "http://127.0.0.1.evil.com/", "title": "t", "elements": []},
        {"url": "http://127.0.0.1@evil.com/", "title": "t", "elements": []},
        {"url": "https://x", "title": 1, "elements": []},
        {"url": "https://x", "title": "t", "elements": "nope"},
        {"url": "https://x", "title": "t", "elements": [{"id": "", "role": "button", "name": "x"}]},
        {"url": "https://x", "title": "t", "elements": [{"id": "e1", "role": "div", "name": "x"}]},
        {"url": "https://x", "title": "t", "elements": [{"id": "e1", "role": "button", "name": ""}]},
        {
            "url": "https://x",
            "title": "t",
            "elements": [{"id": "e1", "role": "button", "name": "x", "href": "/"}],
        },
        {"url": "https://x", "title": "t", "elements": [], "seo": "string"},
        {"url": "https://x", "title": "t", "elements": [], "seo": {"hack": 1}},
        {"url": "https://x", "title": "t", "elements": [], "seo": {"description": "x" * 2001}},
        {"url": "https://x", "title": "t", "elements": [], "seo": {"keywords": "not-a-list"}},
        {"url": "https://x", "title": "t", "elements": [], "seo": {"keywords": [""]}},
        {"url": "https://x", "title": "t", "elements": [], "seo": {"keywords": [1]}},
        {"url": "https://x", "title": "t", "elements": [], "seo": {"keywords": ["k" * 201]}},
        {"url": "https://x", "title": "x" * 501, "elements": []},
        {"url": "https://" + ("a" * 1990) + ".com", "title": "t", "elements": []},
        {
            "url": "https://x",
            "title": "t",
            "elements": [{"id": "e1", "role": "button", "name": "n" * 501}],
        },
        {
            "url": "https://x",
            "title": "t",
            "elements": [{"id": "i" * 201, "role": "button", "name": "ok"}],
        },
    ],
)
def test_parse_snapshot_rejects_malformed_or_oversized_payloads(
    payload: dict[str, object],
) -> None:
    with pytest.raises(BridgeError):
        _parse_snapshot(payload)


def test_parse_seo_meta_truncates_keyword_list_to_thirty_two() -> None:
    meta = _parse_seo_meta({"keywords": [f"k{i}" for i in range(40)]})

    assert len(meta.keywords) == 32
    assert meta.keywords[0] == "k0"
    assert meta.keywords[-1] == "k31"


def test_parse_seo_meta_treats_null_fields_as_empty() -> None:
    meta = _parse_seo_meta(
        {
            "description": None,
            "site_name": None,
            "og_title": None,
            "keywords": None,
            "canonical_url": None,
        }
    )

    assert meta.description == ""
    assert meta.site_name == ""
    assert meta.og_title == ""
    assert meta.keywords == ()
    assert meta.canonical_url == ""
