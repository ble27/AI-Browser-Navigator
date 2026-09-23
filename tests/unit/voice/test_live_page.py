"""Tests for resolving commands against a live-page bridge snapshot."""

from __future__ import annotations

import pytest
from gesture_control.actions import Intent, IntentType
from gesture_control.browser.bridge import (
    BridgeDisconnectedError,
    PageElement,
    PageSnapshot,
)
from gesture_control.voice.live_page import (
    LivePageCommandResolver,
    PageCommandUnavailableError,
)


class _Bridge:
    def __init__(self, elements: tuple[PageElement, ...], disconnected: bool = False) -> None:
        self._elements = elements
        self._disconnected = disconnected
        self.snapshot_calls = 0

    def snapshot(self) -> PageSnapshot:
        self.snapshot_calls += 1
        if self._disconnected:
            raise BridgeDisconnectedError("extension unavailable")
        return PageSnapshot(
            url="https://example.test",
            title="Fixture",
            elements=self._elements,
        )


def test_non_page_command_does_not_request_snapshot() -> None:
    bridge = _Bridge(())
    resolver = LivePageCommandResolver(bridge)  # type: ignore[arg-type]

    assert resolver.resolve("scroll down") is None
    assert bridge.snapshot_calls == 0


def test_search_resolves_to_page_search_before_omnibox_fallback() -> None:
    bridge = _Bridge((PageElement("search", "textbox", "Search Amazon"),))
    resolver = LivePageCommandResolver(bridge)  # type: ignore[arg-type]

    assert resolver.resolve("search for mechanical keyboard") == Intent(
        IntentType.SUBMIT_TEXT,
        target_id="search",
        text="mechanical keyboard",
    )


def test_disconnected_search_falls_back_but_click_reports_bridge_error() -> None:
    bridge = _Bridge((), disconnected=True)
    resolver = LivePageCommandResolver(bridge)  # type: ignore[arg-type]

    assert resolver.resolve("search for mechanical keyboard") is None
    with pytest.raises(PageCommandUnavailableError, match="extension unavailable"):
        resolver.resolve("click add to cart")


def test_warm_snapshot_is_reused_once_by_resolve() -> None:
    bridge = _Bridge((PageElement("btn", "button", "Submit Answer"),))
    resolver = LivePageCommandResolver(bridge)  # type: ignore[arg-type]

    resolver.warm()
    assert bridge.snapshot_calls == 1
    assert resolver.resolve("submit answer") == Intent(
        IntentType.CLICK_ELEMENT,
        target_id="btn",
    )
    assert bridge.snapshot_calls == 1
    assert resolver.resolve("submit answer") == Intent(
        IntentType.CLICK_ELEMENT,
        target_id="btn",
    )
    assert bridge.snapshot_calls == 2
