"""Tests for hardware-free microphone speech-boundary state."""

from __future__ import annotations

import numpy as np
import pytest
from gesture_control.voice.audio import RecordingConfig, UtteranceSegmenter
from numpy.typing import NDArray


def _block(config: RecordingConfig, amplitude: float) -> NDArray[np.float32]:
    return np.full(config.block_size, amplitude, dtype=np.float32)


def test_segmenter_waits_for_speech_and_stops_after_silence() -> None:
    config = RecordingConfig(
        block_duration_s=0.1,
        speech_threshold=0.1,
        min_speech_s=0.2,
        pre_roll_s=0.3,
        trailing_silence_s=0.2,
        max_utterance_s=2.0,
    )
    segmenter = UtteranceSegmenter(config)

    assert segmenter.add_block(_block(config, 0.0)) is None
    assert segmenter.add_block(_block(config, 0.2)) is None
    assert segmenter.add_block(_block(config, 0.2)) is None
    assert segmenter.add_block(_block(config, 0.2)) is None
    assert segmenter.add_block(_block(config, 0.0)) is None
    utterance = segmenter.add_block(_block(config, 0.0))

    assert utterance is not None
    assert utterance.dtype == np.float32
    assert utterance.size == config.block_size * 6
    assert np.all(utterance[: config.block_size] == 0.0)


def test_segmenter_caps_a_continuous_utterance() -> None:
    config = RecordingConfig(
        block_duration_s=0.1,
        speech_threshold=0.1,
        min_speech_s=0.1,
        pre_roll_s=0.1,
        trailing_silence_s=0.2,
        max_utterance_s=0.5,
    )
    segmenter = UtteranceSegmenter(config)
    utterance = None

    for _ in range(5):
        utterance = segmenter.add_block(_block(config, 0.2))

    assert utterance is not None
    assert utterance.size == config.sample_rate * 0.5


def test_segmenter_rejects_wrong_block_shape_and_dtype() -> None:
    config = RecordingConfig(block_duration_s=0.1)
    segmenter = UtteranceSegmenter(config)

    with pytest.raises(ValueError, match="mono samples"):
        segmenter.add_block(np.zeros(config.block_size - 1, dtype=np.float32))
    with pytest.raises(ValueError, match="float32"):
        segmenter.add_block(np.zeros(config.block_size, dtype=np.float64))  # type: ignore[arg-type]
