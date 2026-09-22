"""Thin wrapper around MediaPipe Tasks' ``HandLandmarker``.

This is the only module allowed to import from ``mediapipe.tasks``. It
converts MediaPipe's native result objects into the plain dataclasses from
:mod:`gesture_control.vision.geometry`, so the rest of the codebase never has
to depend on MediaPipe's SDK types directly.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import TracebackType

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions

from gesture_control.vision.geometry import HandObservation, Landmark
from gesture_control.vision.model_download import ensure_hand_landmarker_model


class HandLandmarkerService:
    """Detects 21-point hand landmarks in a stream of video frames.

    Wraps MediaPipe's ``HandLandmarker`` task in ``VIDEO`` running mode
    (synchronous, monotonically-increasing timestamps) rather than
    ``LIVE_STREAM`` mode, since a synchronous call-and-get-result API is
    simpler to reason about and test than an async callback.

    Usage:
        with HandLandmarkerService() as landmarker:
            hands = landmarker.detect(frame_bgr)

    Args:
        model_path: Path to a ``hand_landmarker.task`` model bundle. If
            ``None``, the model is downloaded and cached automatically via
            :func:`ensure_hand_landmarker_model`.
        num_hands: Maximum number of hands to detect simultaneously.
        min_detection_confidence: Minimum confidence, in ``[0, 1]``, for the
            initial palm detection.
        min_presence_confidence: Minimum confidence that a hand is still
            present. Falling below this restarts palm detection, which is
            much slower than tracking and drops the pointer for that frame.
        min_tracking_confidence: Minimum confidence to keep tracking the
            previous hand instead of searching the whole frame again.
        use_gpu: Whether to request MediaPipe's GPU delegate. Defaults to
            ``False`` (CPU delegate) because GPU delegate backends differ
            per platform (Metal on macOS, OpenGL/Vulkan elsewhere) and are
            not reliably available in every environment (e.g. headless CI,
            some sandboxes) -- this crashed outright in local testing on
            macOS with no GPU service available. CPU is slower but is the
            one code path guaranteed to work identically everywhere.
    """

    def __init__(
        self,
        model_path: Path | None = None,
        num_hands: int = 2,
        min_detection_confidence: float = 0.5,
        min_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        use_gpu: bool = False,
    ) -> None:
        """Load the model bundle and initialize the underlying MediaPipe task graph."""
        resolved_model_path = model_path or ensure_hand_landmarker_model()
        delegate = BaseOptions.Delegate.GPU if use_gpu else BaseOptions.Delegate.CPU
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(resolved_model_path), delegate=delegate),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=num_hands,
            min_hand_detection_confidence=min_detection_confidence,
            min_hand_presence_confidence=min_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        # MediaPipe's VIDEO mode requires strictly increasing millisecond
        # timestamps; anchor to process start rather than wall-clock epoch
        # so values stay small and monotonic for the lifetime of the service.
        self._start_time = time.monotonic()
        self._last_timestamp_ms = -1

    def detect(self, frame_bgr: np.ndarray) -> list[HandObservation]:
        """Detect hands in a single BGR video frame.

        Args:
            frame_bgr: A ``(height, width, 3)`` BGR frame, as produced by
                :class:`gesture_control.vision.camera.Camera`.

        Returns:
            One :class:`HandObservation` per detected hand (possibly empty).
        """
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        timestamp_ms = int((time.monotonic() - self._start_time) * 1000)
        # Two detects in the same millisecond would violate VIDEO mode and
        # raise. Bump by one so a fast loop cannot stall the tracker.
        if timestamp_ms <= self._last_timestamp_ms:
            timestamp_ms = self._last_timestamp_ms + 1
        self._last_timestamp_ms = timestamp_ms
        result = self._landmarker.detect_for_video(mp_image, timestamp_ms)
        return _to_hand_observations(result)

    def close(self) -> None:
        """Release the underlying MediaPipe task graph. Safe to call twice."""
        self._landmarker.close()

    def __enter__(self) -> HandLandmarkerService:
        """Return self unchanged; the task graph is already initialized in ``__init__``."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the underlying MediaPipe task graph on leaving a ``with`` block."""
        self.close()


def _to_hand_observations(result: vision.HandLandmarkerResult) -> list[HandObservation]:
    """Convert a raw MediaPipe result into our plain :class:`HandObservation` list.

    Args:
        result: The result returned by ``HandLandmarker.detect_for_video``.

    Returns:
        A list of :class:`HandObservation`, one per detected hand, with
        MediaPipe's landmark/handedness objects converted to plain floats.
    """
    observations: list[HandObservation] = []
    for hand_landmarks, handedness in zip(result.hand_landmarks, result.handedness, strict=True):
        landmarks = tuple(Landmark(x=lm.x, y=lm.y, z=lm.z) for lm in hand_landmarks)
        top_category = handedness[0]
        observations.append(
            HandObservation(
                landmarks=landmarks,
                handedness=top_category.category_name,
                score=top_category.score,
            )
        )
    return observations
