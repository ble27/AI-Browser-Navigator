"""Tests for gesture_control.vision.camera.

``cv2.VideoCapture`` is monkeypatched with an in-memory fake so these tests
never require a real webcam -- see docs/QA_CHECKLISTS.md for the manual,
hardware-in-the-loop verification.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pytest
from gesture_control.vision import camera as camera_module
from gesture_control.vision.camera import Camera, CameraUnavailableError


class _FakeVideoCapture:
    """A minimal stand-in for cv2.VideoCapture, configured via class attributes."""

    opens_successfully: ClassVar[bool] = True
    frames_to_return: ClassVar[list[np.ndarray | None]] = []

    def __init__(self, device_index: int) -> None:
        self.device_index = device_index
        self.released = False
        self._frame_queue = list(self.frames_to_return)
        self.props: dict[int, float] = {}

    def isOpened(self) -> bool:  # noqa: N802 (mirrors cv2's camelCase API)
        return self.opens_successfully

    def set(self, prop_id: int, value: float) -> bool:  # noqa: N802
        self.props[prop_id] = value
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
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
