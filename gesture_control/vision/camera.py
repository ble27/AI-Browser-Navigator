"""OpenCV webcam capture, wrapped as a small context-managed class.

This is the only module allowed to touch ``cv2.VideoCapture`` directly, so
camera lifecycle bugs (forgotten ``.release()`` calls, etc.) have exactly one
place to be found and fixed.
"""

from __future__ import annotations

import platform
from types import TracebackType

import cv2
import numpy as np

_MAX_CONSECUTIVE_BLACK_FRAMES = 30
_BLACK_FRAME_MAX_PIXEL_VALUE = 2


class CameraUnavailableError(RuntimeError):
    """Raised when the requested camera device cannot be opened or read."""


class Camera:
    """Context-managed wrapper around ``cv2.VideoCapture``.

    Usage:
        with Camera(device_index=0) as camera:
            frame = camera.read_frame()

    Args:
        device_index: OS camera index to open (``0`` is typically the
            built-in/default webcam).
        width: Requested capture width in pixels. Best-effort: not all
            camera drivers honor this.
        height: Requested capture height in pixels. Best-effort.
    """

    def __init__(
        self,
        device_index: int = 0,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        """Store the requested camera configuration without opening the device yet."""
        self._device_index = device_index
        self._width = width
        self._height = height
        self._capture: cv2.VideoCapture | None = None
        self._consecutive_black_frames = 0

    def open(self) -> Camera:
        """Open the underlying camera device.

        Returns:
            ``self``, so this can be chained (``Camera(0).open()``) in
            addition to being used as a context manager.

        Raises:
            CameraUnavailableError: If the device cannot be opened -- e.g. no
                webcam is connected, another process holds it, or (on
                macOS) the app has not been granted Camera permission.
        """
        capture = _open_capture(self._device_index)
        if not capture.isOpened():
            capture.release()
            raise CameraUnavailableError(
                f"Could not open camera at index {self._device_index}. "
                "Check that a webcam is connected, not in use by another "
                "app, and that this application has camera permission "
                "(on macOS: System Settings > Privacy & Security > Camera)."
            )
        if self._width is not None:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        if self._height is not None:
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        self._capture = capture
        return self

    def read_frame(self) -> np.ndarray:
        """Read a single BGR frame from the camera.

        Returns:
            An ``(height, width, 3)`` BGR ``numpy.ndarray``.

        Raises:
            RuntimeError: If called before :meth:`open`.
            CameraUnavailableError: If a frame could not be read (e.g. the
                camera was disconnected mid-stream).
        """
        if self._capture is None:
            raise RuntimeError(
                "Camera.read_frame() called before open(); use "
                "`with Camera(...) as camera:` or call `.open()` first."
            )
        ok, frame = self._capture.read()
        if not ok or frame is None:
            raise CameraUnavailableError(
                "Failed to read a frame from the camera; it may have been "
                "disconnected or released by another process."
            )
        if int(frame.max()) <= _BLACK_FRAME_MAX_PIXEL_VALUE:
            self._consecutive_black_frames += 1
            if self._consecutive_black_frames >= _MAX_CONSECUTIVE_BLACK_FRAMES:
                raise CameraUnavailableError(
                    "The camera returned only black frames. Check that the camera lens is "
                    "uncovered, no other app is using it, and this terminal has Camera "
                    "permission (macOS: System Settings > Privacy & Security > Camera). "
                    "If you have multiple cameras, try --camera-index 1."
                )
        else:
            self._consecutive_black_frames = 0
        return frame

    def close(self) -> None:
        """Release the underlying camera device, if open. Safe to call twice."""
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self._consecutive_black_frames = 0

    def __enter__(self) -> Camera:
        """Open the camera on entering a ``with`` block. See :meth:`open`."""
        return self.open()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Release the camera on leaving a ``with`` block, even if an exception occurred."""
        self.close()


def _open_capture(device_index: int) -> cv2.VideoCapture:
    """Open a camera using the platform's most reliable backend.

    macOS's generic backend can open a camera but return a black stream. Prefer
    AVFoundation there, while retaining OpenCV's default backend as a fallback
    for devices unsupported by AVFoundation.

    Args:
        device_index: OS camera device index to open.

    Returns:
        An OpenCV capture object. The caller owns releasing it.
    """
    if platform.system() == "Darwin":
        capture = cv2.VideoCapture(device_index, cv2.CAP_AVFOUNDATION)
        if capture.isOpened():
            return capture
        capture.release()
    return cv2.VideoCapture(device_index)
