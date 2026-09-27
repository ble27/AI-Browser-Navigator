"""Translate modality-neutral intents into gated input-backend calls."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from gesture_control.backends.base import (
    BrowserAction,
    FocusedPageFieldAction,
    InputBackend,
    LaunchableApp,
    PressableKey,
)
from gesture_control.voice.stream_contracts import MAX_TYPED_CHARS


class IntentType(StrEnum):
    """Actions currently understood by the shared Action Mapper."""

    MOVE_CURSOR = "move_cursor"
    CLICK_LEFT = "click_left"
    OPEN_URL = "open_url"
    NEXT_TAB = "next_tab"
    PREVIOUS_TAB = "previous_tab"
    NEW_TAB = "new_tab"
    CLOSE_TAB = "close_tab"
    GO_BACK = "go_back"
    GO_FORWARD = "go_forward"
    RELOAD_PAGE = "reload_page"
    REOPEN_TAB = "reopen_tab"
    SEARCH_WEB = "search_web"
    SCROLL = "scroll"
    CLICK_ELEMENT = "click_element"
    FOCUS_ELEMENT = "focus_element"
    EDIT_FOCUSED_PAGE_FIELD = "edit_focused_page_field"
    TYPE_TEXT = "type_text"
    SUBMIT_TEXT = "submit_text"
    FOCUS_CHROME_OMNIBOX = "focus_chrome_omnibox"
    OPEN_APP = "open_app"
    TYPE_FOCUSED = "type_focused"
    PRESS_KEY = "press_key"


_BROWSER_ACTIONS: dict[IntentType, BrowserAction] = {
    IntentType.NEXT_TAB: BrowserAction.NEXT_TAB,
    IntentType.PREVIOUS_TAB: BrowserAction.PREVIOUS_TAB,
    IntentType.NEW_TAB: BrowserAction.NEW_TAB,
    IntentType.CLOSE_TAB: BrowserAction.CLOSE_TAB,
    IntentType.GO_BACK: BrowserAction.GO_BACK,
    IntentType.GO_FORWARD: BrowserAction.GO_FORWARD,
    IntentType.RELOAD_PAGE: BrowserAction.RELOAD_PAGE,
    IntentType.REOPEN_TAB: BrowserAction.REOPEN_TAB,
}


@dataclass(frozen=True, slots=True)
class Intent:
    """A modality-neutral user action.

    Attributes:
        kind: The action requested by a gesture or voice command.
        x: Target cursor horizontal coordinate, required for ``MOVE_CURSOR``.
        y: Target cursor vertical coordinate, required for ``MOVE_CURSOR``.
        url: HTTPS URL to open, required for ``OPEN_URL``.
        target_id: Indexed page element id (``e1``, ``e2``, ...), required for
            ``CLICK_ELEMENT`` and ``TYPE_TEXT``.
        text: Literal text to type into a field, required for ``TYPE_TEXT``.
            For ``SEARCH_WEB``, this is the literal omnibox query.
        amount: Signed page count for ``SCROLL``. Positive values scroll up
            and negative values scroll down.
        app: Application to open for ``OPEN_APP``.
        key: Key chord for ``PRESS_KEY``.
        field_action: Guarded active page field edit for
            ``EDIT_FOCUSED_PAGE_FIELD``.
    """

    kind: IntentType
    x: int | None = None
    y: int | None = None
    url: str | None = None
    target_id: str | None = None
    text: str | None = None
    amount: int | None = None
    app: LaunchableApp | None = None
    key: PressableKey | None = None
    field_action: FocusedPageFieldAction | None = None


class ActionMapper:
    """Dispatch intents through the sole synthetic-input boundary."""

    def __init__(self, backend: InputBackend) -> None:
        """Create an action mapper for one OS input backend.

        Args:
            backend: The platform adapter that performs gated input injection.
        """
        self._backend = backend

    def dispatch(self, intent: Intent) -> None:
        """Execute an intent via the configured backend.

        Args:
            intent: The gesture or voice action to perform.

        Raises:
            ValueError: If a cursor movement intent omits a coordinate, an
                ``OPEN_URL`` intent omits ``url``, a ``CLICK_ELEMENT`` intent
                omits ``target_id``, or a ``TYPE_TEXT`` intent omits
                ``target_id`` or ``text``, or a focused-page edit omits its
                action.
        """
        if intent.kind is IntentType.MOVE_CURSOR:
            if intent.x is None or intent.y is None:
                raise ValueError("MOVE_CURSOR intents require both x and y coordinates.")
            self._backend.move_to(intent.x, intent.y)
        elif intent.kind is IntentType.CLICK_LEFT:
            self._backend.click_left()
        elif intent.kind is IntentType.OPEN_URL:
            if intent.url is None:
                raise ValueError("OPEN_URL intents require a url.")
            self._backend.open_url(intent.url)
        elif intent.kind in _BROWSER_ACTIONS:
            self._backend.navigate_browser(_BROWSER_ACTIONS[intent.kind])
        elif intent.kind is IntentType.SEARCH_WEB:
            if not intent.text:
                raise ValueError("SEARCH_WEB intents require non-empty text.")
            self._backend.search_web(intent.text)
        elif intent.kind is IntentType.SCROLL:
            if intent.amount is None or intent.amount == 0:
                raise ValueError("SCROLL intents require a non-zero amount.")
            self._backend.scroll(intent.amount)
        elif intent.kind is IntentType.CLICK_ELEMENT:
            if not intent.target_id:
                raise ValueError("CLICK_ELEMENT intents require a target_id.")
            self._backend.click_element(intent.target_id)
        elif intent.kind is IntentType.FOCUS_ELEMENT:
            if not intent.target_id:
                raise ValueError("FOCUS_ELEMENT intents require a target_id.")
            self._backend.focus_element(intent.target_id)
        elif intent.kind is IntentType.EDIT_FOCUSED_PAGE_FIELD:
            if intent.field_action is None:
                raise ValueError("EDIT_FOCUSED_PAGE_FIELD intents require a field_action.")
            self._backend.edit_focused_page_field(intent.field_action)
        elif intent.kind is IntentType.TYPE_TEXT:
            if not intent.target_id or intent.text is None:
                raise ValueError("TYPE_TEXT intents require a target_id and text.")
            self._backend.type_text(intent.target_id, intent.text)
        elif intent.kind is IntentType.SUBMIT_TEXT:
            if not intent.target_id or intent.text is None:
                raise ValueError("SUBMIT_TEXT intents require a target_id and text.")
            self._backend.submit_text(intent.target_id, intent.text)
        elif intent.kind is IntentType.FOCUS_CHROME_OMNIBOX:
            self._backend.focus_chrome_omnibox()
        elif intent.kind is IntentType.OPEN_APP:
            if intent.app is None:
                raise ValueError("OPEN_APP intents require an app.")
            self._backend.open_app(intent.app)
        elif intent.kind is IntentType.TYPE_FOCUSED:
            if intent.text is None or not intent.text:
                raise ValueError("TYPE_FOCUSED intents require non-empty text.")
            if len(intent.text) > MAX_TYPED_CHARS:
                raise ValueError(f"TYPE_FOCUSED text exceeds {MAX_TYPED_CHARS} characters.")
            if any(ord(ch) < 32 or ord(ch) == 127 for ch in intent.text):
                raise ValueError("TYPE_FOCUSED text must not contain control characters.")
            self._backend.type_focused(intent.text)
        elif intent.kind is IntentType.PRESS_KEY:
            if intent.key is None:
                raise ValueError("PRESS_KEY intents require a key.")
            self._backend.press_key(intent.key)
