"""Every IntentType must dispatch, and every voice-reachable one must have a phrase."""

from __future__ import annotations

from gesture_control.actions import ActionMapper, Intent, IntentType
from gesture_control.backends.base import (
    BrowserAction,
    FocusedPageFieldAction,
    InputBackend,
    LaunchableApp,
    PressableKey,
)
from gesture_control.voice.commands import parse_command
from gesture_control.voice.desktop import parse_app_command
from gesture_control.voice.page import PageElement, resolve_page_command

_SAMPLES: dict[IntentType, Intent] = {
    IntentType.MOVE_CURSOR: Intent(IntentType.MOVE_CURSOR, x=1, y=2),
    IntentType.CLICK_LEFT: Intent(IntentType.CLICK_LEFT),
    IntentType.OPEN_URL: Intent(IntentType.OPEN_URL, url="https://example.com"),
    IntentType.NEXT_TAB: Intent(IntentType.NEXT_TAB),
    IntentType.PREVIOUS_TAB: Intent(IntentType.PREVIOUS_TAB),
    IntentType.NEW_TAB: Intent(IntentType.NEW_TAB),
    IntentType.CLOSE_TAB: Intent(IntentType.CLOSE_TAB),
    IntentType.GO_BACK: Intent(IntentType.GO_BACK),
    IntentType.GO_FORWARD: Intent(IntentType.GO_FORWARD),
    IntentType.RELOAD_PAGE: Intent(IntentType.RELOAD_PAGE),
    IntentType.REOPEN_TAB: Intent(IntentType.REOPEN_TAB),
    IntentType.SEARCH_WEB: Intent(IntentType.SEARCH_WEB, text="query"),
    IntentType.SCROLL: Intent(IntentType.SCROLL, amount=-1),
    IntentType.CLICK_ELEMENT: Intent(IntentType.CLICK_ELEMENT, target_id="e1"),
    IntentType.FOCUS_ELEMENT: Intent(IntentType.FOCUS_ELEMENT, target_id="e2"),
    IntentType.EDIT_FOCUSED_PAGE_FIELD: Intent(
        IntentType.EDIT_FOCUSED_PAGE_FIELD,
        field_action=FocusedPageFieldAction.DELETE_LINE,
    ),
    IntentType.TYPE_TEXT: Intent(IntentType.TYPE_TEXT, target_id="e3", text="hi"),
    IntentType.SUBMIT_TEXT: Intent(IntentType.SUBMIT_TEXT, target_id="e3", text="hi"),
    IntentType.FOCUS_CHROME_OMNIBOX: Intent(IntentType.FOCUS_CHROME_OMNIBOX),
    IntentType.OPEN_APP: Intent(IntentType.OPEN_APP, app=LaunchableApp.NOTES),
    IntentType.TYPE_FOCUSED: Intent(IntentType.TYPE_FOCUSED, text="hi"),
    IntentType.PRESS_KEY: Intent(IntentType.PRESS_KEY, key=PressableKey.ENTER),
}


class _RecordingBackend(InputBackend):
    """Count one call per dispatched intent."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def screen_size(self) -> tuple[int, int]:
        return 100, 100

    def move_to(self, x: int, y: int) -> None:
        del x, y
        self.calls.append("move_to")

    def click_left(self) -> None:
        self.calls.append("click_left")

    def open_url(self, url: str) -> None:
        del url
        self.calls.append("open_url")

    def navigate_browser(self, action: BrowserAction) -> None:
        self.calls.append(action.value)

    def search_web(self, text: str) -> None:
        del text
        self.calls.append("search_web")

    def scroll(self, amount: int) -> None:
        del amount
        self.calls.append("scroll")

    def click_element(self, target_id: str) -> None:
        del target_id
        self.calls.append("click_element")

    def type_text(self, target_id: str, text: str) -> None:
        del target_id, text
        self.calls.append("type_text")

    def focus_element(self, target_id: str) -> None:
        del target_id
        self.calls.append("focus_element")

    def edit_focused_page_field(self, action: FocusedPageFieldAction) -> None:
        self.calls.append(action.value)

    def submit_text(self, target_id: str, text: str) -> None:
        del target_id, text
        self.calls.append("submit_text")

    def focus_chrome_omnibox(self) -> None:
        self.calls.append("focus_chrome_omnibox")

    def open_app(self, app: LaunchableApp) -> None:
        del app
        self.calls.append("open_app")

    def type_focused(self, text: str) -> None:
        del text
        self.calls.append("type_focused")

    def press_key(self, key: PressableKey) -> None:
        del key
        self.calls.append("press_key")


def test_every_intent_type_has_a_sample_and_reaches_the_backend() -> None:
    assert set(_SAMPLES) == set(IntentType)
    for kind, intent in _SAMPLES.items():
        backend = _RecordingBackend()
        ActionMapper(backend).dispatch(intent)
        assert backend.calls, f"{kind.value} did not call the backend"


_VOICE_PHRASES: dict[str, IntentType] = {
    "open reddit": IntentType.OPEN_URL,
    "next tab": IntentType.NEXT_TAB,
    "previous tab": IntentType.PREVIOUS_TAB,
    "new tab": IntentType.NEW_TAB,
    "close tab": IntentType.CLOSE_TAB,
    "go back": IntentType.GO_BACK,
    "go forward": IntentType.GO_FORWARD,
    "reload": IntentType.RELOAD_PAGE,
    "reopen closed tab": IntentType.REOPEN_TAB,
    "search for headphones": IntentType.SEARCH_WEB,
    "scroll down": IntentType.SCROLL,
    "delete line": IntentType.EDIT_FOCUSED_PAGE_FIELD,
    "focus chrome search bar": IntentType.FOCUS_CHROME_OMNIBOX,
    "open notes": IntentType.OPEN_APP,
    "type hello": IntentType.TYPE_FOCUSED,
    "return": IntentType.PRESS_KEY,
}


def _command_intent(phrase: str) -> Intent | None:
    """Resolve a phrase the way the planner does for closed commands."""
    if phrase.startswith("open "):
        app = parse_app_command(phrase)
        if app is not None:
            return app
    return parse_command(phrase)


def test_voice_phrases_cover_every_command_intent() -> None:
    produced: set[IntentType] = set()
    for phrase, kind in _VOICE_PHRASES.items():
        intent = _command_intent(phrase)
        assert intent is not None, phrase
        assert intent.kind is kind
        produced.add(intent.kind)
    elements = (
        PageElement("e1", "link", "Pricing"),
        PageElement("e2", "textbox", "Email"),
        PageElement("e3", "textbox", "Search"),
    )
    assert resolve_page_command("click pricing", elements).kind is IntentType.CLICK_ELEMENT  # type: ignore[union-attr]
    assert resolve_page_command("focus email", elements).kind is IntentType.FOCUS_ELEMENT  # type: ignore[union-attr]
    assert resolve_page_command("type hi into email", elements).kind is IntentType.TYPE_TEXT  # type: ignore[union-attr]
    assert resolve_page_command("search headphones", elements).kind is IntentType.SUBMIT_TEXT  # type: ignore[union-attr]
    page_kinds = {
        IntentType.CLICK_ELEMENT,
        IntentType.FOCUS_ELEMENT,
        IntentType.TYPE_TEXT,
        IntentType.SUBMIT_TEXT,
    }
    gesture_kinds = {IntentType.MOVE_CURSOR, IntentType.CLICK_LEFT}
    assert produced | page_kinds | gesture_kinds == set(IntentType)
