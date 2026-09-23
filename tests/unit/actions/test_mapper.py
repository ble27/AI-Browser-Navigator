"""Tests for the M2 modality-neutral Action Mapper."""

from __future__ import annotations

import pytest
from gesture_control.actions import ActionMapper, Intent, IntentType
from gesture_control.backends.base import InputBackend


class _FakeBackend(InputBackend):
    """Record gated synthetic input without interacting with an operating system."""

    def __init__(self) -> None:
        super().__init__()
        self.moves: list[tuple[int, int]] = []
        self.click_count = 0
        self.opened_urls: list[str] = []

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
