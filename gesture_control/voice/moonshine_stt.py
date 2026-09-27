"""Moonshine streaming speech-to-text adapter."""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable

from gesture_control.voice.stream_contracts import TranscriptEvent, TranscriptEventKind

_ALLOWED_MODELS = frozenset({"small_streaming", "medium_streaming"})


class MoonshineStreamingTranscriber:
    """Offline streaming transcriber backed by ``moonshine-voice``."""

    def __init__(
        self,
        model_arch: str = "small_streaming",
        update_interval_s: float = 0.3,
    ) -> None:
        """Create a transcriber for one Moonshine streaming architecture."""
        if model_arch not in _ALLOWED_MODELS:
            raise ValueError(f"Unsupported model_arch: {model_arch}")
        self._model_arch = model_arch
        self._update_interval_s = update_interval_s
        self._sink: Callable[[TranscriptEvent], None] | None = None
        self._stream = None
        self._line_id = 0

    def start(self, sink: Callable[[TranscriptEvent], None]) -> None:
        """Begin streaming microphone audio to ``sink``."""
        self._sink = sink
        try:
            from moonshine_voice import Transcriber, get_model_for_language
        except ImportError as exc:
            raise RuntimeError(
                "moonshine-voice is not installed. pip install 'moonshine-voice==0.1.5'",
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

        class _Listener(TranscriptEventListener):  # type: ignore[misc,valid-type]
            def __init__(self_inner) -> None:  # noqa: N805
                self_inner._line_id = 0

            def on_line_started(self_inner, event: object) -> None:  # noqa: N805
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

    def stop(self) -> None:
        """Stop streaming and release audio resources."""
        if self._stream is not None:
            self._stream.stop()
            self._stream = None
        self._sink = None


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
