"""OpenCV webcam capture, wrapped as a small context-managed class.

This is the only module allowed to touch ``cv2.VideoCapture`` directly, so
camera lifecycle bugs (forgotten ``.release()`` calls, etc.) have exactly one
place to be found and fixed.
"""

from __future__ import annotations

import platform
import threading
import time
from types import TracebackType

import cv2
import numpy as np

_MAX_CONSECUTIVE_BLACK_FRAMES = 30
_BLACK_FRAME_MAX_PIXEL_VALUE = 2
_LATEST_FRAME_TIMEOUT_S = 2.0
# Asked only when a reader thread is dropping stale frames. A higher capture
# rate means the newest image is younger when inference is slower than the
# camera; drivers that ignore the request keep their default rate.
_REQUESTED_CAPTURE_FPS = 60.0


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
        drop_stale_frames: When ``True``, a background reader keeps only the
            newest frame. Landmark inference is often slower than the camera,
            and OpenCV's capture queue would otherwise hand detection an image
            that is already tens or hundreds of milliseconds old.
        stabilize_exposure: When ``True``, best-effort disable auto-exposure
            and auto-focus. Brightness hunting mid-gesture shifts landmark
            positions and reads as cursor jitter; drivers that ignore these
            requests keep their defaults.
    """

    def __init__(
        self,
        device_index: int = 0,
        width: int | None = None,
        height: int | None = None,
        drop_stale_frames: bool = False,
        stabilize_exposure: bool = False,
    ) -> None:
        """Store the requested camera configuration without opening the device yet."""
        self._device_index = device_index
        self._width = width
        self._height = height
        self._drop_stale_frames = drop_stale_frames
        self._stabilize_exposure = stabilize_exposure
        self._capture: cv2.VideoCapture | None = None
        self._consecutive_black_frames = 0
        self._frame_lock = threading.Lock()
        self._stop_reading = threading.Event()
        self._reader_thread: threading.Thread | None = None
        self._latest_frame: np.ndarray | None = None
        self._reader_error: CameraUnavailableError | None = None

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
        # A one-frame driver queue is the best effort before the reader thread.
        # Several backends ignore it, which is why ``drop_stale_frames`` exists.
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if self._drop_stale_frames:
            capture.set(cv2.CAP_PROP_FPS, _REQUESTED_CAPTURE_FPS)
        if self._stabilize_exposure:
            _request_stable_exposure(capture)
        self._capture = capture
        if self._drop_stale_frames:
            self._stop_reading.clear()
            self._reader_thread = threading.Thread(
                target=self._read_latest_loop,
                name="gesture-control-camera",
                daemon=True,
            )
            self._reader_thread.start()
        return self

    def read_frame(self) -> np.ndarray:
        """Read a single BGR frame from the camera.

        Returns:
            An ``(height, width, 3)`` BGR ``numpy.ndarray``. When
            ``drop_stale_frames`` is enabled, this is a copy of the newest
            frame the reader has captured, never an older queued one.

        Raises:
            RuntimeError: If called before :meth:`open`.
            CameraUnavailableError: If a frame could not be read (e.g. the
                camera was disconnected mid-stream).
        """
        if self._capture is None and self._reader_thread is None:
            raise RuntimeError(
                "Camera.read_frame() called before open(); use "
                "`with Camera(...) as camera:` or call `.open()` first."
            )
        if self._drop_stale_frames:
            return self._take_latest_frame()
        return self._read_from_capture()

    def close(self) -> None:
        """Release the underlying camera device, if open. Safe to call twice."""
        self._stop_reading.set()
        # Releasing the device unblocks a reader stuck inside ``VideoCapture.read``.
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=_LATEST_FRAME_TIMEOUT_S)
            self._reader_thread = None
        with self._frame_lock:
            self._latest_frame = None
            self._reader_error = None
        self._consecutive_black_frames = 0

    def _read_latest_loop(self) -> None:
        """Keep overwriting the shared slot so callers never see a queued frame."""
        while not self._stop_reading.is_set():
            try:
                frame = self._read_from_capture().copy()
            except CameraUnavailableError as exc:
                with self._frame_lock:
                    self._reader_error = exc
                return
            with self._frame_lock:
                self._latest_frame = frame

    def _take_latest_frame(self) -> np.ndarray:
        """Return the newest captured frame, waiting briefly for the first one."""
        deadline = time.monotonic() + _LATEST_FRAME_TIMEOUT_S
        while time.monotonic() < deadline:
            with self._frame_lock:
                frame = self._latest_frame
                self._latest_frame = None
                error = self._reader_error
            if frame is not None:
                return frame
            if error is not None:
                raise error
            time.sleep(0.001)
        raise CameraUnavailableError(
            "Timed out waiting for a camera frame. The camera may be disconnected "
            "or held by another application."
        )

    def _read_from_capture(self) -> np.ndarray:
        """Read one frame from the open device and apply the black-frame guard."""
        if self._capture is None:
            raise CameraUnavailableError(
                "Failed to read a frame from the camera; it may have been "
                "disconnected or released by another process."
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


def _request_stable_exposure(capture: cv2.VideoCapture) -> None:
    """Best-effort lock of exposure and focus for steadier landmarks.

    OpenCV property semantics differ by backend: ``CAP_PROP_AUTO_EXPOSURE`` is
    ``0.25`` for manual on some V4L2 devices and ``0``/``1`` elsewhere, so both
    common "manual" encodings are attempted. Failures are ignored — a camera
    that rejects the request simply keeps auto mode.
    """
    capture.set(cv2.CAP_PROP_AUTOFOCUS, 0)
    capture.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
    capture.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0)
