"""Continuous local voice-command runtime."""

from __future__ import annotations

import threading
from collections.abc import Callable

from gesture_control.actions import ActionMapper, Intent
from gesture_control.voice.audio import UtteranceRecorder
from gesture_control.voice.commands import parse_command
from gesture_control.voice.live_page import PageCommandUnavailableError
from gesture_control.voice.transcription import VOICE_SAMPLE_RATE, Transcriber


class VoiceAgent:
    """Record, transcribe, parse, and dispatch deterministic commands."""

    def __init__(
        self,
        recorder: UtteranceRecorder,
        transcriber: Transcriber,
        action_mapper: ActionMapper,
        output: Callable[[str], None] = print,
        page_resolver: Callable[[str], Intent | None] | None = None,
        page_prefetch: Callable[[], None] | None = None,
    ) -> None:
        """Wire the hardware-independent voice command loop.

        Args:
            recorder: Captures one utterance per call.
            transcriber: Converts utterance audio to local text.
            action_mapper: Shared intent-to-backend dispatcher.
            output: Feedback sink, injectable for tests.
            page_resolver: Optional active-page intent resolver.
            page_prefetch: Optional hook started in parallel with
                transcription so a page snapshot can overlap STT.
        """
        self._recorder = recorder
        self._transcriber = transcriber
        self._action_mapper = action_mapper
        self._output = output
        self._page_resolver = page_resolver
        self._page_prefetch = page_prefetch

    def run_once(self) -> bool:
        """Process one utterance.

        Returns:
            ``True`` when a recognized intent was dispatched; otherwise
            ``False``. Empty and unknown transcripts never reach the mapper.
        """
        audio = self._recorder.record_utterance()
        prefetch_thread: threading.Thread | None = None
        if self._page_prefetch is not None:
            prefetch_thread = threading.Thread(
                target=self._page_prefetch,
                name="page-snapshot-prefetch",
                daemon=True,
            )
            prefetch_thread.start()
        transcript = self._transcriber.transcribe(audio, VOICE_SAMPLE_RATE)
        if prefetch_thread is not None:
            prefetch_thread.join(timeout=2.0)
        if not transcript.strip():
            return False
        self._output(f"Heard: {transcript}")
        utterance_duration_s = float(audio.size) / VOICE_SAMPLE_RATE
        try:
            intent = self._page_resolver(transcript) if self._page_resolver is not None else None
        except PageCommandUnavailableError as exc:
            self._output(f"Page command unavailable: {exc}")
            return False
        if intent is None:
            intent = parse_command(transcript, utterance_duration_s)
        if intent is None:
            self._output("Unrecognized command.")
            return False
        self._action_mapper.dispatch(intent)
        self._output(f"Recognized: {intent.kind.value}")
        return True

    def run_forever(self) -> None:
        """Process utterances until the caller interrupts the loop."""
        while True:
            self.run_once()
