"""Unit tests for on-page search against a fake Chrome bridge."""

from __future__ import annotations

from gesture_control.browser.bridge import PageElement, PageSnapshot
from gesture_control.browser.site_search import try_site_search


class _FakeBridge:
    """In-memory bridge that records click/submit operations."""

    def __init__(self, *snapshots: PageSnapshot) -> None:
        self._snapshots = list(snapshots)
        self.clicks: list[str] = []
        self.submits: list[tuple[str, str]] = []

    def snapshot(self, timeout: float | None = None) -> PageSnapshot:
        del timeout
        if not self._snapshots:
            raise RuntimeError("no snapshot")
        return self._snapshots.pop(0)

    def click(self, target_id: str, timeout: float | None = None) -> None:
        del timeout
        self.clicks.append(target_id)

    def type_and_submit(self, target_id: str, text: str, timeout: float | None = None) -> None:
        del timeout
        self.submits.append((target_id, text))


def test_try_site_search_uses_unique_search_textbox() -> None:
    bridge = _FakeBridge(
        PageSnapshot(
            url="https://example.com",
            title="Example",
            elements=(
                PageElement("e1", "textbox", "Search"),
                PageElement("e2", "button", "Go"),
            ),
        )
    )

    assert try_site_search(bridge, "mac mini") is True
    assert bridge.submits == [("e1", "mac mini")]
    assert bridge.clicks == []


def test_try_site_search_opens_collapsed_search_button() -> None:
    closed = PageSnapshot(
        url="https://www.apple.com/",
        title="Apple",
        elements=(
            PageElement("nav", "link", "Store"),
            PageElement("sbtn", "button", "Search apple.com"),
        ),
    )
    opened = PageSnapshot(
        url="https://www.apple.com/",
        title="Apple",
        elements=(
            PageElement("nav", "link", "Store"),
            PageElement("sbtn", "button", "Search apple.com"),
            PageElement("sbox", "textbox", "Search apple.com"),
        ),
    )
    bridge = _FakeBridge(closed, opened)

    assert try_site_search(bridge, "airpods") is True
    assert bridge.clicks == ["sbtn"]
    assert bridge.submits == [("sbox", "airpods")]


def test_try_site_search_returns_false_without_unique_control() -> None:
    bridge = _FakeBridge(
        PageSnapshot(
            url="https://example.com",
            title="Example",
            elements=(
                PageElement("a", "textbox", "Search products"),
                PageElement("b", "textbox", "Search help"),
            ),
        )
    )

    assert try_site_search(bridge, "query") is False
    assert bridge.submits == []


def test_try_site_search_returns_false_when_bridge_unavailable() -> None:
    class _Dead:
        def snapshot(self, timeout: float | None = None) -> PageSnapshot:
            del timeout
            raise RuntimeError("disconnected")

    assert try_site_search(_Dead(), "query") is False  # type: ignore[arg-type]
