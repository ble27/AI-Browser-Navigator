"""Tests for gesture_control.vision.geometry -- pure math, no hardware."""

from __future__ import annotations

import math

from gesture_control.vision.geometry import (
    HAND_CONNECTIONS,
    HandLandmarkIndex,
    HandObservation,
    Landmark,
    landmark_distance,
    normalized_to_pixel_coords,
)


def test_normalized_to_pixel_coords_maps_into_frame_bounds() -> None:
    """A midpoint normalized coordinate should map to the frame's midpoint pixel."""
    result = normalized_to_pixel_coords(0.5, 0.5, frame_width=640, frame_height=480)
    assert result == (320, 240)


def test_normalized_to_pixel_coords_clamps_upper_edge_into_bounds() -> None:
    """x=1.0/y=1.0 is the far edge; it should clamp to the last valid pixel, not overflow."""
    result = normalized_to_pixel_coords(1.0, 1.0, frame_width=640, frame_height=480)
    assert result == (639, 479)


def test_normalized_to_pixel_coords_returns_none_when_out_of_frame() -> None:
    """Coordinates outside [0, 1] represent an off-frame landmark and should be dropped."""
    assert normalized_to_pixel_coords(-0.1, 0.5, frame_width=640, frame_height=480) is None
    assert normalized_to_pixel_coords(0.5, 1.1, frame_width=640, frame_height=480) is None


def test_hand_connections_only_reference_valid_landmark_indices() -> None:
    """Every connection endpoint must be a valid index into the 21-point landmark list."""
    for start_idx, end_idx in HAND_CONNECTIONS:
        assert 0 <= start_idx <= 20
        assert 0 <= end_idx <= 20
        assert start_idx != end_idx


def test_hand_connections_has_no_duplicate_edges() -> None:
    """The connection set shouldn't draw the same skeleton edge twice."""
    assert len(HAND_CONNECTIONS) == len(set(HAND_CONNECTIONS))


def test_landmark_distance_between_identical_points_is_zero() -> None:
    """Distance from a point to itself should be exactly zero."""
    point = Landmark(x=0.3, y=0.4, z=0.0)
    assert landmark_distance(point, point) == 0.0


def test_landmark_distance_matches_known_3_4_5_triangle() -> None:
    """A 3-4-5 right triangle in normalized space should yield distance 5."""
    a = Landmark(x=0.0, y=0.0, z=0.0)
    b = Landmark(x=3.0, y=4.0, z=0.0)
    assert math.isclose(landmark_distance(a, b), 5.0)


def test_landmark_distance_ignores_depth_by_default() -> None:
    """z should not affect the 2D distance used for most gesture thresholds by default."""
    a = Landmark(x=0.0, y=0.0, z=0.0)
    b = Landmark(x=0.0, y=0.0, z=10.0)
    assert landmark_distance(a, b) == 0.0
    assert landmark_distance(a, b, use_depth=True) == 10.0


def test_hand_observation_landmark_lookup_by_named_index() -> None:
    """HandObservation.landmark() should let callers use named indices, not raw ints."""
    landmarks = tuple(Landmark(x=i / 20, y=i / 20, z=0.0) for i in range(21))
    hand = HandObservation(landmarks=landmarks, handedness="Right", score=0.99)

    wrist = hand.landmark(HandLandmarkIndex.WRIST)
    index_tip = hand.landmark(HandLandmarkIndex.INDEX_FINGER_TIP)

    assert wrist == landmarks[0]
    assert index_tip == landmarks[8]
