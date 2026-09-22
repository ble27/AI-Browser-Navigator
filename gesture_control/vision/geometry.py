"""Pure geometry helpers for hand-landmark data.

Everything in this module operates on plain floats/tuples and has no
dependency on OpenCV, MediaPipe, or any I/O -- it is safe to unit test with
synthetic data. :mod:`gesture_control.vision.hand_landmarker` converts
MediaPipe's native result objects into the dataclasses defined here so the
rest of the codebase (gesture recognition, overlays, tests) never has to deal
with MediaPipe's SDK types directly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum


class HandLandmarkIndex(IntEnum):
    """Named indices into the 21-point MediaPipe hand landmark model.

    See the MediaPipe HandLandmarker documentation for the canonical diagram
    of these 21 points. Using named indices instead of raw integers makes
    gesture logic (e.g. "index fingertip") self-documenting.
    """

    WRIST = 0
    THUMB_CMC = 1
    THUMB_MCP = 2
    THUMB_IP = 3
    THUMB_TIP = 4
    INDEX_FINGER_MCP = 5
    INDEX_FINGER_PIP = 6
    INDEX_FINGER_DIP = 7
    INDEX_FINGER_TIP = 8
    MIDDLE_FINGER_MCP = 9
    MIDDLE_FINGER_PIP = 10
    MIDDLE_FINGER_DIP = 11
    MIDDLE_FINGER_TIP = 12
    RING_FINGER_MCP = 13
    RING_FINGER_PIP = 14
    RING_FINGER_DIP = 15
    RING_FINGER_TIP = 16
    PINKY_MCP = 17
    PINKY_PIP = 18
    PINKY_DIP = 19
    PINKY_TIP = 20


# Skeleton edges between the 21 landmarks, grouped by finger and mirroring
# MediaPipe's own `hands_connections.HAND_CONNECTIONS` set. Kept as plain
# tuples (not a MediaPipe type) so this module has zero MediaPipe dependency.
_PALM_CONNECTIONS: tuple[tuple[int, int], ...] = (
    (0, 1),
    (0, 5),
    (9, 13),
    (13, 17),
    (5, 9),
    (0, 17),
)
_THUMB_CONNECTIONS: tuple[tuple[int, int], ...] = ((1, 2), (2, 3), (3, 4))
_INDEX_CONNECTIONS: tuple[tuple[int, int], ...] = ((5, 6), (6, 7), (7, 8))
_MIDDLE_CONNECTIONS: tuple[tuple[int, int], ...] = ((9, 10), (10, 11), (11, 12))
_RING_CONNECTIONS: tuple[tuple[int, int], ...] = ((13, 14), (14, 15), (15, 16))
_PINKY_CONNECTIONS: tuple[tuple[int, int], ...] = ((17, 18), (18, 19), (19, 20))

HAND_CONNECTIONS: tuple[tuple[int, int], ...] = (
    _PALM_CONNECTIONS
    + _THUMB_CONNECTIONS
    + _INDEX_CONNECTIONS
    + _MIDDLE_CONNECTIONS
    + _RING_CONNECTIONS
    + _PINKY_CONNECTIONS
)


@dataclass(frozen=True, slots=True)
class Landmark:
    """A single normalized 3D hand landmark.

    Attributes:
        x: Horizontal position, normalized to ``[0, 1]`` across frame width
            (0 = left edge, 1 = right edge).
        y: Vertical position, normalized to ``[0, 1]`` across frame height
            (0 = top edge, 1 = bottom edge).
        z: Depth relative to the wrist, roughly normalized by hand size.
            Smaller (more negative) values are closer to the camera.
    """

    x: float
    y: float
    z: float


@dataclass(frozen=True, slots=True)
class HandObservation:
    """A single detected hand, with all 21 landmarks and handedness.

    Attributes:
        landmarks: Exactly 21 landmarks, indexed per :class:`HandLandmarkIndex`.
        handedness: ``"Left"`` or ``"Right"``, as reported by the model. Note
            this is the hand's real-world handedness, which is mirrored
            relative to a selfie-view camera image.
        score: Model confidence for the handedness classification, in
            ``[0, 1]``.
    """

    landmarks: tuple[Landmark, ...]
    handedness: str
    score: float

    def landmark(self, index: HandLandmarkIndex) -> Landmark:
        """Look up a landmark by name instead of raw integer index.

        Args:
            index: The named landmark to retrieve.

        Returns:
            The corresponding :class:`Landmark`.
        """
        return self.landmarks[index]


def normalized_to_pixel_coords(
    x: float, y: float, frame_width: int, frame_height: int
) -> tuple[int, int] | None:
    """Convert a normalized ``[0, 1]`` coordinate to integer pixel coordinates.

    Args:
        x: Normalized horizontal position.
        y: Normalized vertical position.
        frame_width: Frame width in pixels.
        frame_height: Frame height in pixels.

    Returns:
        An ``(x_px, y_px)`` tuple, or ``None`` if the point falls outside the
        visible ``[0, 1]`` range (mirrors MediaPipe's own drawing-utils
        behavior of not rendering off-frame points).
    """
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        return None
    x_px = min(math.floor(x * frame_width), frame_width - 1)
    y_px = min(math.floor(y * frame_height), frame_height - 1)
    return x_px, y_px


def landmark_distance(a: Landmark, b: Landmark, *, use_depth: bool = False) -> float:
    """Compute the Euclidean distance between two landmarks.

    This operates in normalized coordinate space, so the result is only
    meaningful relative to other distances from the same frame/hand (e.g.
    comparing a pinch distance against a per-hand reference distance) -- it
    is not a physical-world unit.

    Args:
        a: The first landmark.
        b: The second landmark.
        use_depth: Whether to include the ``z`` axis in the distance
            calculation. Depth is noisier than x/y, so most 2D gestures
            (e.g. pinch detection) should leave this ``False``.

    Returns:
        The Euclidean distance between ``a`` and ``b``.
    """
    dx = a.x - b.x
    dy = a.y - b.y
    dz = (a.z - b.z) if use_depth else 0.0
    return math.sqrt(dx * dx + dy * dy + dz * dz)
