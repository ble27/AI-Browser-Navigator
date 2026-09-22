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

    def screen_size(self) -> tuple[int, int]:
        return 100, 100

    def move_to(self, x: int, y: int) -> None:
        if not self.safe_pause.is_paused:
            self.moves.append((x, y))

    def click_left(self) -> None:
        if not self.safe_pause.is_paused:
            self.click_count += 1


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
