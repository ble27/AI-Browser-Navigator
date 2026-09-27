"""Tests for the Moonshine streaming STT adapter."""

from __future__ import annotations

import sys
import types

import pytest
from gesture_control.voice.moonshine_stt import MoonshineStreamingTranscriber
from gesture_control.voice.stream_contracts import TranscriptEventKind


def test_invalid_model_arch_raises() -> None:
    with pytest.raises(ValueError):
        MoonshineStreamingTranscriber(model_arch="tiny")


def test_stop_is_idempotent() -> None:
    transcriber = MoonshineStreamingTranscriber()
    transcriber.stop()
    transcriber.stop()


def test_missing_package_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    transcriber = MoonshineStreamingTranscriber()
    real_import = __import__

    def blocked_import(
        name: str,
        globals: object | None = None,
        locals: object | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "moonshine_voice":
            raise ImportError("blocked for test")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", blocked_import)
    with pytest.raises(RuntimeError, match="moonshine-voice"):
        transcriber.start(lambda _event: None)


def test_listener_maps_line_events() -> None:
    fake_module = types.ModuleType("moonshine_voice")

    class ModelArch:
        SMALL_STREAMING = "small"

    class TranscriptEventListener:
        pass

    class _Line:
        def __init__(self, text: str) -> None:
            self.text = text

    class _Event:
        def __init__(self, text: str) -> None:
            self.line = _Line(text)

    class _Stream:
        def __init__(self) -> None:
            self._listener = None

        def add_listener(self, listener: object) -> None:
            self._listener = listener

        def start(self) -> None:
            assert self._listener is not None
            self._listener.on_line_started(_Event("hel"))
            self._listener.on_line_text_changed(_Event("hello"))
            self._listener.on_line_completed(_Event("hello"))

        def stop(self) -> None:
            return None

    class Transcriber:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        def create_stream(self, **kwargs: object) -> _Stream:
            del kwargs
            return _Stream()

    def get_model_for_language(language: str, model_arch: object) -> tuple[str, object]:
        del language
        return "/tmp/model", model_arch

    fake_module.ModelArch = ModelArch
    fake_module.TranscriptEventListener = TranscriptEventListener
    fake_module.Transcriber = Transcriber
    fake_module.get_model_for_language = get_model_for_language

    sys.modules["moonshine_voice"] = fake_module
    events: list[tuple[TranscriptEventKind, str, int]] = []

    def sink(event: object) -> None:
        from gesture_control.voice.stream_contracts import TranscriptEvent

        assert isinstance(event, TranscriptEvent)
        events.append((event.kind, event.text, event.line_id))

    transcriber = MoonshineStreamingTranscriber()
    transcriber.start(sink)
    transcriber.stop()

    assert any(kind is TranscriptEventKind.PARTIAL for kind, _text, _line in events)
    assert events.count((TranscriptEventKind.FINAL, "hello", 0)) == 1
