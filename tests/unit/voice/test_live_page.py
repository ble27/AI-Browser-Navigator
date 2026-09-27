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
    assert resolver.resolve("open amazon") is None
    with pytest.raises(PageCommandUnavailableError, match="extension unavailable"):
        resolver.resolve("click add to cart")


@pytest.mark.parametrize(
    "phrase",
    [
        "hit submit",
        "pick the submit",
        "push submit",
        "mouse click on submit",
        "left click submit",
        "write hello into email",
        "fill email with hello",
        "type hello into email",
        "tap checkout",
    ],
)
def test_disconnected_everyday_page_verbs_report_bridge_error(phrase: str) -> None:
    """Explicit page mutations must not silently no-op when the bridge is down."""
    bridge = _Bridge((), disconnected=True)
    resolver = LivePageCommandResolver(bridge)  # type: ignore[arg-type]

    with pytest.raises(PageCommandUnavailableError, match="extension unavailable"):
        resolver.resolve(phrase)


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


def test_ranked_click_orders_alias() -> None:
    """Soft-rank maps spoken 'orders' onto Amazon-style labels."""
    bridge = _Bridge(
        (
            PageElement("e1", "link", "Account & Lists"),
            PageElement("e2", "link", "Returns & Orders"),
            PageElement("e3", "link", "Cart"),
        ),
    )
    resolver = LivePageCommandResolver(bridge)  # type: ignore[arg-type]
    assert resolver.resolve("click orders") == Intent(
        IntentType.CLICK_ELEMENT,
        target_id="e2",
    )


def test_ranked_click_fails_closed_when_ambiguous() -> None:
    bridge = _Bridge(
        (
            PageElement("e1", "link", "Orders today"),
            PageElement("e2", "link", "Orders yesterday"),
        ),
    )
    resolver = LivePageCommandResolver(bridge)  # type: ignore[arg-type]
    assert resolver.resolve("click orders") is None
