"""Local microphone recording with testable speech-boundary detection."""

from __future__ import annotations

import math
import queue
from collections import deque
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from gesture_control.voice.transcription import VOICE_SAMPLE_RATE


class UtteranceRecorder(Protocol):
    """Capture one spoken utterance as mono float32 audio."""

    def record_utterance(self) -> NDArray[np.float32]:
        """Wait for and return one complete utterance."""


@dataclass(frozen=True, slots=True)
class RecordingConfig:
    """Speech-boundary and microphone capture settings.

    The defaults use 30 ms blocks, a short 200 ms pre-roll so initial
    consonants are retained, 350 ms trailing silence for command completion,
    and an eight-second safety cap appropriate for short deterministic
    commands.

    Attributes:
        sample_rate: Input samples per second. Voice mode requires 16 kHz.
        block_duration_s: Duration of each analyzed microphone block.
        speech_threshold: Root-mean-square amplitude considered speech.
        min_speech_s: Continuous above-threshold audio required to start.
        pre_roll_s: Audio retained before confirmed speech.
        trailing_silence_s: Below-threshold duration that ends an utterance.
        max_utterance_s: Maximum returned audio duration including pre-roll.
    """

    sample_rate: int = VOICE_SAMPLE_RATE
    block_duration_s: float = 0.03
    speech_threshold: float = 0.015
    min_speech_s: float = 0.10
    pre_roll_s: float = 0.20
    trailing_silence_s: float = 0.35
    max_utterance_s: float = 8.0

    def __post_init__(self) -> None:
        """Validate settings before microphone capture begins."""
        numeric_values = (
            self.block_duration_s,
            self.speech_threshold,
            self.min_speech_s,
            self.pre_roll_s,
            self.trailing_silence_s,
            self.max_utterance_s,
        )
        if self.sample_rate != VOICE_SAMPLE_RATE:
            raise ValueError("Voice recording requires a 16 kHz sample rate.")
        if any(value <= 0 for value in numeric_values):
            raise ValueError("Voice recording durations and threshold must be positive.")
        if self.pre_roll_s >= self.max_utterance_s:
            raise ValueError("pre_roll_s must be shorter than max_utterance_s.")

    @property
    def block_size(self) -> int:
        """Return samples captured in each analysis block."""
        return round(self.sample_rate * self.block_duration_s)


class UtteranceSegmenter:
    """Collect blocks from pre-roll through trailing silence."""

    def __init__(self, config: RecordingConfig | None = None) -> None:
        """Create a fresh speech-boundary state machine.

        Args:
            config: Recording and speech-boundary settings.
        """
        self.config = config or RecordingConfig()
        self._pre_roll_blocks = math.ceil(self.config.pre_roll_s / self.config.block_duration_s)
        self._min_speech_blocks = math.ceil(self.config.min_speech_s / self.config.block_duration_s)
        self._trailing_silence_blocks = math.ceil(
            self.config.trailing_silence_s / self.config.block_duration_s
        )
        self._max_blocks = math.ceil(self.config.max_utterance_s / self.config.block_duration_s)
        self._pre_roll: deque[NDArray[np.float32]] = deque(maxlen=self._pre_roll_blocks)
        self._utterance: list[NDArray[np.float32]] | None = None
        self._speech_run = 0
        self._silence_run = 0

    def add_block(self, block: NDArray[np.float32]) -> NDArray[np.float32] | None:
        """Consume one mono block and return audio when the utterance ends.

        Args:
            block: One mono float32 block of exactly ``config.block_size``
                samples.

        Returns:
            A complete utterance once trailing silence or the duration cap is
            reached; otherwise ``None``.

        Raises:
            ValueError: If the block shape or dtype does not match the config.
        """
        if block.ndim != 1 or block.size != self.config.block_size:
            raise ValueError(f"Audio blocks must contain {self.config.block_size} mono samples.")
        if block.dtype != np.float32:
            raise ValueError("Audio blocks must use float32 samples.")

        copied = block.copy()
        is_speech = _root_mean_square(copied) >= self.config.speech_threshold
        if self._utterance is None:
            self._pre_roll.append(copied)
            self._speech_run = self._speech_run + 1 if is_speech else 0
            if self._speech_run < self._min_speech_blocks:
                return None
            self._utterance = list(self._pre_roll)
            self._silence_run = 0
        else:
            self._utterance.append(copied)
            self._silence_run = 0 if is_speech else self._silence_run + 1

        if len(self._utterance) >= self._max_blocks:
            return self._finish()
        if self._silence_run >= self._trailing_silence_blocks:
            return self._finish()
        return None

    def _finish(self) -> NDArray[np.float32]:
        """Join the completed utterance and clear captured blocks."""
        if self._utterance is None:
            raise RuntimeError("Cannot finish before speech starts.")
        audio = np.concatenate(self._utterance).astype(np.float32, copy=False)
        self._utterance = None
        return audio


class MicrophoneUtteranceRecorder:
    """Record speech from the default sounddevice input."""

    def __init__(self, config: RecordingConfig | None = None) -> None:
        """Configure default-microphone utterance capture.

        Args:
            config: Recording and speech-boundary settings.
        """
        self.config = config or RecordingConfig()

    def record_utterance(self) -> NDArray[np.float32]:
        """Wait for one utterance and return mono float32 samples.

        Returns:
            Captured 16 kHz mono audio including a short pre-roll.

        Raises:
            RuntimeError: If sounddevice is missing or the microphone stream
                cannot be opened/read.
        """
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "Microphone voice mode requires optional audio dependencies. "
                'Install them with: pip install -e ".[voice]"'
            ) from exc

        blocks: queue.Queue[NDArray[np.float32]] = queue.Queue()
        segmenter = UtteranceSegmenter(self.config)

        def capture_block(
            indata: NDArray[np.float32],
            frames: int,
            time_info: object,
            status: object,
        ) -> None:
            """Copy one callback block before sounddevice reuses its buffer."""
            del frames, time_info, status
            blocks.put(np.asarray(indata[:, 0], dtype=np.float32).copy())

        try:
            with sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=self.config.block_size,
                callback=capture_block,
            ):
                while True:
                    utterance = segmenter.add_block(blocks.get())
                    if utterance is not None:
                        return utterance
        except Exception as exc:
            raise RuntimeError(
                "Could not record from the default microphone. Check macOS "
                "Microphone permission, the selected input device, and that no "
                "other application has exclusive access."
            ) from exc


def _root_mean_square(block: NDArray[np.float32]) -> float:
    """Return block energy without overflowing float32 multiplication."""
    samples = block.astype(np.float64, copy=False)
    return float(np.sqrt(np.mean(samples * samples)))
