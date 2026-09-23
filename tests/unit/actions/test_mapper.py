"""Tests for the M2 modality-neutral Action Mapper."""

from __future__ import annotations

import pytest
from gesture_control.actions import ActionMapper, Intent, IntentType
from gesture_control.backends.base import BrowserAction, InputBackend


class _FakeBackend(InputBackend):
    """Record gated synthetic input without interacting with an operating system."""

    def __init__(self) -> None:
        super().__init__()
        self.moves: list[tuple[int, int]] = []
        self.click_count = 0
        self.opened_urls: list[str] = []
        self.browser_actions: list[BrowserAction] = []
        self.clicked_elements: list[str] = []
        self.typed: list[tuple[str, str]] = []

    def screen_size(self) -> tuple[int, int]:
        return 100, 100

    def move_to(self, x: int, y: int) -> None:
        if not self.safe_pause.is_paused:
            self.moves.append((x, y))

    def click_left(self) -> None:
        if not self.safe_pause.is_paused:
            self.click_count += 1

    def open_url(self, url: str) -> None:
        if not self.safe_pause.is_paused:
            self.opened_urls.append(url)

    def navigate_browser(self, action: BrowserAction) -> None:
        if not self.safe_pause.is_paused:
            self.browser_actions.append(action)

    def click_element(self, target_id: str) -> None:
        if not self.safe_pause.is_paused:
            self.clicked_elements.append(target_id)

    def type_text(self, target_id: str, text: str) -> None:
        if not self.safe_pause.is_paused:
            self.typed.append((target_id, text))


def test_action_mapper_dispatches_cursor_move_and_click() -> None:
    """M2 intents should invoke their matching backend operations."""
    backend = _FakeBackend()
    mapper = ActionMapper(backend)

    mapper.dispatch(Intent(IntentType.MOVE_CURSOR, x=12, y=34))
    mapper.dispatch(Intent(IntentType.CLICK_LEFT))

    assert backend.moves == [(12, 34)]
    assert backend.click_count == 1


def test_safe_pause_blocks_actions_at_backend_boundary() -> None:
    """A paused backend must reject input even when an intent is dispatched."""
    backend = _FakeBackend()
    backend.safe_pause.toggle()
    mapper = ActionMapper(backend)

    mapper.dispatch(Intent(IntentType.MOVE_CURSOR, x=12, y=34))
    mapper.dispatch(Intent(IntentType.CLICK_LEFT))

    assert backend.moves == []
    assert backend.click_count == 0


def test_cursor_intent_requires_both_coordinates() -> None:
    """Invalid cursor intents should not reach the backend."""
    with pytest.raises(ValueError, match="require both x and y"):
        ActionMapper(_FakeBackend()).dispatch(Intent(IntentType.MOVE_CURSOR, x=12))


def test_action_mapper_opens_the_url_from_an_open_url_intent() -> None:
    """OPEN_URL intents should ask the backend to open the given URL."""
    backend = _FakeBackend()
    mapper = ActionMapper(backend)

    mapper.dispatch(Intent(IntentType.OPEN_URL, url="https://cursor.com"))

    assert backend.opened_urls == ["https://cursor.com"]


def test_open_url_intent_requires_a_url() -> None:
    """OPEN_URL without a url must raise and must not touch the backend."""
    backend = _FakeBackend()
    mapper = ActionMapper(backend)

    with pytest.raises(ValueError):
        mapper.dispatch(Intent(IntentType.OPEN_URL))

    assert backend.opened_urls == []


def test_safe_pause_blocks_open_url() -> None:
    """A paused backend must not open URLs even when OPEN_URL is dispatched."""
    backend = _FakeBackend()
    backend.safe_pause.toggle()
    mapper = ActionMapper(backend)

    mapper.dispatch(Intent(IntentType.OPEN_URL, url="https://www.apple.com"))

    assert backend.opened_urls == []


@pytest.mark.parametrize(
    ("intent_type", "action"),
    [
        (IntentType.NEXT_TAB, BrowserAction.NEXT_TAB),
        (IntentType.PREVIOUS_TAB, BrowserAction.PREVIOUS_TAB),
        (IntentType.NEW_TAB, BrowserAction.NEW_TAB),
        (IntentType.CLOSE_TAB, BrowserAction.CLOSE_TAB),
        (IntentType.GO_BACK, BrowserAction.GO_BACK),
        (IntentType.GO_FORWARD, BrowserAction.GO_FORWARD),
        (IntentType.RELOAD_PAGE, BrowserAction.RELOAD_PAGE),
    ],
)
def test_action_mapper_dispatches_browser_navigation(
    intent_type: IntentType, action: BrowserAction
) -> None:
    """Navigation intents should map onto one typed backend operation."""
    backend = _FakeBackend()

    ActionMapper(backend).dispatch(Intent(intent_type))

    assert backend.browser_actions == [action]


def test_action_mapper_clicks_a_named_page_element() -> None:
    """CLICK_ELEMENT should forward the indexed element id."""
    backend = _FakeBackend()
    ActionMapper(backend).dispatch(Intent(IntentType.CLICK_ELEMENT, target_id="e1"))

    assert backend.clicked_elements == ["e1"]


def test_click_element_intent_requires_a_target_id() -> None:
    """CLICK_ELEMENT without a target must raise and must not click."""
    backend = _FakeBackend()

    with pytest.raises(ValueError, match="target_id"):
        ActionMapper(backend).dispatch(Intent(IntentType.CLICK_ELEMENT))

    assert backend.clicked_elements == []


def test_action_mapper_types_into_a_named_field() -> None:
    """TYPE_TEXT should forward the field id and the literal text."""
    backend = _FakeBackend()
    ActionMapper(backend).dispatch(Intent(IntentType.TYPE_TEXT, target_id="e2", text="hello"))

    assert backend.typed == [("e2", "hello")]


def test_type_text_intent_requires_text() -> None:
    """TYPE_TEXT without text must raise and must not type."""
    backend = _FakeBackend()

    with pytest.raises(ValueError, match="text"):
        ActionMapper(backend).dispatch(Intent(IntentType.TYPE_TEXT, target_id="e2"))

    assert backend.typed == []


def test_safe_pause_blocks_page_actions() -> None:
    """A paused backend must not click or type even when those intents are dispatched."""
    backend = _FakeBackend()
    backend.safe_pause.toggle()
    mapper = ActionMapper(backend)

    mapper.dispatch(Intent(IntentType.CLICK_ELEMENT, target_id="e1"))
    mapper.dispatch(Intent(IntentType.TYPE_TEXT, target_id="e2", text="hello"))

    assert backend.clicked_elements == []
    assert backend.typed == []
