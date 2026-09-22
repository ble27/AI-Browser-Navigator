"""Pure gesture recognition and cursor-coordinate smoothing for M2.

This module deliberately has no dependency on OpenCV, MediaPipe, or an input
backend. It turns a detected hand into normalized pointer and pinch events
that can be tested with synthetic landmarks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from gesture_control.gestures.smoothing import OneEuroFilter
from gesture_control.vision.geometry import HandLandmarkIndex, HandObservation, landmark_distance

_PINCH_CLOSE_RATIO = 0.35
_PINCH_OPEN_RATIO = 0.45
# The fingertip landmark is the noisiest point on the hand. Blending a little
# of the distal joint (one landmark back) cuts that noise before it is
# multiplied by the screen size, without moving the pointer off the fingertip.
_TIP_BLEND = 0.85
# 1€ tuning is in screen pixels. At rest the cutoff stays low enough that a
# few pixels of landmark noise never become cursor motion. Beta opens the
# filter once the fingertip is actually moving, so a swipe is not lagged by
# the same smoothing that holds a still hand.
_DEFAULT_MIN_CUTOFF_HZ = 1.2
_DEFAULT_BETA = 0.025
_DEFAULT_DERIVATIVE_CUTOFF_HZ = 1.0
_DEFAULT_EDGE_MARGIN = 0.12
# Resting landmark noise converges a few pixels and then reverses direction.
# Hold the cursor until the filtered point leaves this radius so that noise
# cannot step the pointer. A real movement is monotonic, so once it escapes
# the radius the pointer follows every sample until it comes to rest.
_STILL_RADIUS_PX = 14.0
_CRAWL_SPEED_PX_S = 30.0
_SETTLE_SPEED_PX_S = 90.0
# Predict forward by a fraction of the pipeline delay, but never past the
# measured fingertip. That closes the visible gap during a swipe without
# the overshoot that reads as jitter.
_LEAD_SECONDS = 0.04
_LEAD_MIN_SPEED_PX_S = 220.0


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
        index_dip = hand.landmark(HandLandmarkIndex.INDEX_FINGER_DIP)
        pinch_ratio = _pinch_ratio(hand)
        pinch_started = False
        if not self._pinching and pinch_ratio <= self._close_ratio:
            self._pinching = True
            pinch_started = True
        elif self._pinching and pinch_ratio >= self._open_ratio:
            self._pinching = False
        return PointerGesture(
            x=_clamp_normalized(_TIP_BLEND * index_tip.x + (1.0 - _TIP_BLEND) * index_dip.x),
            y=_clamp_normalized(_TIP_BLEND * index_tip.y + (1.0 - _TIP_BLEND) * index_dip.y),
            is_pinching=self._pinching,
            pinch_started=pinch_started,
        )

    def reset(self) -> None:
        """Clear gesture state when no hand is tracked."""
        self._pinching = False


class CursorMapper:
    """Map normalized gesture coordinates to a low-latency screen position."""

    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        min_cutoff_hz: float = _DEFAULT_MIN_CUTOFF_HZ,
        beta: float = _DEFAULT_BETA,
        derivative_cutoff_hz: float = _DEFAULT_DERIVATIVE_CUTOFF_HZ,
        edge_margin: float = _DEFAULT_EDGE_MARGIN,
    ) -> None:
        """Create a cursor mapper for one screen.

        Args:
            screen_width: Width of the target screen in pixels.
            screen_height: Height of the target screen in pixels.
            min_cutoff_hz: 1€ cutoff while the fingertip is still.
            beta: Extra cutoff added per pixel/second of fingertip speed.
            derivative_cutoff_hz: Cutoff of the speed estimate.
            edge_margin: Normalized inset of the camera region that maps onto
                the full screen, in ``[0, 0.5)``. ``0`` uses the whole frame.

        Raises:
            ValueError: If screen dimensions or filter settings are invalid.
        """
        if screen_width <= 0 or screen_height <= 0:
            raise ValueError("screen dimensions must be positive.")
        if not 0.0 <= edge_margin < 0.5:
            raise ValueError("edge_margin must be in the range [0, 0.5).")
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._edge_margin = edge_margin
        self._x_filter = OneEuroFilter(min_cutoff_hz, beta, derivative_cutoff_hz)
        self._y_filter = OneEuroFilter(min_cutoff_hz, beta, derivative_cutoff_hz)
        self._anchor: tuple[float, float] | None = None
        self._last_velocity = (0.0, 0.0)
        self._settled = True

    def map(self, x: float, y: float, timestamp_s: float) -> tuple[int, int]:
        """Transform a normalized point into a screen coordinate.

        Args:
            x: Normalized horizontal position in camera space.
            y: Normalized vertical position in camera space.
            timestamp_s: Sample time in seconds, from a monotonic clock.

        Returns:
            A clamped ``(x, y)`` screen coordinate in pixels.
        """
        active_x = _expand_active_region(x, self._edge_margin)
        active_y = _expand_active_region(y, self._edge_margin)
        # The camera is presented as a selfie view, so invert its x axis to
        # make moving a hand left move the macOS cursor left.
        target_x = (1.0 - active_x) * (self._screen_width - 1)
        target_y = active_y * (self._screen_height - 1)
        filtered_x, velocity_x = self._x_filter.filter(target_x, timestamp_s)
        filtered_y, velocity_y = self._y_filter.filter(target_y, timestamp_s)
        predicted_x = _lead_toward_target(filtered_x, target_x, velocity_x)
        predicted_y = _lead_toward_target(filtered_y, target_y, velocity_y)
        predicted_x = _clamp_screen(predicted_x, self._screen_width)
        predicted_y = _clamp_screen(predicted_y, self._screen_height)
        return self._stabilize(predicted_x, predicted_y, velocity_x, velocity_y)

    def _stabilize(
        self,
        predicted_x: float,
        predicted_y: float,
        velocity_x: float,
        velocity_y: float,
    ) -> tuple[int, int]:
        """Hold a resting pointer, then follow once motion is clearly real."""
        if self._anchor is None:
            self._anchor = (predicted_x, predicted_y)
            self._last_velocity = (velocity_x, velocity_y)
            return round(predicted_x), round(predicted_y)

        anchor_x, anchor_y = self._anchor
        distance = math.hypot(predicted_x - anchor_x, predicted_y - anchor_y)
        speed = math.hypot(velocity_x, velocity_y)
        reversing = velocity_x * self._last_velocity[0] + velocity_y * self._last_velocity[1] < 0.0
        self._last_velocity = (velocity_x, velocity_y)

        if self._settled and distance <= _STILL_RADIUS_PX:
            return round(anchor_x), round(anchor_y)

        # A stopped hand produces a small, often reversing speed. A slow
        # deliberate drift does not reverse, so it keeps updating.
        if speed < _CRAWL_SPEED_PX_S or (speed < _SETTLE_SPEED_PX_S and reversing):
            self._settled = True
            self._anchor = (predicted_x, predicted_y)
            return round(predicted_x), round(predicted_y)

        self._settled = False
        self._anchor = (predicted_x, predicted_y)
        return round(predicted_x), round(predicted_y)


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


def _expand_active_region(value: float, margin: float) -> float:
    """Map the central camera region onto the full normalized range.

    Reaching the literal edge of the webcam image is an awkward pose and is
    where the hand is most likely to leave the frame. Insetting that region
    lets the pointer reach a screen edge while the fingertip stays inside
    the image. Coordinates outside the region clamp to the screen edge.
    """
    if margin == 0.0:
        return _clamp_normalized(value)
    span = 1.0 - 2.0 * margin
    return _clamp_normalized((value - margin) / span)


def _lead_toward_target(filtered: float, target: float, velocity: float) -> float:
    """Advance a lagged filtered position toward the measured target."""
    if abs(velocity) < _LEAD_MIN_SPEED_PX_S:
        return filtered
    predicted = filtered + velocity * _LEAD_SECONDS
    if target >= filtered:
        return min(predicted, target)
    return max(predicted, target)


def _clamp_screen(value: float, size: int) -> float:
    """Clamp one screen coordinate to the display."""
    return min(max(value, 0.0), float(size - 1))


def _clamp_normalized(value: float) -> float:
    """Clamp one normalized coordinate to the visible range."""
    return min(max(value, 0.0), 1.0)
