"""Tests for :class:`StreamingVoiceAgent`."""

from __future__ import annotations

import time

from gesture_control.actions import Intent, IntentType
from gesture_control.voice.stream_contracts import (
    CancelStep,
    Clause,
    PageStep,
    ResolvedStep,
    TranscriptEvent,
    TranscriptEventKind,
)
from gesture_control.voice.streaming_agent import StreamingVoiceAgent


class _FakeTranscriber:
    def start(self, sink: object) -> None:
        del sink

    def stop(self) -> None:
        return None


class _FakeSegmenter:
    def feed(self, event: TranscriptEvent) -> list[object]:
        del event
        return []


class _FakePlanner:
    @property
    def surface(self) -> object:
        return None

    def plan(self, clause: object) -> list[object]:
        del clause
        return []


class _FakeExecutor:
    def __init__(self) -> None:
        self.batches: list[list[object]] = []

    def submit(self, steps: object) -> None:
        self.batches.append(list(steps))  # type: ignore[arg-type]

    def close(self, timeout_s: float = 2.0) -> None:
        del timeout_s


def test_repair_runs_before_segmenter() -> None:
    seen: list[str] = []
    printed: list[str] = []

    class _RecordingSegmenter:
        def feed(self, event: TranscriptEvent) -> list[object]:
            seen.append(event.text)
            return []

    agent = StreamingVoiceAgent(
        _FakeTranscriber(),
        _RecordingSegmenter(),
        _FakePlanner(),
        _FakeExecutor(),
        output=printed.append,
    )
    agent.on_event(
        TranscriptEvent(TranscriptEventKind.FINAL, "Open Cloud.", 0, 0.0),
    )
    assert seen == ["Open claude"]
    assert printed == ["[final] Open claude"]


def test_filler_final_does_not_submit() -> None:
    executor = _FakeExecutor()

    class _Seg:
        def feed(self, event: TranscriptEvent) -> list[Clause]:
            return [Clause(event.text, event.line_id, 0, True)]

    class _Plan:
        @property
        def surface(self) -> object:
            return None

        def plan(self, clause: Clause) -> list[object]:
            return [PageStep(source=clause, phrase=clause.text)]

    agent = StreamingVoiceAgent(
        _FakeTranscriber(),
        _Seg(),
        _Plan(),
        executor,
        output=lambda _line: None,
    )
    agent.on_event(TranscriptEvent(TranscriptEventKind.FINAL, "you", 1, 0.0))
    agent.on_event(TranscriptEvent(TranscriptEventKind.FINAL, "Hullo", 2, 0.1))
    assert executor.batches == []


def test_open_url_submits_immediately_on_final() -> None:
    executor = _FakeExecutor()

    class _Seg:
        def feed(self, event: TranscriptEvent) -> list[Clause]:
            return [Clause(event.text, event.line_id, 0, True)]

    class _Plan:
        @property
        def surface(self) -> object:
            return None

        def plan(self, clause: Clause) -> list[ResolvedStep]:
            return [
                ResolvedStep(
                    source=clause,
                    intent=Intent(IntentType.OPEN_URL, url="https://www.reddit.com"),
                ),
            ]

    agent = StreamingVoiceAgent(
        _FakeTranscriber(),
        _Seg(),
        _Plan(),
        executor,
        output=lambda _line: None,
    )
    agent.on_event(TranscriptEvent(TranscriptEventKind.FINAL, "open reddit", 1, 0.0))
    assert len(executor.batches) == 1
    assert executor.batches[0][0].intent.kind is IntentType.OPEN_URL  # type: ignore[union-attr]


def test_type_holds_until_final() -> None:
    executor = _FakeExecutor()

    class _Seg:
        def feed(self, event: TranscriptEvent) -> list[Clause]:
            final = event.kind is TranscriptEventKind.FINAL
            return [Clause(event.text, event.line_id, 0, final)]

    class _Plan:
        @property
        def surface(self) -> object:
            return None

        def plan(self, clause: Clause) -> list[ResolvedStep]:
            return [
                ResolvedStep(
                    source=clause,
                    intent=Intent(IntentType.TYPE_FOCUSED, text="buy milk"),
                ),
            ]

    agent = StreamingVoiceAgent(
        _FakeTranscriber(),
        _Seg(),
        _Plan(),
        executor,
        output=lambda _line: None,
        debounce_s=0.05,
        free_text_silence_s=5.0,
    )
    agent.on_event(
        TranscriptEvent(TranscriptEventKind.PARTIAL, "type buy milk", 1, 0.0),
    )
    time.sleep(0.12)
    assert executor.batches == []
    agent.on_event(
        TranscriptEvent(TranscriptEventKind.FINAL, "type buy milk", 1, 0.2),
    )
    assert len(executor.batches) == 1
    assert executor.batches[0][0].intent.kind is IntentType.TYPE_FOCUSED  # type: ignore[union-attr]


def test_ask_opens_immediately_holds_type_until_final() -> None:
    executor = _FakeExecutor()

    class _Seg:
        def feed(self, event: TranscriptEvent) -> list[Clause]:
            final = event.kind is TranscriptEventKind.FINAL
            return [Clause(event.text, event.line_id, 0, final)]

    class _Plan:
        @property
        def surface(self) -> object:
            return None

        def plan(self, clause: Clause) -> list[ResolvedStep]:
            return [
                ResolvedStep(
                    source=clause,
                    intent=Intent(IntentType.OPEN_URL, url="https://claude.ai/new"),
                ),
                ResolvedStep(
                    source=clause,
                    intent=Intent(IntentType.TYPE_FOCUSED, text="capital of france"),
                ),
            ]

    agent = StreamingVoiceAgent(
        _FakeTranscriber(),
        _Seg(),
        _Plan(),
        executor,
        output=lambda _line: None,
        debounce_s=0.05,
        free_text_silence_s=5.0,
    )
    agent.on_event(
        TranscriptEvent(
            TranscriptEventKind.PARTIAL,
            "ask claude capital of france",
            1,
            0.0,
        ),
    )
    time.sleep(0.12)
    assert len(executor.batches) == 1
    assert executor.batches[0][0].intent.kind is IntentType.OPEN_URL  # type: ignore[union-attr]
    agent.on_event(
        TranscriptEvent(
            TranscriptEventKind.FINAL,
            "ask claude capital of france",
            1,
            0.3,
        ),
    )
    assert len(executor.batches) == 2
    assert executor.batches[1][0].intent.kind is IntentType.TYPE_FOCUSED  # type: ignore[union-attr]


def test_cancel_submits_immediately() -> None:
    executor = _FakeExecutor()

    class _Seg:
        def feed(self, event: TranscriptEvent) -> list[Clause]:
            return [Clause(event.text, event.line_id, 0, True)]

    class _Plan:
        @property
        def surface(self) -> object:
            return None

        def plan(self, clause: Clause) -> list[CancelStep]:
            return [CancelStep(source=clause)]

    agent = StreamingVoiceAgent(
        _FakeTranscriber(),
        _Seg(),
        _Plan(),
        executor,
        output=lambda _line: None,
    )
    agent.on_event(TranscriptEvent(TranscriptEventKind.FINAL, "cancel", 1, 0.0))
    assert len(executor.batches) == 1
    assert isinstance(executor.batches[0][0], CancelStep)


def test_next_tab_fires_on_partial_before_final() -> None:
    """Tab commands must not wait for Moonshine FINAL / VAD silence."""
    executor = _FakeExecutor()

    class _Seg:
        def feed(self, event: TranscriptEvent) -> list[Clause]:
            # Real segmenter also withholds single-clause partials until FINAL.
            if event.kind is TranscriptEventKind.FINAL:
                return [Clause(event.text, event.line_id, 0, True)]
            return []

    class _Plan:
        @property
        def surface(self) -> object:
            return None

        def plan(self, clause: Clause) -> list[ResolvedStep]:
            return [
                ResolvedStep(
                    source=clause,
                    intent=Intent(IntentType.NEXT_TAB),
                ),
            ]

    agent = StreamingVoiceAgent(
        _FakeTranscriber(),
        _Seg(),
        _Plan(),
        executor,
        output=lambda _line: None,
        debounce_s=0.05,
        fast_debounce_s=0.05,
    )
    agent.on_event(TranscriptEvent(TranscriptEventKind.PARTIAL, "next tab", 1, 0.0))
    time.sleep(0.12)
    assert len(executor.batches) == 1
    assert executor.batches[0][0].intent.kind is IntentType.NEXT_TAB  # type: ignore[union-attr]
    agent.on_event(TranscriptEvent(TranscriptEventKind.FINAL, "next tab", 1, 0.5))
    assert len(executor.batches) == 1  # no double dispatch


def test_close_tap_alias_via_real_planner() -> None:
    from gesture_control.voice.planner import DeterministicClausePlanner
    from gesture_control.voice.segmenter import DeterministicClauseSegmenter

    executor = _FakeExecutor()
    agent = StreamingVoiceAgent(
        _FakeTranscriber(),
        DeterministicClauseSegmenter(),
        DeterministicClausePlanner(),
        executor,
        output=lambda _line: None,
        debounce_s=0.05,
        fast_debounce_s=0.05,
    )
    agent.on_event(TranscriptEvent(TranscriptEventKind.PARTIAL, "close tap", 3, 0.0))
    time.sleep(0.12)
    assert len(executor.batches) == 1
    assert executor.batches[0][0].intent.kind is IntentType.CLOSE_TAB  # type: ignore[union-attr]


def test_destructive_click_waits_for_confirm() -> None:
    executor = _FakeExecutor()
    printed: list[str] = []

    class _Seg:
        def feed(self, event: TranscriptEvent) -> list[Clause]:
            return [Clause(event.text, event.line_id, 0, True)]

    class _Plan:
        @property
        def surface(self) -> object:
            return None

        def plan(self, clause: Clause) -> list[PageStep]:
            return [PageStep(source=clause, phrase=clause.text)]

    agent = StreamingVoiceAgent(
        _FakeTranscriber(),
        _Seg(),
        _Plan(),
        executor,
        output=printed.append,
    )
    agent.on_event(TranscriptEvent(TranscriptEventKind.FINAL, "click buy now", 1, 0.0))
    assert executor.batches == []
    assert any("confirm needed" in line for line in printed)
    agent.on_event(TranscriptEvent(TranscriptEventKind.FINAL, "confirm", 2, 1.0))
    assert len(executor.batches) == 1
    assert isinstance(executor.batches[0][0], PageStep)
