"""Coordinator for offline streaming voice control."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from threading import Lock

from gesture_control.voice.asr_repair import repair_command_text
from gesture_control.voice.stream_contracts import (
    ClausePlanner,
    ClauseSegmenter,
    StepExecutor,
    StreamingTranscriber,
    TranscriptEvent,
)


class StreamingVoiceAgent:
    """Apply repair, segment, plan, and enqueue steps for each STT event."""

    def __init__(
        self,
        transcriber: StreamingTranscriber,
        segmenter: ClauseSegmenter,
        planner: ClausePlanner,
        executor: StepExecutor,
        output: Callable[[str], None] = print,
    ) -> None:
        """Wire streaming voice ports together."""
        self._transcriber = transcriber
        self._segmenter = segmenter
        self._planner = planner
        self._executor = executor
        self._output = output
        self._lock = Lock()

    def on_event(self, event: TranscriptEvent) -> None:
        """Handle one transcript event from the STT thread."""
        repaired = repair_command_text(event.text)
        repaired_event = TranscriptEvent(event.kind, repaired, event.line_id, event.at_s)
        with self._lock:
            for clause in self._segmenter.feed(repaired_event):
                steps = self._planner.plan(clause)
                if steps:
                    self._executor.submit(steps)

    def start(self) -> None:
        """Start microphone streaming."""
        self._transcriber.start(self.on_event)

    def stop(self) -> None:
        """Stop microphone streaming."""
        self._transcriber.stop()


StreamingVoiceAgent.__signature__ = inspect.Signature(
    [
        inspect.Parameter("self", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter("transcriber", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter("segmenter", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter("planner", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter("executor", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter(
            "output",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=print,
        ),
    ],
)
