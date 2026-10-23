"""Type commands commit on a short pause and do not type the phrase twice."""

from __future__ import annotations

import time

from gesture_control.actions import IntentType
from gesture_control.backends.base import PressableKey
from gesture_control.voice.planner import DeterministicClausePlanner
from gesture_control.voice.preferences import VoicePreferences
from gesture_control.voice.segmenter import DeterministicClauseSegmenter
from gesture_control.voice.stream_contracts import (
    ResolvedStep,
    TranscriptEvent,
    TranscriptEventKind,
)
from gesture_control.voice.streaming_agent import StreamingVoiceAgent

from .test_streaming_agent import _FakeExecutor, _FakeTranscriber


def _typed(executor: _FakeExecutor) -> list[str]:
    texts: list[str] = []
    for batch in executor.batches:
        for step in batch:
            if isinstance(step, ResolvedStep) and step.intent.kind is IntentType.TYPE_FOCUSED:
                texts.append(step.intent.text or "")
    return texts


def _agent(executor: _FakeExecutor) -> StreamingVoiceAgent:
    return StreamingVoiceAgent(
        _FakeTranscriber(),
        DeterministicClauseSegmenter(),
        DeterministicClausePlanner(),
        executor,
        output=lambda _line: None,
        debounce_s=0.02,
        fast_debounce_s=0.01,
        free_text_silence_s=5.0,
        type_silence_s=0.05,
    )


def _partial(text: str, line_id: int = 0) -> TranscriptEvent:
    return TranscriptEvent(TranscriptEventKind.PARTIAL, text, line_id, time.monotonic())


def test_type_command_is_typed_before_the_recognizer_final() -> None:
    executor = _FakeExecutor()
    agent = _agent(executor)
    started = time.monotonic()
    agent.on_event(_partial("type hello"))
    deadline = time.monotonic() + 1.0
    while _typed(executor) != ["hello"] and time.monotonic() < deadline:
        time.sleep(0.02)
    assert _typed(executor) == ["hello"]
    assert time.monotonic() - started < 0.5
    agent.on_event(TranscriptEvent(TranscriptEventKind.FINAL, "type hello", 0, time.monotonic()))
    time.sleep(0.05)
    assert _typed(executor) == ["hello"]


def test_growing_type_command_appends_only_the_new_suffix() -> None:
    executor = _FakeExecutor()
    agent = _agent(executor)
    agent.on_event(_partial("type hel"))
    deadline = time.monotonic() + 1.0
    while _typed(executor) != ["hel"] and time.monotonic() < deadline:
        time.sleep(0.02)
    assert _typed(executor) == ["hel"]
    agent.on_event(_partial("type hello"))
    deadline = time.monotonic() + 1.0
    while _typed(executor) != ["hel", "lo"] and time.monotonic() < deadline:
        time.sleep(0.02)
    assert _typed(executor) == ["hel", "lo"]


def test_revised_type_command_backspaces_the_previous_text() -> None:
    executor = _FakeExecutor()
    agent = _agent(executor)
    agent.on_event(_partial("type cat"))
    deadline = time.monotonic() + 1.0
    while _typed(executor) != ["cat"] and time.monotonic() < deadline:
        time.sleep(0.02)
    agent.on_event(_partial("type car"))
    deadline = time.monotonic() + 1.0
    while len(executor.batches) < 2 and time.monotonic() < deadline:
        time.sleep(0.02)
    revised = [step for step in executor.batches[-1] if isinstance(step, ResolvedStep)]
    backspaces = [
        step
        for step in revised
        if step.intent.kind is IntentType.PRESS_KEY and step.intent.key is PressableKey.BACKSPACE
    ]
    assert len(backspaces) == 3
    assert _typed(executor)[-1] == "car"


def test_steady_typing_setting_waits_longer_than_the_fast_default() -> None:
    executor = _FakeExecutor()
    agent = StreamingVoiceAgent(
        _FakeTranscriber(),
        DeterministicClauseSegmenter(),
        DeterministicClausePlanner(),
        executor,
        output=lambda _line: None,
        debounce_s=0.02,
        fast_debounce_s=0.01,
        free_text_silence_s=5.0,
        type_silence_s=0.05,
        preferences=lambda: VoicePreferences(typing="steady"),
    )
    agent.on_event(_partial("type hello"))
    time.sleep(0.25)
    assert _typed(executor) == []
    deadline = time.monotonic() + 1.5
    while _typed(executor) != ["hello"] and time.monotonic() < deadline:
        time.sleep(0.02)
    assert _typed(executor) == ["hello"]
