"""Apple Silicon streaming STT via MLX Whisper (utterance-endpointed)."""

from __future__ import annotations

import math
import queue
import threading
import time
from collections.abc import Callable

from gesture_control.voice.stream_contracts import TranscriptEvent, TranscriptEventKind
from gesture_control.voice.transcription import VOICE_SAMPLE_RATE

_DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"
# Bias decoding toward the closed command grammar without inventing free text.
_COMMAND_PROMPT = (
    "Voice commands: next tab, previous tab, new tab, close tab, go back, "
    "go forward, reload, refresh, open amazon, open reddit, open chatgpt, "
    "open claude, open gemini, scroll down, scroll up, press enter, cancel."
)
_CAPTURE_BLOCK_S = 0.1
# End a spoken line after this much trailing silence.
_SILENCE_END_S = 0.55
# Ignore ultra-short blips before starting a line.
_MIN_SPEECH_S = 0.18
# Drop lines that are too short to be a real command.
_MIN_UTTERANCE_SAMPLES = int(VOICE_SAMPLE_RATE * 0.25)
_RMS_SPEECH = 0.012
_RMS_SILENCE = 0.006
_MAX_UTTERANCE_SAMPLES = VOICE_SAMPLE_RATE * 12


def _rms(samples: list[float]) -> float:
    if not samples:
        return 0.0
    total = 0.0
    for value in samples:
        total += value * value
    return math.sqrt(total / len(samples))


class MlxWhisperStreamingTranscriber:
    """Offline STT that endpoints on silence, then decodes with MLX Whisper.

    Unlike Moonshine, this does not emit true mid-speech partials. It emits a
    lightweight PARTIAL while speech is active, then a FINAL after silence so
    ``large-v3-turbo`` can correct the whole utterance on Apple Silicon.
    """

    def __init__(
        self,
        model_repo: str = _DEFAULT_MODEL,
        *,
        silence_end_s: float = _SILENCE_END_S,
    ) -> None:
        """Create a transcriber for one Hugging Face MLX Whisper repo."""
        self._model_repo = model_repo
        self._silence_end_s = silence_end_s
        self._sink: Callable[[TranscriptEvent], None] | None = None
        self._stop = threading.Event()
        self._input_stream = None
        self._worker: threading.Thread | None = None
        self._audio_queue: queue.Queue[list[float] | None] = queue.Queue()
        self._line_id = 0
        self._model_loaded = False

    def start(self, sink: Callable[[TranscriptEvent], None]) -> None:
        """Begin microphone capture and silence-endpointed transcription."""
        self._sink = sink
        self._stop.clear()
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "Microphone streaming requires optional audio dependencies. "
                'Install them with: pip install -e ".[voice]"'
            ) from exc

        # Fail fast if mlx-whisper is missing before opening the mic.
        self._ensure_mlx()

        blocksize = max(1, int(VOICE_SAMPLE_RATE * _CAPTURE_BLOCK_S))
        audio_queue = self._audio_queue

        def capture_block(
            indata: object,
            frames: int,
            time_info: object,
            status: object,
        ) -> None:
            del frames, time_info, status
            import numpy as np

            samples = np.asarray(indata, dtype=np.float32)[:, 0]
            audio_queue.put(samples.astype(np.float32, copy=False).tolist())

        try:
            input_stream = sd.InputStream(
                samplerate=VOICE_SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=blocksize,
                callback=capture_block,
            )
        except Exception as exc:
            raise RuntimeError(
                "Could not open the default microphone for streaming. Check "
                "macOS Microphone permission and the selected input device."
            ) from exc

        self._input_stream = input_stream
        input_stream.start()
        self._worker = threading.Thread(
            target=self._run_loop,
            name="mlx-whisper-stt",
            daemon=True,
        )
        self._worker.start()

    def stop(self) -> None:
        """Stop capture and release audio resources."""
        self._stop.set()
        self._audio_queue.put(None)
        input_stream = self._input_stream
        if input_stream is not None:
            try:
                input_stream.stop()
                input_stream.close()
            except Exception:
                pass
            self._input_stream = None
        if self._worker is not None:
            self._worker.join(timeout=5.0)
            self._worker = None
        self._sink = None
        while True:
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

    def _run_loop(self) -> None:
        """Accumulate speech until silence, then emit one FINAL transcript."""
        speaking = False
        utterance: list[float] = []
        silence_samples = 0
        speech_samples = 0
        silence_needed = int(VOICE_SAMPLE_RATE * self._silence_end_s)
        min_speech = int(VOICE_SAMPLE_RATE * _MIN_SPEECH_S)
        while not self._stop.is_set():
            try:
                chunk = self._audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if chunk is None:
                break
            level = _rms(chunk)
            if not speaking:
                if level >= _RMS_SPEECH:
                    speaking = True
                    utterance = list(chunk)
                    silence_samples = 0
                    speech_samples = len(chunk)
                continue

            utterance.extend(chunk)
            if len(utterance) > _MAX_UTTERANCE_SAMPLES:
                del utterance[: len(utterance) - _MAX_UTTERANCE_SAMPLES]
            if level >= _RMS_SILENCE:
                silence_samples = 0
                speech_samples += len(chunk)
            else:
                silence_samples += len(chunk)

            if speech_samples >= min_speech and silence_samples >= silence_needed:
                pcm = utterance[: max(0, len(utterance) - silence_samples)]
                speaking = False
                utterance = []
                silence_samples = 0
                speech_samples = 0
                if len(pcm) < _MIN_UTTERANCE_SAMPLES:
                    continue
                text = self._transcribe(pcm)
                if text:
                    self._emit_final(self._line_id, text)
                self._line_id += 1

        if speaking and len(utterance) >= _MIN_UTTERANCE_SAMPLES:
            text = self._transcribe(utterance)
            if text:
                self._emit_final(self._line_id, text)

    def _emit_final(self, line_id: int, text: str) -> None:
        sink = self._sink
        if sink is None:
            return
        sink(
            TranscriptEvent(
                TranscriptEventKind.FINAL,
                text,
                line_id,
                time.monotonic(),
            ),
        )

    def _ensure_mlx(self) -> None:
        try:
            import mlx_whisper  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "mlx-whisper is not installed. "
                "pip install 'mlx-whisper' (Apple Silicon required)."
            ) from exc

    def _transcribe(self, pcm_f32: list[float]) -> str:
        """Decode one endpointed utterance with MLX Whisper."""
        try:
            import mlx_whisper
            import numpy as np
        except ImportError:
            return ""
        audio = np.asarray(pcm_f32, dtype=np.float32)
        try:
            result = mlx_whisper.transcribe(
                audio,
                path_or_hf_repo=self._model_repo,
                language="en",
                condition_on_previous_text=False,
                initial_prompt=_COMMAND_PROMPT,
                verbose=False,
            )
        except Exception:
            return ""
        self._model_loaded = True
        text = str(result.get("text", "")).strip()
        return text
