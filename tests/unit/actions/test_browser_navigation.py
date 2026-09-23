"""Contract tests for browser navigation through the Action Mapper."""

from __future__ import annotations

import pytest
from gesture_control.actions import ActionMapper, Intent, IntentType
from gesture_control.backends.base import BrowserAction, InputBackend


class _RecordingBackend(InputBackend):
    """Record every backend operation without injecting operating-system input."""

    def __init__(self) -> None:
        super().__init__()
        self.browser_actions: list[BrowserAction] = []

    def screen_size(self) -> tuple[int, int]:
        return 100, 100

    def move_to(self, x: int, y: int) -> None:
        del x, y

    def click_left(self) -> None:
        return None

    def open_url(self, url: str) -> None:
        del url

    def click_element(self, target_id: str) -> None:
        del target_id

    def type_text(self, target_id: str, text: str) -> None:
        del target_id, text

    def navigate_browser(self, action: BrowserAction) -> None:
        """Record one typed browser action."""
        self.browser_actions.append(action)


@pytest.mark.parametrize(
    ("kind", "action"),
    [
        (IntentType.PREVIOUS_TAB, BrowserAction.PREVIOUS_TAB),
        (IntentType.NEXT_TAB, BrowserAction.NEXT_TAB),
        (IntentType.NEW_TAB, BrowserAction.NEW_TAB),
        (IntentType.CLOSE_TAB, BrowserAction.CLOSE_TAB),
        (IntentType.GO_BACK, BrowserAction.GO_BACK),
        (IntentType.GO_FORWARD, BrowserAction.GO_FORWARD),
        (IntentType.RELOAD_PAGE, BrowserAction.RELOAD_PAGE),
    ],
)
def test_action_mapper_dispatches_typed_browser_actions(
    kind: IntentType,
    action: BrowserAction,
) -> None:
    """Each browser intent should map to exactly one typed backend action."""
    backend = _RecordingBackend()

    ActionMapper(backend).dispatch(Intent(kind))

    assert backend.browser_actions == [action]
