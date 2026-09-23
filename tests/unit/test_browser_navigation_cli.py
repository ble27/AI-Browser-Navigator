"""Hardware-free CLI contract tests for one-shot browser commands."""

from __future__ import annotations

import pytest
from gesture_control import app
from gesture_control.backends.base import BrowserAction, InputBackend


class _RecordingBackend(InputBackend):
    """Record browser operations without opening Chrome or injecting input."""

    instances: list[_RecordingBackend] = []

    def __init__(self) -> None:
        super().__init__()
        self.opened_urls: list[str] = []
        self.browser_actions: list[BrowserAction] = []
        self.__class__.instances.append(self)

    def screen_size(self) -> tuple[int, int]:
        return 100, 100

    def move_to(self, x: int, y: int) -> None:
        del x, y

    def click_left(self) -> None:
        return None

    def open_url(self, url: str) -> None:
        self.opened_urls.append(url)

    def search_web(self, text: str) -> None:
        del text

    def scroll(self, amount: int) -> None:
        del amount

    def click_element(self, target_id: str) -> None:
        del target_id

    def type_text(self, target_id: str, text: str) -> None:
        del target_id, text

    def navigate_browser(self, action: BrowserAction) -> None:
        """Record one browser-navigation action."""
        self.browser_actions.append(action)


@pytest.fixture(autouse=True)
def _isolate_command_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace all hardware boundaries for every CLI test in this module."""
    _RecordingBackend.instances.clear()

    def fail_if_camera_starts(*args: object, **kwargs: object) -> int:
        raise AssertionError("run_debug_overlay must not start for --command")

    monkeypatch.setattr(app, "MacOSInputBackend", _RecordingBackend)
    monkeypatch.setattr(app, "run_debug_overlay", fail_if_camera_starts)
    monkeypatch.setattr(app.sys, "platform", "darwin")


@pytest.mark.parametrize(
    ("phrase", "action"),
    [
        ("next tab", BrowserAction.NEXT_TAB),
        ("switch tab", BrowserAction.NEXT_TAB),
        ("previous tab", BrowserAction.PREVIOUS_TAB),
        ("new tab", BrowserAction.NEW_TAB),
        ("close tab", BrowserAction.CLOSE_TAB),
        ("go back", BrowserAction.GO_BACK),
        ("back", BrowserAction.GO_BACK),
        ("go forward", BrowserAction.GO_FORWARD),
        ("forward", BrowserAction.GO_FORWARD),
        ("reload", BrowserAction.RELOAD_PAGE),
        ("refresh", BrowserAction.RELOAD_PAGE),
    ],
)
def test_command_dispatches_browser_navigation_without_camera(
    phrase: str,
    action: BrowserAction,
) -> None:
    """A recognized navigation phrase should dispatch once and exit successfully."""
    assert app.main(["--command", phrase]) == 0
    assert len(_RecordingBackend.instances) == 1
    backend = _RecordingBackend.instances[0]
    assert backend.browser_actions == [action]
    assert backend.opened_urls == []


@pytest.mark.parametrize(
    ("phrase", "url"),
    [
        ("open cursor webpage", "https://cursor.com"),
        ("open apple website", "https://www.apple.com"),
    ],
)
def test_command_retains_existing_open_site_behavior(
    phrase: str,
    url: str,
) -> None:
    """Existing allowlisted open-site phrases should still skip the camera."""
    assert app.main(["--command", phrase]) == 0
    assert len(_RecordingBackend.instances) == 1
    backend = _RecordingBackend.instances[0]
    assert backend.opened_urls == [url]
    assert backend.browser_actions == []


def test_unknown_command_returns_one_without_starting_camera() -> None:
    """An unknown phrase should fail before constructing an input backend."""
    assert app.main(["--command", "next tab please"]) == 1
    assert _RecordingBackend.instances == []
