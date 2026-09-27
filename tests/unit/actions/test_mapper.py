"""Tests for the M2 modality-neutral Action Mapper."""

from __future__ import annotations

import pytest
from gesture_control.actions import ActionMapper, Intent, IntentType
from gesture_control.backends.base import (
    BrowserAction,
    FocusedPageFieldAction,
    InputBackend,
    LaunchableApp,
    PressableKey,
)
from gesture_control.voice.stream_contracts import MAX_TYPED_CHARS


class _FakeBackend(InputBackend):
    """Record gated synthetic input without interacting with an operating system."""

    def __init__(self) -> None:
        super().__init__()
        self.moves: list[tuple[int, int]] = []
        self.click_count = 0
        self.opened_urls: list[str] = []
        self.browser_actions: list[BrowserAction] = []
        self.searches: list[str] = []
        self.scrolls: list[int] = []
        self.clicked_elements: list[str] = []
        self.focused_elements: list[str] = []
        self.typed: list[tuple[str, str]] = []
        self.submitted: list[tuple[str, str]] = []
        self.omnibox_focuses = 0
        self.opened_apps: list[LaunchableApp] = []
        self.focused_text: list[str] = []
        self.pressed_keys: list[PressableKey] = []
        self.field_actions: list[FocusedPageFieldAction] = []

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

    def search_web(self, text: str) -> None:
        if not self.safe_pause.is_paused:
            self.searches.append(text)

    def scroll(self, amount: int) -> None:
        if not self.safe_pause.is_paused:
            self.scrolls.append(amount)

    def click_element(self, target_id: str) -> None:
        if not self.safe_pause.is_paused:
            self.clicked_elements.append(target_id)

    def type_text(self, target_id: str, text: str) -> None:
        if not self.safe_pause.is_paused:
            self.typed.append((target_id, text))

    def focus_element(self, target_id: str) -> None:
        if not self.safe_pause.is_paused:
            self.focused_elements.append(target_id)

    def submit_text(self, target_id: str, text: str) -> None:
        if not self.safe_pause.is_paused:
            self.submitted.append((target_id, text))

    def focus_chrome_omnibox(self) -> None:
        if not self.safe_pause.is_paused:
            self.omnibox_focuses += 1

    def open_app(self, app: LaunchableApp) -> None:
        if not self.safe_pause.is_paused:
            self.opened_apps.append(app)

    def type_focused(self, text: str) -> None:
        if not self.safe_pause.is_paused:
            self.focused_text.append(text)

    def press_key(self, key: PressableKey) -> None:
        if not self.safe_pause.is_paused:
            self.pressed_keys.append(key)

    def edit_focused_page_field(self, action: FocusedPageFieldAction) -> None:
        if not self.safe_pause.is_paused:
            self.field_actions.append(action)


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


def test_action_mapper_focuses_chrome_omnibox() -> None:
    backend = _FakeBackend()

    ActionMapper(backend).dispatch(Intent(IntentType.FOCUS_CHROME_OMNIBOX))

    assert backend.omnibox_focuses == 1


def test_action_mapper_dispatches_search_and_scroll_payloads() -> None:
    """Search text and signed page units should reach their backend methods."""
    backend = _FakeBackend()
    mapper = ActionMapper(backend)

    mapper.dispatch(Intent(IntentType.SEARCH_WEB, text="literal query"))
    mapper.dispatch(Intent(IntentType.SCROLL, amount=-4))

    assert backend.searches == ["literal query"]
    assert backend.scrolls == [-4]


@pytest.mark.parametrize(
    "intent",
    [
        Intent(IntentType.SEARCH_WEB),
        Intent(IntentType.SEARCH_WEB, text=""),
        Intent(IntentType.SCROLL),
        Intent(IntentType.SCROLL, amount=0),
    ],
)
def test_action_mapper_rejects_invalid_search_and_scroll_payloads(intent: Intent) -> None:
    """Missing search text and zero/missing scroll amounts must not dispatch."""
    backend = _FakeBackend()

    with pytest.raises(ValueError):
        ActionMapper(backend).dispatch(intent)

    assert backend.searches == []
    assert backend.scrolls == []


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


def test_action_mapper_focuses_and_submits_page_fields() -> None:
    backend = _FakeBackend()
    mapper = ActionMapper(backend)

    mapper.dispatch(Intent(IntentType.FOCUS_ELEMENT, target_id="search"))
    mapper.dispatch(
        Intent(
            IntentType.SUBMIT_TEXT,
            target_id="search",
            text="mechanical keyboard",
        )
    )

    assert backend.focused_elements == ["search"]
    assert backend.submitted == [("search", "mechanical keyboard")]


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


def test_action_mapper_opens_launchable_app() -> None:
    backend = _FakeBackend()
    ActionMapper(backend).dispatch(Intent(IntentType.OPEN_APP, app=LaunchableApp.NOTES))
    assert backend.opened_apps == [LaunchableApp.NOTES]


def test_open_app_intent_requires_app() -> None:
    backend = _FakeBackend()
    with pytest.raises(ValueError, match="app"):
        ActionMapper(backend).dispatch(Intent(IntentType.OPEN_APP))
    assert backend.opened_apps == []


def test_action_mapper_types_into_focus() -> None:
    backend = _FakeBackend()
    ActionMapper(backend).dispatch(Intent(IntentType.TYPE_FOCUSED, text="buy milk"))
    assert backend.focused_text == ["buy milk"]


def test_type_focused_rejects_empty_long_and_control_text() -> None:
    backend = _FakeBackend()
    mapper = ActionMapper(backend)
    with pytest.raises(ValueError, match="non-empty"):
        mapper.dispatch(Intent(IntentType.TYPE_FOCUSED, text=""))
    too_long = "a" * (MAX_TYPED_CHARS + 1)
    with pytest.raises(ValueError, match="exceeds"):
        mapper.dispatch(Intent(IntentType.TYPE_FOCUSED, text=too_long))
    with pytest.raises(ValueError, match="control"):
        mapper.dispatch(Intent(IntentType.TYPE_FOCUSED, text="hello\x00"))
    assert backend.focused_text == []


def test_action_mapper_presses_key() -> None:
    backend = _FakeBackend()
    ActionMapper(backend).dispatch(Intent(IntentType.PRESS_KEY, key=PressableKey.ENTER))
    assert backend.pressed_keys == [PressableKey.ENTER]


def test_press_key_intent_requires_key() -> None:
    backend = _FakeBackend()
    with pytest.raises(ValueError, match="key"):
        ActionMapper(backend).dispatch(Intent(IntentType.PRESS_KEY))
    assert backend.pressed_keys == []


def test_action_mapper_dispatches_focused_page_field_edit() -> None:
    backend = _FakeBackend()
    ActionMapper(backend).dispatch(
        Intent(
            IntentType.EDIT_FOCUSED_PAGE_FIELD,
            field_action=FocusedPageFieldAction.DELETE_WORD,
        )
    )

    assert backend.field_actions == [FocusedPageFieldAction.DELETE_WORD]


def test_action_mapper_rejects_focused_page_field_edit_without_action() -> None:
    backend = _FakeBackend()

    with pytest.raises(ValueError, match="field_action"):
        ActionMapper(backend).dispatch(Intent(IntentType.EDIT_FOCUSED_PAGE_FIELD))

    assert backend.field_actions == []


def test_safe_pause_blocks_focused_page_field_edits() -> None:
    backend = _FakeBackend()
    backend.safe_pause.toggle()

    ActionMapper(backend).dispatch(
        Intent(
            IntentType.EDIT_FOCUSED_PAGE_FIELD,
            field_action=FocusedPageFieldAction.DELETE_LINE,
        )
    )

    assert backend.field_actions == []
