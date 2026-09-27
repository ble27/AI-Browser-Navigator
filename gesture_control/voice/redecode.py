"""Optional FINAL-line redecode with a stronger offline STT model (S3c)."""

from __future__ import annotations

from typing import Protocol


class FinalRedecoder(Protocol):
    """Re-transcribe one completed utterance's PCM after Moonshine FINAL."""

    def redecode(self, pcm_f32: list[float], sample_rate: int) -> str | None:
        """Return a replacement transcript, or ``None`` to keep Moonshine text."""


class NullFinalRedecoder:
    """No-op redecoder (default)."""

    def redecode(self, pcm_f32: list[float], sample_rate: int) -> str | None:
        """Always keep the streaming transcript."""
        del pcm_f32, sample_rate
        return None


class FasterWhisperFinalRedecoder:
    """Batch redecode via faster-whisper (already in the voice extra).

    Intended for FINAL only: Moonshine partials stay fast; the stronger model
    corrects the completed line when ``--voice-redecode`` is enabled.
    """

    def __init__(self, model_name: str = "base.en") -> None:
        """Create a lazy-loaded faster-whisper redecoder.

        Args:
            model_name: faster-whisper model id (default ``base.en``).
        """
        self._model_name = model_name
        self._model: object | None = None

    def redecode(self, pcm_f32: list[float], sample_rate: int) -> str | None:
        """Transcribe ``pcm_f32`` and return plain text, or ``None`` on failure."""
        if not pcm_f32:
            return None
        try:
            import numpy as np
        except ImportError:
            return None
        model = self._ensure_model()
        if model is None:
            return None
        audio = np.asarray(pcm_f32, dtype=np.float32)
        if sample_rate != 16_000:
            # faster-whisper expects 16 kHz; moonshine capture already is.
            return None
        try:
            segments, _info = model.transcribe(  # type: ignore[attr-defined]
                audio,
                language="en",
                beam_size=1,
                vad_filter=False,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
            return text or None
        except Exception:
            return None

    def _ensure_model(self) -> object | None:
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            return None
        self._model = WhisperModel(self._model_name, device="cpu", compute_type="int8")
        return self._model


class MlxWhisperFinalRedecoder:
    """Batch FINAL redecode via MLX Whisper ``large-v3-turbo`` on Apple Silicon.

    Moonshine partials stay available for early closed commands; this stronger
    decoder replaces the completed line when ``--voice-redecode`` selects MLX.
    """

    def __init__(
        self,
        model_repo: str = "mlx-community/whisper-large-v3-turbo",
    ) -> None:
        """Create a lazy MLX Whisper redecoder.

        Args:
            model_repo: Hugging Face MLX Whisper repo id.
        """
        self._model_repo = model_repo

    def redecode(self, pcm_f32: list[float], sample_rate: int) -> str | None:
        """Transcribe ``pcm_f32`` with MLX Whisper, or ``None`` on failure."""
        if not pcm_f32 or sample_rate != 16_000:
            return None
        try:
            import mlx_whisper
            import numpy as np
        except ImportError:
            return None
        audio = np.asarray(pcm_f32, dtype=np.float32)
        try:
            result = mlx_whisper.transcribe(
                audio,
                path_or_hf_repo=self._model_repo,
                language="en",
                condition_on_previous_text=False,
                verbose=False,
            )
        except Exception:
            return None
        text = str(result.get("text", "")).strip()
        return text or None
