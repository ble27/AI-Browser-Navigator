"""Pure gesture recognition and cursor-coordinate smoothing for M2.

This module deliberately has no dependency on OpenCV, MediaPipe, or an input
backend. It turns a detected hand into normalized pointer and pinch events
that can be tested with synthetic landmarks.
"""

from __future__ import annotations

from dataclasses import dataclass

from gesture_control.vision.geometry import HandLandmarkIndex, HandObservation, landmark_distance

_PINCH_CLOSE_RATIO = 0.35
_PINCH_OPEN_RATIO = 0.45
_DEFAULT_SMOOTHING = 0.4


@dataclass(frozen=True, slots=True)
class PointerGesture:
    """The pointer state recognized from one hand in a video frame.

    Attributes:
        x: Normalized horizontal index-fingertip position, clamped to ``[0, 1]``.
        y: Normalized vertical index-fingertip position, clamped to ``[0, 1]``.
        is_pinching: Whether the thumb and index fingertips are currently pinched.
        pinch_started: Whether a thumb-index pinch began in this frame.
    """

    x: float
    y: float
    is_pinching: bool
    pinch_started: bool


class PointerGestureRecognizer:
    """Recognize index-finger cursor positions and edge-triggered pinches.

    The thumb-index distance is normalized by the wrist-to-index-knuckle
    distance, making the threshold scale with the detected hand rather than
    depending on a fixed camera distance.
    """

    def __init__(
        self,
        close_ratio: float = _PINCH_CLOSE_RATIO,
        open_ratio: float = _PINCH_OPEN_RATIO,
    ) -> None:
        """Create a recognizer with hysteresis thresholds for pinch state.

        Args:
            close_ratio: Pinch ratio at or below which a pinch begins.
            open_ratio: Pinch ratio at or above which a pinch ends.

        Raises:
            ValueError: If ratios are invalid or do not provide hysteresis.
        """
        if close_ratio <= 0.0 or open_ratio <= close_ratio:
            raise ValueError("open_ratio must be greater than a positive close_ratio.")
        self._close_ratio = close_ratio
        self._open_ratio = open_ratio
        self._pinching = False

    def recognize(self, hand: HandObservation) -> PointerGesture:
        """Recognize pointer location and a new pinch from one hand.

        Args:
            hand: A hand observation containing MediaPipe's 21 landmarks.

        Returns:
            The normalized pointer location and whether a pinch started now.
        """
        index_tip = hand.landmark(HandLandmarkIndex.INDEX_FINGER_TIP)
        pinch_ratio = _pinch_ratio(hand)
        pinch_started = False
        if not self._pinching and pinch_ratio <= self._close_ratio:
            self._pinching = True
            pinch_started = True
        elif self._pinching and pinch_ratio >= self._open_ratio:
            self._pinching = False
        return PointerGesture(
            x=_clamp_normalized(index_tip.x),
            y=_clamp_normalized(index_tip.y),
            is_pinching=self._pinching,
            pinch_started=pinch_started,
        )

    def reset(self) -> None:
        """Clear gesture state when no hand is tracked."""
        self._pinching = False


class CursorMapper:
    """Map normalized gesture coordinates to smoothed screen coordinates."""

    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        smoothing: float = _DEFAULT_SMOOTHING,
    ) -> None:
        """Create a cursor mapper for one screen.

        Args:
            screen_width: Width of the target screen in pixels.
            screen_height: Height of the target screen in pixels.
            smoothing: Fraction of the gap to move each frame, in ``(0, 1]``.
                A higher value improves responsiveness while a lower value
                filters more camera jitter.

        Raises:
            ValueError: If screen dimensions or smoothing are invalid.
        """
        if screen_width <= 0 or screen_height <= 0:
            raise ValueError("screen dimensions must be positive.")
        if not 0.0 < smoothing <= 1.0:
            raise ValueError("smoothing must be in the range (0, 1].")
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._smoothing = smoothing
        self._position: tuple[float, float] | None = None

    def map(self, x: float, y: float) -> tuple[int, int]:
        """Transform a normalized point into a smoothed screen coordinate.

        Args:
            x: Normalized horizontal position.
            y: Normalized vertical position.

        Returns:
            A clamped ``(x, y)`` screen coordinate in pixels.
        """
        # The camera is presented as a selfie view, so invert its x axis to
        # make moving a hand left move the macOS cursor left.
        target_x = (1.0 - _clamp_normalized(x)) * (self._screen_width - 1)
        target_y = _clamp_normalized(y) * (self._screen_height - 1)
        if self._position is None:
            self._position = (target_x, target_y)
        else:
            old_x, old_y = self._position
            self._position = (
                old_x + self._smoothing * (target_x - old_x),
                old_y + self._smoothing * (target_y - old_y),
            )
        mapped_x, mapped_y = self._position
        return round(mapped_x), round(mapped_y)


def _pinch_ratio(hand: HandObservation) -> float:
    """Calculate thumb-index distance relative to the hand's reference size."""
    thumb_tip = hand.landmark(HandLandmarkIndex.THUMB_TIP)
    index_tip = hand.landmark(HandLandmarkIndex.INDEX_FINGER_TIP)
    wrist = hand.landmark(HandLandmarkIndex.WRIST)
    index_mcp = hand.landmark(HandLandmarkIndex.INDEX_FINGER_MCP)
    reference_distance = landmark_distance(wrist, index_mcp)
    if reference_distance == 0.0:
        return float("inf")
    return landmark_distance(thumb_tip, index_tip) / reference_distance


def _clamp_normalized(value: float) -> float:
    """Clamp one normalized coordinate to the visible range."""
    return min(max(value, 0.0), 1.0)
