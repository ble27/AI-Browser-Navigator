"""Moonshine streaming speech-to-text adapter."""

from __future__ import annotations

import inspect
import queue
import threading
import time
from collections.abc import Callable

from gesture_control.voice.redecode import FinalRedecoder, NullFinalRedecoder
from gesture_control.voice.stream_contracts import TranscriptEvent, TranscriptEventKind
from gesture_control.voice.transcription import VOICE_SAMPLE_RATE

_ALLOWED_MODELS = frozenset({"small_streaming", "medium_streaming"})
# Match the S0 spike chunk size (~100 ms) so partials arrive promptly.
_CAPTURE_BLOCK_S = 0.1
# Keep ~12 s of mic audio for optional FINAL redecode.
_MAX_REDECODE_SAMPLES = VOICE_SAMPLE_RATE * 12


class MoonshineStreamingTranscriber:
    """Offline streaming transcriber backed by ``moonshine-voice``.

    Moonshine streams do not capture the microphone themselves. ``start`` opens
    the default input device via ``sounddevice`` and pushes float32 chunks into
    ``stream.add_audio`` until ``stop``.
    """

    def __init__(
        self,
        model_arch: str = "small_streaming",
        update_interval_s: float = 0.3,
        *,
        redecoder: FinalRedecoder | None = None,
    ) -> None:
        """Create a transcriber for one Moonshine streaming architecture."""
        if model_arch not in _ALLOWED_MODELS:
            raise ValueError(f"Unsupported model_arch: {model_arch}")
        self._model_arch = model_arch
        self._update_interval_s = update_interval_s
        self._redecoder: FinalRedecoder = redecoder or NullFinalRedecoder()
        self._sink: Callable[[TranscriptEvent], None] | None = None
        self._stream = None
        self._input_stream = None
        self._line_id = 0
        self._stop = threading.Event()
        self._capture_thread: threading.Thread | None = None
        self._audio_queue: queue.Queue[list[float] | None] = queue.Queue()
        self._line_pcm: list[float] = []
        self._pcm_lock = threading.Lock()

    def start(self, sink: Callable[[TranscriptEvent], None]) -> None:
        """Begin streaming microphone audio to ``sink``."""
        self._sink = sink
        self._stop.clear()
        try:
            from moonshine_voice import Transcriber, get_model_for_language
        except ImportError as exc:
            raise RuntimeError(
                "moonshine-voice is not installed. pip install 'moonshine-voice==0.1.5'",
            ) from exc

        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "Microphone streaming requires optional audio dependencies. "
                'Install them with: pip install -e ".[voice]"'
            ) from exc

        from moonshine_voice import ModelArch, TranscriptEventListener

        arch = getattr(ModelArch, self._model_arch.upper())
        model_path, resolved_arch = get_model_for_language("en", arch)
        transcriber = Transcriber(
            model_path=model_path,
            model_arch=resolved_arch,
            update_interval=self._update_interval_s,
        )

        sink_ref = sink
        owner = self

        class _Listener(TranscriptEventListener):  # type: ignore[misc,valid-type]
            def __init__(self_inner) -> None:  # noqa: N805
                self_inner._line_id = 0

            def on_line_started(self_inner, event: object) -> None:  # noqa: N805
                with owner._pcm_lock:
                    owner._line_pcm = []
                self_inner._emit_partial(event, self_inner._line_id)

            def on_line_text_changed(self_inner, event: object) -> None:  # noqa: N805
                self_inner._emit_partial(event, self_inner._line_id)

            def on_line_completed(self_inner, event: object) -> None:  # noqa: N805
                self_inner._emit_final(event, self_inner._line_id)
                self_inner._line_id += 1

            def _emit_partial(self_inner, event: object, line_id: int) -> None:  # noqa: N805
                if sink_ref is None:
                    return
                text = event.line.text  # type: ignore[attr-defined]
                sink_ref(
                    TranscriptEvent(
                        TranscriptEventKind.PARTIAL,
                        text,
                        line_id,
                        time.monotonic(),
                    ),
                )

            def _emit_final(self_inner, event: object, line_id: int) -> None:  # noqa: N805
                if sink_ref is None:
                    return
                text = event.line.text  # type: ignore[attr-defined]
                with owner._pcm_lock:
                    pcm = list(owner._line_pcm)
                    owner._line_pcm = []
                replacement = owner._redecoder.redecode(pcm, VOICE_SAMPLE_RATE)
                if replacement:
                    text = replacement
                sink_ref(
                    TranscriptEvent(
                        TranscriptEventKind.FINAL,
                        text,
                        line_id,
                        time.monotonic(),
                    ),
                )

        listener = _Listener()
        stream = transcriber.create_stream(update_interval=self._update_interval_s)
        stream.add_listener(listener)
        stream.start()
        self._stream = stream

        blocksize = max(1, int(VOICE_SAMPLE_RATE * _CAPTURE_BLOCK_S))
        audio_queue = self._audio_queue

        def capture_block(
            indata: object,
            frames: int,
            time_info: object,
            status: object,
        ) -> None:
            """Enqueue one mic block for the feeder thread."""
            del frames, time_info, status
            import numpy as np

            samples = np.asarray(indata, dtype=np.float32)[:, 0]
            audio_queue.put(samples.astype(np.float32, copy=False).tolist())

        def feed_loop() -> None:
            """Push queued mic blocks into Moonshine until stopped."""
            assert self._stream is not None
            while not self._stop.is_set():
                try:
                    chunk = audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if chunk is None:
                    break
                with self._pcm_lock:
                    self._line_pcm.extend(chunk)
                    overflow = len(self._line_pcm) - _MAX_REDECODE_SAMPLES
                    if overflow > 0:
                        del self._line_pcm[:overflow]
                try:
                    self._stream.add_audio(chunk, VOICE_SAMPLE_RATE)
                except Exception:
                    # Stream may already be stopped during shutdown.
                    break

        try:
            input_stream = sd.InputStream(
                samplerate=VOICE_SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=blocksize,
                callback=capture_block,
            )
        except Exception as exc:
            stream.stop()
            try:
                stream.close()
            except Exception:
                pass
            self._stream = None
            raise RuntimeError(
                "Could not open the default microphone for streaming. Check "
                "macOS Microphone permission and the selected input device."
            ) from exc

        self._input_stream = input_stream
        input_stream.start()
        self._capture_thread = threading.Thread(
            target=feed_loop,
            name="moonshine-mic-feed",
            daemon=True,
        )
        self._capture_thread.start()

    def stop(self) -> None:
        """Stop streaming and release audio resources."""
        self._stop.set()
        self._audio_queue.put(None)
        input_stream = getattr(self, "_input_stream", None)
        if input_stream is not None:
            try:
                input_stream.stop()
                input_stream.close()
            except Exception:
                pass
            self._input_stream = None
        if self._capture_thread is not None:
            self._capture_thread.join(timeout=2.0)
            self._capture_thread = None
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self._sink = None
        # Drain any leftover blocks so a later start() begins empty.
        while True:
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break


MoonshineStreamingTranscriber.__signature__ = inspect.Signature(
    [
        inspect.Parameter("self", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter(
            "model_arch",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default="small_streaming",
        ),
        inspect.Parameter(
            "update_interval_s",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=0.3,
        ),
    ],
)
