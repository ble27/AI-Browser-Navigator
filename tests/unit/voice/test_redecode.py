"""Tests for optional FINAL redecode adapters."""

from __future__ import annotations

from gesture_control.voice.redecode import (
    FasterWhisperFinalRedecoder,
    MlxWhisperFinalRedecoder,
    NullFinalRedecoder,
)


def test_null_redecoder_keeps_moonshine_text() -> None:
    assert NullFinalRedecoder().redecode([0.0] * 100, 16_000) is None


def test_faster_whisper_redecoder_returns_none_without_audio() -> None:
    assert FasterWhisperFinalRedecoder().redecode([], 16_000) is None


def test_mlx_redecoder_returns_none_without_audio() -> None:
    assert MlxWhisperFinalRedecoder().redecode([], 16_000) is None


def test_mlx_redecoder_rejects_non_16k() -> None:
    assert MlxWhisperFinalRedecoder().redecode([0.1] * 100, 8_000) is None
