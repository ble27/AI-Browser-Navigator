"""Tests for gesture_control.vision.camera.

``cv2.VideoCapture`` is monkeypatched with an in-memory fake so these tests
never require a real webcam -- see docs/QA_CHECKLISTS.md for the manual,
hardware-in-the-loop verification.
"""

from __future__ import annotations

import time
from typing import ClassVar

import cv2
import numpy as np
import pytest
from gesture_control.vision import camera as camera_module
from gesture_control.vision.camera import Camera, CameraUnavailableError


class _FakeVideoCapture:
    """A minimal stand-in for cv2.VideoCapture, configured via class attributes."""

    opens_successfully: ClassVar[bool] = True
    frames_to_return: ClassVar[list[np.ndarray | None]] = []

    def __init__(self, device_index: int, backend: int | None = None) -> None:
        self.device_index = device_index
        self.backend = backend
        self.released = False
        self.reads = 0
        self._frame_queue = list(self.frames_to_return)
        self.props: dict[int, float] = {}

    def isOpened(self) -> bool:  # noqa: N802 (mirrors cv2's camelCase API)
        return self.opens_successfully

    def set(self, prop_id: int, value: float) -> bool:  # noqa: N802
        self.props[prop_id] = value
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        self.reads += 1
        if not self._frame_queue:
            return False, None
        frame = self._frame_queue.pop(0)
        return (frame is not None), frame

    def release(self) -> None:
        self.released = True


@pytest.fixture(autouse=True)
def _reset_fake_capture_defaults() -> None:
    """Reset the fake's class-level config between tests to avoid leakage."""
    _FakeVideoCapture.opens_successfully = True
    _FakeVideoCapture.frames_to_return = []


def test_camera_open_raises_when_device_cannot_be_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A camera that fails to open should raise a clear, actionable error."""
    _FakeVideoCapture.opens_successfully = False
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", _FakeVideoCapture)

    with pytest.raises(CameraUnavailableError, match="Could not open camera"):
        Camera(device_index=0).open()


def test_camera_uses_avfoundation_on_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    """macOS cameras should use the native AVFoundation capture backend."""
    monkeypatch.setattr(camera_module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", _FakeVideoCapture)

    camera = Camera(device_index=2).open()

    assert isinstance(camera._capture, _FakeVideoCapture)
    assert camera._capture.device_index == 2
    assert camera._capture.backend == cv2.CAP_AVFOUNDATION
    camera.close()


def test_camera_read_frame_before_open_raises_runtime_error() -> None:
    """Calling read_frame() before open()/__enter__() is a programming error, not a hardware one."""
    camera = Camera(device_index=0)
    with pytest.raises(RuntimeError, match="before open"):
        camera.read_frame()


def test_camera_context_manager_opens_and_releases(monkeypatch: pytest.MonkeyPatch) -> None:
    """Using Camera as a context manager should open on enter and release on exit."""
    fake_frame = np.zeros((4, 4, 3), dtype=np.uint8)
    _FakeVideoCapture.frames_to_return = [fake_frame]
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", _FakeVideoCapture)

    with Camera(device_index=1) as camera:
        frame = camera.read_frame()
        assert frame is fake_frame
        underlying = camera._capture
        assert isinstance(underlying, _FakeVideoCapture)
        assert underlying.released is False

    assert underlying.released is True


def test_camera_read_frame_raises_when_read_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed frame read (e.g. camera disconnected) should raise CameraUnavailableError."""
    _FakeVideoCapture.frames_to_return = [None]
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", _FakeVideoCapture)

    with Camera(device_index=0) as camera:
        with pytest.raises(CameraUnavailableError, match="Failed to read a frame"):
            camera.read_frame()


def test_camera_read_frame_raises_after_persistently_black_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A black camera stream should produce actionable troubleshooting guidance."""
    black_frame = np.zeros((4, 4, 3), dtype=np.uint8)
    _FakeVideoCapture.frames_to_return = [black_frame] * 30
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", _FakeVideoCapture)

    with Camera(device_index=0) as camera:
        for _ in range(29):
            assert camera.read_frame() is black_frame
        with pytest.raises(CameraUnavailableError, match="returned only black frames"):
            camera.read_frame()


def test_camera_requests_a_one_frame_driver_buffer(monkeypatch: pytest.MonkeyPatch) -> None:
    """A deep capture queue is what makes the pointer trail the hand."""
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", _FakeVideoCapture)

    with Camera(device_index=0) as camera:
        underlying = camera._capture
        assert isinstance(underlying, _FakeVideoCapture)
        assert underlying.props[cv2.CAP_PROP_BUFFERSIZE] == 1


def test_drop_stale_frames_returns_the_newest_captured_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inference must see the latest image, not an earlier frame still in the queue."""
    _FakeVideoCapture.frames_to_return = [
        np.full((2, 2, 3), fill_value, dtype=np.uint8) for fill_value in (10, 20, 30)
    ]
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", _FakeVideoCapture)

    with Camera(device_index=0, drop_stale_frames=True) as camera:
        underlying = camera._capture
        assert isinstance(underlying, _FakeVideoCapture)
        assert underlying.props[cv2.CAP_PROP_FPS] == 60.0
        newest = _wait_for_pixel(camera, 30)

    assert int(newest[0, 0, 0]) == 30
    assert underlying.released is True


def _wait_for_pixel(camera: Camera, pixel_value: int) -> np.ndarray:
    """Read until the reader has published ``pixel_value`` or the device ends."""
    deadline = time.monotonic() + 2.0
    latest: np.ndarray | None = None
    while time.monotonic() < deadline:
        try:
            latest = camera.read_frame()
        except CameraUnavailableError:
            break
        if int(latest[0, 0, 0]) == pixel_value:
            return latest
    assert latest is not None
    return latest
