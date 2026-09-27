"""Tests for MLX Whisper streaming STT adapter."""

from __future__ import annotations

from gesture_control.voice.mlx_stt import MlxWhisperStreamingTranscriber, _rms


def test_rms_empty_is_zero() -> None:
    assert _rms([]) == 0.0


def test_rms_of_constant_signal() -> None:
    assert abs(_rms([0.5, -0.5, 0.5, -0.5]) - 0.5) < 1e-6


def test_transcriber_defaults_to_turbo_repo() -> None:
    stt = MlxWhisperStreamingTranscriber()
    assert stt._model_repo == "mlx-community/whisper-large-v3-turbo"
