"""Continuous local voice-command runtime."""

from __future__ import annotations

from collections.abc import Callable

from gesture_control.actions import ActionMapper
from gesture_control.voice.audio import UtteranceRecorder
from gesture_control.voice.commands import parse_command
from gesture_control.voice.transcription import VOICE_SAMPLE_RATE, Transcriber


class VoiceAgent:
    """Record, transcribe, parse, and dispatch deterministic commands."""

    def __init__(
        self,
        recorder: UtteranceRecorder,
        transcriber: Transcriber,
        action_mapper: ActionMapper,
        output: Callable[[str], None] = print,
    ) -> None:
        """Wire the hardware-independent voice command loop.

        Args:
            recorder: Captures one utterance per call.
            transcriber: Converts utterance audio to local text.
            action_mapper: Shared intent-to-backend dispatcher.
            output: Feedback sink, injectable for tests.
        """
        self._recorder = recorder
        self._transcriber = transcriber
        self._action_mapper = action_mapper
        self._output = output

    def run_once(self) -> bool:
        """Process one utterance.

        Returns:
            ``True`` when a recognized intent was dispatched; otherwise
            ``False``. Empty and unknown transcripts never reach the mapper.
        """
        audio = self._recorder.record_utterance()
        transcript = self._transcriber.transcribe(audio, VOICE_SAMPLE_RATE)
        if not transcript.strip():
            return False
        self._output(f"Heard: {transcript}")
        utterance_duration_s = float(audio.size) / VOICE_SAMPLE_RATE
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
