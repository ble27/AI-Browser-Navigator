"""Tests for :class:`StreamingVoiceAgent`."""

from __future__ import annotations

from gesture_control.voice.stream_contracts import TranscriptEvent, TranscriptEventKind


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
    def submit(self, steps: object) -> None:
        del steps

    def close(self, timeout_s: float = 2.0) -> None:
        del timeout_s


def test_repair_runs_before_segmenter() -> None:
    from gesture_control.voice.streaming_agent import StreamingVoiceAgent

    seen: list[str] = []

    class _RecordingSegmenter:
        def feed(self, event: TranscriptEvent) -> list[object]:
            seen.append(event.text)
            return []

    agent = StreamingVoiceAgent(
        _FakeTranscriber(),
        _RecordingSegmenter(),
        _FakePlanner(),
        _FakeExecutor(),
    )
    agent.on_event(
        TranscriptEvent(TranscriptEventKind.FINAL, "Open Cloud.", 0, 0.0),
    )
    assert seen == ["Open claude"]
