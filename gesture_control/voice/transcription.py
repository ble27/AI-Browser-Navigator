"""Typed, lazy-loaded offline speech transcription."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol, cast

import numpy as np
from numpy.typing import NDArray

VOICE_SAMPLE_RATE = 16_000


class Transcriber(Protocol):
    """Convert one mono audio utterance into text."""

    def transcribe(self, audio: NDArray[np.float32], sample_rate: int = VOICE_SAMPLE_RATE) -> str:
        """Return normalized text for one utterance."""


class _Segment(Protocol):
    """Text-bearing faster-whisper segment."""

    text: str


class _WhisperModel(Protocol):
    """Subset of ``faster_whisper.WhisperModel`` used by this application."""

    def transcribe(
        self,
        audio: NDArray[np.float32],
        *,
        language: str,
        beam_size: int,
        vad_filter: bool,
        condition_on_previous_text: bool,
    ) -> tuple[Iterable[_Segment], object]:
        """Transcribe one in-memory audio array."""


ModelFactory = Callable[[str, str, str], _WhisperModel]


class FasterWhisperTranscriber:
    """Transcribe short English commands locally with faster-whisper."""

    def __init__(
        self,
        model_name: str = "tiny.en",
        device: str = "cpu",
        compute_type: str = "int8",
        model_factory: ModelFactory | None = None,
    ) -> None:
        """Initialize one reusable offline Whisper model.

        The default model may download from Hugging Face on first use. Once
        cached, transcription remains local and no audio is uploaded.

        Args:
            model_name: faster-whisper model id or local model directory.
            device: CTranslate2 execution device.
            compute_type: CTranslate2 model quantization type.
            model_factory: Injectable model constructor for hardware-free tests.

        Raises:
            RuntimeError: If faster-whisper is unavailable or model
                initialization fails.
        """
        factory = model_factory or _load_whisper_model
        try:
            self._model = factory(model_name, device, compute_type)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Could not initialize faster-whisper model {model_name!r}. "
                "The first run may need internet access to download the model; "
                "check the model name, network, and available disk space."
            ) from exc

    def transcribe(self, audio: NDArray[np.float32], sample_rate: int = VOICE_SAMPLE_RATE) -> str:
        """Transcribe one 16 kHz mono float32 command.

        Args:
            audio: One-dimensional mono float32 samples.
            sample_rate: Audio sample rate. Must be 16 kHz.

        Returns:
            Segment text joined with collapsed whitespace.

        Raises:
            ValueError: If the sample rate, shape, or dtype is unsupported.
            RuntimeError: If local transcription fails.
        """
        if sample_rate != VOICE_SAMPLE_RATE:
            raise ValueError("faster-whisper commands require 16 kHz audio.")
        if audio.ndim != 1:
            raise ValueError("faster-whisper commands require a mono audio array.")
        if audio.dtype != np.float32:
            raise ValueError("faster-whisper commands require float32 audio.")

        try:
            segments, _info = self._model.transcribe(
                audio,
                language="en",
                beam_size=1,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            materialized = list(segments)
        except Exception as exc:
            raise RuntimeError(
                "Offline speech transcription failed. Check the selected voice "
                "model and available CPU/memory."
            ) from exc
        return " ".join(" ".join(segment.text.split()) for segment in materialized).strip()


def _load_whisper_model(model_name: str, device: str, compute_type: str) -> _WhisperModel:
    """Load faster-whisper only when voice mode is explicitly requested.

    Args:
        model_name: faster-whisper model id or local model directory.
        device: CTranslate2 execution device.
        compute_type: CTranslate2 model quantization type.

    Returns:
        An initialized faster-whisper model.

    Raises:
        RuntimeError: If the optional package is not installed.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "Voice transcription requires optional dependencies. Install them "
            'with: pip install -e ".[voice]"'
        ) from exc
    return cast(
        _WhisperModel,
        WhisperModel(model_name, device=device, compute_type=compute_type),
    )
