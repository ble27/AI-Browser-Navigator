"""Tests for streaming wait/act policy."""

from __future__ import annotations

from gesture_control.actions import Intent, IntentType
from gesture_control.backends.base import LaunchableApp, PressableKey
from gesture_control.voice.policy import (
    FREE_TEXT_SILENCE_S,
    PolicyDecision,
    classify_clause,
    is_filler_text,
    partition_steps,
)
from gesture_control.voice.stream_contracts import (
    CancelStep,
    Clause,
    PageStep,
    ResolvedStep,
)


def _clause(text: str, *, final: bool = False) -> Clause:
    return Clause(text=text, line_id=1, index=0, final=final)


def test_filler_text_detected() -> None:
    assert is_filler_text("you")
    assert is_filler_text("Okay.")
    assert is_filler_text("  hullo  ")
    assert not is_filler_text("open reddit")


def test_classify_filler_and_empty_ignored() -> None:
    clause = _clause("you", final=True)
    assert classify_clause(clause, []) is PolicyDecision.IGNORE
    assert (
        classify_clause(clause, [ResolvedStep(clause, Intent(IntentType.OPEN_URL))])
        is PolicyDecision.IGNORE
    )


def test_cancel_always_acts() -> None:
    clause = _clause("cancel", final=False)
    steps = [CancelStep(source=clause)]
    assert classify_clause(clause, steps) is PolicyDecision.ACT


def test_open_url_acts_on_partial_clause() -> None:
    clause = _clause("open reddit", final=False)
    steps = [
        ResolvedStep(
            source=clause,
            intent=Intent(IntentType.OPEN_URL, url="https://www.reddit.com"),
        ),
    ]
    assert classify_clause(clause, steps) is PolicyDecision.ACT


def test_type_waits_until_final_or_silence() -> None:
    clause = _clause("type buy milk", final=False)
    steps = [
        ResolvedStep(
            source=clause,
            intent=Intent(IntentType.TYPE_FOCUSED, text="buy milk"),
        ),
    ]
    assert classify_clause(clause, steps) is PolicyDecision.WAIT
    assert classify_clause(clause, steps, silence_s=FREE_TEXT_SILENCE_S) is PolicyDecision.ACT
    assert classify_clause(_clause("type buy milk", final=True), steps) is PolicyDecision.ACT


def test_partition_ask_macro_open_now_type_and_enter_later() -> None:
    clause = _clause("ask claude what is 2 plus 2", final=False)
    steps = [
        ResolvedStep(
            source=clause,
            intent=Intent(IntentType.OPEN_URL, url="https://claude.ai/new"),
        ),
        ResolvedStep(
            source=clause,
            intent=Intent(IntentType.TYPE_FOCUSED, text="what is 2 plus 2"),
        ),
        ResolvedStep(
            source=clause,
            intent=Intent(IntentType.PRESS_KEY, key=PressableKey.ENTER),
        ),
    ]
    immediate, deferred = partition_steps(steps)
    assert len(immediate) == 1
    assert isinstance(immediate[0], ResolvedStep)
    assert immediate[0].intent.kind is IntentType.OPEN_URL
    assert [s.intent.kind for s in deferred if isinstance(s, ResolvedStep)] == [
        IntentType.TYPE_FOCUSED,
        IntentType.PRESS_KEY,
    ]


def test_page_click_deferred() -> None:
    clause = _clause("click orders", final=False)
    steps = [PageStep(source=clause, phrase="click orders")]
    immediate, deferred = partition_steps(steps)
    assert immediate == []
    assert deferred == steps


def test_open_app_immediate() -> None:
    clause = _clause("open notes", final=False)
    steps = [
        ResolvedStep(
            source=clause,
            intent=Intent(IntentType.OPEN_APP, app=LaunchableApp.NOTES),
        ),
    ]
    immediate, deferred = partition_steps(steps)
    assert immediate == steps
    assert deferred == []
