"""Tests for pure M2 cursor and pinch gesture logic."""

from __future__ import annotations

import pytest
from gesture_control.gestures.cursor import CursorMapper, PointerGestureRecognizer
from gesture_control.vision.geometry import HandLandmarkIndex, HandObservation, Landmark


def _hand(index_tip: Landmark, thumb_tip: Landmark) -> HandObservation:
    """Build a synthetic hand with a stable unit-sized pinch reference."""
    landmarks = [Landmark(0.2, 0.2, 0.0) for _ in range(21)]
    landmarks[HandLandmarkIndex.WRIST] = Landmark(0.0, 0.0, 0.0)
    landmarks[HandLandmarkIndex.INDEX_FINGER_MCP] = Landmark(1.0, 0.0, 0.0)
    landmarks[HandLandmarkIndex.INDEX_FINGER_TIP] = index_tip
    landmarks[HandLandmarkIndex.THUMB_TIP] = thumb_tip
    return HandObservation(tuple(landmarks), "Right", 0.99)


def test_recognizer_emits_one_event_for_each_pinch() -> None:
    """A held pinch must click once until it has been released and pinched again."""
    recognizer = PointerGestureRecognizer()
    pinched_hand = _hand(Landmark(0.55, 0.5, 0.0), Landmark(0.5, 0.5, 0.0))
    open_hand = _hand(Landmark(0.9, 0.5, 0.0), Landmark(0.1, 0.5, 0.0))

    assert recognizer.recognize(pinched_hand).pinch_started is True
    assert recognizer.recognize(pinched_hand).pinch_started is False
    assert recognizer.recognize(open_hand).pinch_started is False
    assert recognizer.recognize(pinched_hand).pinch_started is True


def test_recognizer_clamps_pointer_coordinates() -> None:
    """Pointer coordinates outside the camera image should clamp to the screen edge."""
    recognizer = PointerGestureRecognizer()
    hand = _hand(Landmark(1.5, -0.5, 0.0), Landmark(0.0, 0.0, 0.0))

    pointer = recognizer.recognize(hand)

    assert (pointer.x, pointer.y) == (1.0, 0.0)


def test_cursor_mapper_smooths_toward_target() -> None:
    """Cursor smoothing should move partway toward a changed fingertip target."""
    mapper = CursorMapper(101, 101, smoothing=0.4)

    assert mapper.map(1.0, 0.0) == (0, 0)
    assert mapper.map(0.0, 1.0) == (40, 40)


def test_cursor_mapper_mirrors_the_camera_x_axis() -> None:
    """A hand moving left in a selfie view must move the cursor left."""
    mapper = CursorMapper(101, 101, smoothing=1.0)

    assert mapper.map(1.0, 0.5) == (0, 50)
    assert mapper.map(0.0, 0.5) == (100, 50)


@pytest.mark.parametrize(
    ("width", "height", "smoothing"),
    [(0, 1, 0.5), (1, 0, 0.5), (1, 1, 0.0), (1, 1, 1.1)],
)
def test_cursor_mapper_rejects_invalid_configuration(
    width: int, height: int, smoothing: float
) -> None:
    """Invalid dimensions or smoothing factors should fail at configuration time."""
    with pytest.raises(ValueError):
        CursorMapper(width, height, smoothing)
