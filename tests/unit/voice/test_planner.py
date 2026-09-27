"""Tests for :class:`DeterministicClausePlanner`."""

from __future__ import annotations

from gesture_control.actions import IntentType
from gesture_control.backends.base import FocusedPageFieldAction, LaunchableApp, PressableKey
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


def test_repeated_partial_open_never_waits_on_its_own_destination() -> None:
    planner = DeterministicClausePlanner()
    clause = _clause("open amazon")
    first = planner.plan(clause)
    repeated = planner.plan(clause)
    assert isinstance(first[0], ResolvedStep)
    assert isinstance(repeated[0], ResolvedStep)
    assert first[0].ready is None
    assert repeated[0].ready is None


def test_open_notes_sets_app_surface() -> None:
    planner = DeterministicClausePlanner()
    steps = planner.plan(_clause("open notes"))
    assert planner.surface is Surface.APP
    assert steps[0].intent.app is LaunchableApp.NOTES


def test_session_host_persists_across_lines_for_click() -> None:
    planner = DeterministicClausePlanner()
    planner.plan(_clause("open amazon", line_id=0))
    steps = planner.plan(_clause("click orders", line_id=1))
    assert isinstance(steps[0], PageStep)
    assert steps[0].ready is not None
    assert steps[0].ready.host == "amazon.com"


def test_browser_control_does_not_inherit_session_host_readiness() -> None:
    planner = DeterministicClausePlanner()
    planner.plan(_clause("open amazon", line_id=0))
    steps = planner.plan(_clause("next browser", line_id=1))
    assert isinstance(steps[0], ResolvedStep)
    assert steps[0].intent.kind is IntentType.NEXT_TAB
    assert steps[0].ready is None
    close_steps = planner.plan(_clause("close browser", line_id=2))
    assert isinstance(close_steps[0], ResolvedStep)
    assert close_steps[0].intent.kind is IntentType.CLOSE_TAB
    assert close_steps[0].ready is None


def test_focus_chrome_search_bar_clears_stale_readiness() -> None:
    planner = DeterministicClausePlanner()
    planner.plan(_clause("open amazon", line_id=0))

    steps = planner.plan(_clause("focus Chrome search bar", line_id=1))

    assert isinstance(steps[0], ResolvedStep)
    assert steps[0].intent.kind is IntentType.FOCUS_CHROME_OMNIBOX
    assert steps[0].ready is None
    enter = planner.plan(_clause("done", line_id=2))
    assert isinstance(enter[0], ResolvedStep)
    assert enter[0].ready is None


def test_focus_app_search_bar_is_live_page_step_without_stale_readiness() -> None:
    planner = DeterministicClausePlanner()
    planner.plan(_clause("open amazon", line_id=0))

    steps = planner.plan(_clause("focus app search bar", line_id=1))

    assert isinstance(steps[0], PageStep)
    assert steps[0].phrase == "focus app search bar"
    assert steps[0].ready is None


def test_focused_page_field_commands_are_immediate_and_clear_stale_readiness() -> None:
    planner = DeterministicClausePlanner()
    planner.plan(_clause("open amazon", line_id=0))

    for index, (phrase, action) in enumerate(
        (
            ("unfocus", FocusedPageFieldAction.UNFOCUS),
            ("delete line", FocusedPageFieldAction.DELETE_LINE),
            ("clear search", FocusedPageFieldAction.CLEAR_SEARCH),
            ("delete word", FocusedPageFieldAction.DELETE_WORD),
        ),
        start=1,
    ):
        step = planner.plan(_clause(phrase, line_id=index))[0]
        assert isinstance(step, ResolvedStep)
        assert step.intent.kind is IntentType.EDIT_FOCUSED_PAGE_FIELD
        assert step.intent.field_action is action
        assert step.ready is None


def test_search_query_containing_delete_words_stays_a_search() -> None:
    step = DeterministicClausePlanner().plan(_clause("search for delete word"))[0]

    assert isinstance(step, ResolvedStep)
    assert step.intent.kind is IntentType.SEARCH_WEB
    assert step.intent.text == "delete word"


def test_ask_macro_emits_three_steps() -> None:
    steps = DeterministicClausePlanner().plan(
        _clause("ask claude what is the capital of france"),
    )
    assert len(steps) == 3
    assert steps[0].intent.kind is IntentType.OPEN_URL
    assert steps[1].intent.kind is IntentType.TYPE_FOCUSED
    assert steps[2].intent.key is PressableKey.ENTER


def test_type_on_browser_is_page_step_with_fallback() -> None:
    planner = DeterministicClausePlanner()
    planner.plan(_clause("open amazon", line_id=0))
    steps = planner.plan(_clause("type hello", line_id=1))
    assert len(steps) == 1
    assert isinstance(steps[0], PageStep)
    assert steps[0].fallback is not None
    assert steps[0].fallback.kind is IntentType.TYPE_FOCUSED
    assert steps[0].ready is None


def test_type_into_input_does_not_wait_on_the_open_site() -> None:
    planner = DeterministicClausePlanner()
    planner.plan(_clause("open gemini", line_id=0))
    steps = planner.plan(_clause("type what is your name into input", line_id=1))
    assert len(steps) == 1
    assert isinstance(steps[0], PageStep)
    assert steps[0].ready is None
    assert steps[0].fallback is not None
    assert steps[0].fallback.kind is IntentType.TYPE_FOCUSED
    assert steps[0].fallback.text == "what is your name"
