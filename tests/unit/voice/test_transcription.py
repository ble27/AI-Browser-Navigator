"""Tests for the injectable faster-whisper transcription seam."""

from __future__ import annotations

import builtins
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import pytest
from gesture_control.voice.transcription import FasterWhisperTranscriber
from numpy.typing import NDArray


@dataclass
class _FakeSegment:
    text: str


class _FakeModel:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def transcribe(
        self,
        audio: NDArray[np.float32],
        *,
        language: str,
        beam_size: int,
        vad_filter: bool,
        condition_on_previous_text: bool,
        hotwords: str,
    ) -> tuple[Iterable[_FakeSegment], object]:
        self.calls.append(
            {
                "audio": audio,
                "language": language,
                "beam_size": beam_size,
                "vad_filter": vad_filter,
                "condition_on_previous_text": condition_on_previous_text,
                "hotwords": hotwords,
            }
        )
        return [_FakeSegment("  Next "), _FakeSegment(" tab  ")], object()


def test_transcriber_uses_short_english_command_settings() -> None:
    model = _FakeModel()
    created_with: list[tuple[str, str, str]] = []

    def factory(model_name: str, device: str, compute_type: str) -> _FakeModel:
        created_with.append((model_name, device, compute_type))
        return model

    transcriber = FasterWhisperTranscriber(model_factory=factory)
    audio = np.zeros(1600, dtype=np.float32)

    assert transcriber.transcribe(audio) == "Next tab"
    assert created_with == [("tiny.en", "cpu", "int8")]
    assert model.calls == [
        {
            "audio": audio,
            "language": "en",
            "beam_size": 1,
            "vad_filter": True,
            "condition_on_previous_text": False,
            "hotwords": (
                "next tab switch tab previous tab new tab close tab go back "
                "go forward reload refresh open cursor open apple"
            ),
        }
    ]


def test_transcriber_materializes_segment_iterator() -> None:
    class _IteratorModel(_FakeModel):
        def transcribe(
            self,
            audio: NDArray[np.float32],
            *,
            language: str,
            beam_size: int,
            vad_filter: bool,
            condition_on_previous_text: bool,
            hotwords: str,
        ) -> tuple[Iterable[_FakeSegment], object]:
            del audio, language, beam_size, vad_filter, condition_on_previous_text, hotwords
            return iter([_FakeSegment("reload")]), object()

    transcriber = FasterWhisperTranscriber(
        model_factory=lambda _name, _device, _compute: _IteratorModel()
    )

    assert transcriber.transcribe(np.zeros(1600, dtype=np.float32)) == "reload"


@pytest.mark.parametrize(
    ("audio", "sample_rate"),
    [
        (np.zeros((10, 1), dtype=np.float32), 16_000),
        (np.zeros(10, dtype=np.float64), 16_000),
        (np.zeros(10, dtype=np.float32), 44_100),
    ],
)
def test_transcriber_rejects_unsupported_audio(audio: object, sample_rate: int) -> None:
    transcriber = FasterWhisperTranscriber(
        model_factory=lambda _name, _device, _compute: _FakeModel()
    )

    with pytest.raises(ValueError):
        transcriber.transcribe(audio, sample_rate)  # type: ignore[arg-type]


def test_model_initialization_error_is_actionable() -> None:
    def failing_factory(_name: str, _device: str, _compute: str) -> _FakeModel:
        raise OSError("download failed")

    with pytest.raises(RuntimeError, match="first run may need internet"):
        FasterWhisperTranscriber(model_factory=failing_factory)


def test_empty_segments_produce_an_empty_transcript() -> None:
    class _EmptyModel(_FakeModel):
        def transcribe(
            self,
            audio: NDArray[np.float32],
            *,
            language: str,
            beam_size: int,
            vad_filter: bool,
            condition_on_previous_text: bool,
            hotwords: str,
        ) -> tuple[Iterable[_FakeSegment], object]:
            del audio, language, beam_size, vad_filter, condition_on_previous_text, hotwords
            return iter(()), object()

    transcriber = FasterWhisperTranscriber(
        model_factory=lambda _name, _device, _compute: _EmptyModel()
    )

    assert transcriber.transcribe(np.zeros(16, dtype=np.float32)) == ""


def test_missing_faster_whisper_dependency_has_actionable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def import_without_whisper(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "faster_whisper":
            raise ModuleNotFoundError("No module named 'faster_whisper'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", import_without_whisper)

    with pytest.raises(RuntimeError, match=r"optional dependencies.*\[voice\]") as exc_info:
        FasterWhisperTranscriber()

    assert isinstance(exc_info.value.__cause__, ModuleNotFoundError)


def test_transcription_failure_is_wrapped_with_actionable_context() -> None:
    class _FailingModel(_FakeModel):
        def transcribe(
            self,
            audio: NDArray[np.float32],
            *,
            language: str,
            beam_size: int,
            vad_filter: bool,
            condition_on_previous_text: bool,
            hotwords: str,
        ) -> tuple[Iterable[_FakeSegment], object]:
            del audio, language, beam_size, vad_filter, condition_on_previous_text, hotwords
            raise OSError("corrupt model file")

    transcriber = FasterWhisperTranscriber(
        model_factory=lambda _name, _device, _compute: _FailingModel()
    )

    with pytest.raises(RuntimeError, match="transcription failed") as exc_info:
        transcriber.transcribe(np.zeros(16, dtype=np.float32))

    assert isinstance(exc_info.value.__cause__, OSError)
