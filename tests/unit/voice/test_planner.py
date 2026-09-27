"""Tests for :class:`DeterministicClausePlanner`."""

from __future__ import annotations

from gesture_control.actions import IntentType
from gesture_control.backends.base import LaunchableApp, PressableKey
from gesture_control.voice.planner import DeterministicClausePlanner
from gesture_control.voice.stream_contracts import (
    CancelStep,
    Clause,
    PageStep,
    ResolvedStep,
    Surface,
)


def _clause(text: str, line_id: int = 0, index: int = 0) -> Clause:
    return Clause(text=text, line_id=line_id, index=index, final=True)


def test_control_becomes_cancel_step() -> None:
    steps = DeterministicClausePlanner().plan(_clause("cancel"))
    assert len(steps) == 1
    assert isinstance(steps[0], CancelStep)


def test_open_url_sets_browser_surface() -> None:
    planner = DeterministicClausePlanner()
    steps = planner.plan(_clause("open reddit"))
    assert planner.surface is Surface.BROWSER
    assert isinstance(steps[0], ResolvedStep)
    assert steps[0].intent.kind is IntentType.OPEN_URL


def test_open_notes_sets_app_surface() -> None:
    planner = DeterministicClausePlanner()
    steps = planner.plan(_clause("open notes"))
    assert planner.surface is Surface.APP
    assert steps[0].intent.app is LaunchableApp.NOTES


def test_ask_macro_emits_three_steps() -> None:
    steps = DeterministicClausePlanner().plan(
        _clause("ask claude what is the capital of france"),
    )
    assert len(steps) == 3
    assert steps[0].intent.kind is IntentType.OPEN_URL
    assert steps[1].intent.kind is IntentType.TYPE_FOCUSED
    assert steps[2].intent.key is PressableKey.ENTER


def test_type_on_browser_is_page_step_with_fallback() -> None:
    steps = DeterministicClausePlanner().plan(_clause("type hello"))
    assert len(steps) == 1
    assert isinstance(steps[0], PageStep)
    assert steps[0].fallback is not None
    assert steps[0].fallback.kind is IntentType.TYPE_FOCUSED
