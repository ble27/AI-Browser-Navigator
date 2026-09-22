"""Tests for pure M2 cursor and pinch gesture logic."""

from __future__ import annotations

import pytest
from gesture_control.gestures.cursor import (
    CursorMapper,
    HandPresenceHold,
    PointerGestureRecognizer,
)
from gesture_control.vision.geometry import HandLandmarkIndex, HandObservation, Landmark


def _hand(index_tip: Landmark, thumb_tip: Landmark) -> HandObservation:
    """Build a synthetic hand with a stable unit-sized pinch reference."""
    landmarks = [Landmark(0.2, 0.2, 0.0) for _ in range(21)]
    landmarks[HandLandmarkIndex.WRIST] = Landmark(0.0, 0.0, 0.0)
    landmarks[HandLandmarkIndex.INDEX_FINGER_MCP] = Landmark(1.0, 0.0, 0.0)
    landmarks[HandLandmarkIndex.INDEX_FINGER_TIP] = index_tip
    landmarks[HandLandmarkIndex.THUMB_TIP] = thumb_tip
    return HandObservation(tuple(landmarks), "Right", 0.99)


def test_presence_hold_bridges_a_short_gap_then_releases() -> None:
    """A missed frame keeps the last hand; a longer gap clears it."""
    hold = HandPresenceHold(hold_s=0.12)
    hand = _hand(Landmark(0.4, 0.4, 0.0), Landmark(0.1, 0.4, 0.0))

    assert hold.select([hand], 1.0) is hand
    assert hold.select([], 1.1) is hand
    assert hold.select([], 1.2) is None


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


def test_cursor_mapper_follows_a_fast_swipe_without_trailing() -> None:
    """A quick fingertip move should land near the target within one sample gap."""
    mapper = CursorMapper(1001, 1001, edge_margin=0.0)

    assert mapper.map(1.0, 0.0, 0.0) == (0, 0)
    x, y = mapper.map(0.0, 1.0, 0.10)

    # A fixed 0.4 exponential smoother would still be near (400, 400) here.
    assert x > 750
    assert y > 750


def test_cursor_mapper_holds_still_while_the_fingertip_jitters() -> None:
    """Landmark noise around a resting fingertip must not hunt the cursor."""
    mapper = CursorMapper(1920, 1080, edge_margin=0.0)
    positions = [
        mapper.map(
            0.5 + (0.004 if index % 2 == 0 else -0.004),
            0.5 + (0.003 if index % 2 == 0 else -0.003),
            index / 30.0,
        )
        for index in range(45)
    ]

    assert positions[1:] == [positions[0]] * (len(positions) - 1)


def test_cursor_mapper_tracks_a_steady_drift() -> None:
    """Motion that leaves the resting radius should keep updating, not stair-step."""
    mapper = CursorMapper(1001, 1001, edge_margin=0.0)
    positions = [mapper.map(index / 30.0 * 0.25, 0.5, index / 30.0)[0] for index in range(31)]

    assert positions[0] == 1000
    assert positions[-1] < 820
    assert positions[-1] < positions[0] - 100


def test_cursor_mapper_still_follows_a_slow_move() -> None:
    """The resting deadzone must not pin the cursor during a deliberate drift."""
    mapper = CursorMapper(1001, 1001, edge_margin=0.0)
    mapper.map(1.0, 0.5, 0.0)
    x, _y = mapper.map(0.7, 0.5, 0.5)

    assert x > 200


def test_cursor_mapper_mirrors_the_camera_x_axis() -> None:
    """A hand moving left in a selfie view must move the cursor left."""
    mapper = CursorMapper(101, 101, edge_margin=0.0)

    assert mapper.map(1.0, 0.5, 0.0) == (0, 50)
    assert mapper.map(0.0, 0.5, 0.05) == (100, 50)


def test_cursor_mapper_uses_an_inset_active_region() -> None:
    """A fingertip inside the camera, not on its edge, should reach the screen edge."""
    mapper = CursorMapper(101, 101, edge_margin=0.2)

    assert mapper.map(0.2, 0.2, 0.0) == (100, 0)


@pytest.mark.parametrize(
    ("width", "height", "edge_margin"),
    [(0, 1, 0.0), (1, 0, 0.0), (10, 10, -0.1), (10, 10, 0.5)],
)
def test_cursor_mapper_rejects_invalid_configuration(
    width: int, height: int, edge_margin: float
) -> None:
    """Invalid dimensions or an active-region inset should fail at configuration time."""
    with pytest.raises(ValueError):
        CursorMapper(width, height, edge_margin=edge_margin)
