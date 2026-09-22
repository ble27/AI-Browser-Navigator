"""Drawing helpers for visualizing detected hands on a video frame.

Used by the ``--debug`` CLI flag (see :mod:`gesture_control.app`) to render
a live skeleton overlay for development and manual QA. Not used in the
"headless" gesture-control runtime path, which needs no display.
"""

from __future__ import annotations

import cv2
import numpy as np

from gesture_control.vision.geometry import (
    HAND_CONNECTIONS,
    HandObservation,
    normalized_to_pixel_coords,
)

_LANDMARK_COLOR_BGR = (0, 215, 255)  # amber
_CONNECTION_COLOR_BGR = (60, 200, 60)  # green
_LABEL_COLOR_BGR = (255, 255, 255)  # white
_LANDMARK_RADIUS_PX = 4
_CONNECTION_THICKNESS_PX = 2


def draw_hand_landmarks(frame_bgr: np.ndarray, hands: list[HandObservation]) -> np.ndarray:
    """Draw landmark points, skeleton connections, and a handedness label for each hand.

    Mutates ``frame_bgr`` in place (drawing directly onto the array, as is
    conventional for OpenCV) and also returns it, so calls can be chained.

    Args:
        frame_bgr: The BGR frame to draw on.
        hands: Detected hands, as produced by
            :meth:`gesture_control.vision.hand_landmarker.HandLandmarkerService.detect`.

    Returns:
        The same ``frame_bgr`` array, for convenient chaining.
    """
    frame_height, frame_width = frame_bgr.shape[:2]
    for hand in hands:
        pixel_points = [
            normalized_to_pixel_coords(landmark.x, landmark.y, frame_width, frame_height)
            for landmark in hand.landmarks
        ]
        _draw_connections(frame_bgr, pixel_points)
        _draw_points(frame_bgr, pixel_points)
        _draw_handedness_label(frame_bgr, hand, pixel_points)
    return frame_bgr


def _draw_connections(frame_bgr: np.ndarray, pixel_points: list[tuple[int, int] | None]) -> None:
    """Draw skeleton lines between connected landmark pairs, skipping off-frame points."""
    for start_idx, end_idx in HAND_CONNECTIONS:
        start = pixel_points[start_idx]
        end = pixel_points[end_idx]
        if start is None or end is None:
            continue
        cv2.line(frame_bgr, start, end, _CONNECTION_COLOR_BGR, _CONNECTION_THICKNESS_PX)


def _draw_points(frame_bgr: np.ndarray, pixel_points: list[tuple[int, int] | None]) -> None:
    """Draw a filled circle at each visible landmark."""
    for point in pixel_points:
        if point is None:
            continue
        cv2.circle(frame_bgr, point, _LANDMARK_RADIUS_PX, _LANDMARK_COLOR_BGR, thickness=-1)


def _draw_handedness_label(
    frame_bgr: np.ndarray,
    hand: HandObservation,
    pixel_points: list[tuple[int, int] | None],
) -> None:
    """Draw a text label (e.g. "Left (0.98)") near the wrist, if visible."""
    wrist_point = pixel_points[0]
    if wrist_point is None:
        return
    label_position = (wrist_point[0], max(wrist_point[1] - 20, 20))
    cv2.putText(
        frame_bgr,
        f"{hand.handedness} ({hand.score:.2f})",
        label_position,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        _LABEL_COLOR_BGR,
        2,
    )
