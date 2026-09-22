"""Tests for gesture_control.vision.overlay -- drawing onto synthetic frames.

Uses plain numpy arrays as stand-in frames (no camera required); cv2's
drawing functions work identically on any correctly-shaped array.
"""

from __future__ import annotations

import numpy as np
from gesture_control.vision.geometry import HandObservation, Landmark
from gesture_control.vision.overlay import draw_hand_landmarks


def _make_hand(handedness: str = "Right", score: float = 0.95) -> HandObservation:
    """Build a synthetic HandObservation with 21 landmarks spread across the frame."""
    landmarks = tuple(Landmark(x=0.1 + (i * 0.03), y=0.1 + (i * 0.03), z=0.0) for i in range(21))
    return HandObservation(landmarks=landmarks, handedness=handedness, score=score)


def test_draw_hand_landmarks_returns_same_frame_with_unchanged_shape() -> None:
    """Drawing should mutate and return the same array without changing its shape/dtype."""
    frame = np.zeros((240, 320, 3), dtype=np.uint8)

    result = draw_hand_landmarks(frame, [_make_hand()])

    assert result is frame
    assert result.shape == (240, 320, 3)
    assert result.dtype == np.uint8


def test_draw_hand_landmarks_actually_draws_something() -> None:
    """A frame with a detected hand should no longer be all-black after drawing."""
    frame = np.zeros((240, 320, 3), dtype=np.uint8)

    draw_hand_landmarks(frame, [_make_hand()])

    assert frame.any(), "expected at least some pixels to be drawn on"


def test_draw_hand_landmarks_handles_no_hands_without_error() -> None:
    """An empty hand list (nothing detected this frame) should be a no-op, not an error."""
    frame = np.zeros((240, 320, 3), dtype=np.uint8)

    result = draw_hand_landmarks(frame, [])

    assert result is frame
    assert not result.any()


def test_draw_hand_landmarks_handles_multiple_hands() -> None:
    """Two simultaneously detected hands should both be drawable without error."""
    frame = np.zeros((240, 320, 3), dtype=np.uint8)

    result = draw_hand_landmarks(frame, [_make_hand("Left"), _make_hand("Right")])

    assert result.any()
