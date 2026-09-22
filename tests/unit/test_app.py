"""Tests for the command-line entrypoint (:mod:`gesture_control.app`).

These tests stay hardware-free by monkeypatching the camera/landmarker
boundary rather than opening a real webcam -- see ``tests/manual`` and
``docs/QA_CHECKLISTS.md`` for the manual, hardware-in-the-loop verification
of ``--debug`` itself.
"""

from __future__ import annotations

import pytest
from gesture_control import app
from gesture_control.app import build_arg_parser, main
from gesture_control.vision.camera import CameraUnavailableError


def test_build_arg_parser_defaults() -> None:
    """``--debug`` and ``--camera-index`` should have sensible defaults."""
    parser = build_arg_parser()
    args = parser.parse_args([])
    assert args.debug is False
    assert args.camera_index == 0


def test_build_arg_parser_accepts_debug_flag() -> None:
    """The ``--debug`` flag should be recognized when supplied."""
    parser = build_arg_parser()
    args = parser.parse_args(["--debug"])
    assert args.debug is True


def test_build_arg_parser_accepts_camera_index() -> None:
    """``--camera-index`` should accept an integer device index."""
    parser = build_arg_parser()
    args = parser.parse_args(["--camera-index", "2"])
    assert args.camera_index == 2


def test_build_arg_parser_accepts_control_flag() -> None:
    """``--control`` should require explicit user opt-in."""
    parser = build_arg_parser()
    args = parser.parse_args(["--debug", "--control"])
    assert args.control is True


def test_main_returns_zero_without_arguments() -> None:
    """Running with no arguments should succeed and print a startup message."""
    exit_code = main([])
    assert exit_code == 0


def test_main_dispatches_to_run_debug_overlay_when_debug_flag_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--debug`` should call run_debug_overlay with the requested camera index."""
    received_camera_index: list[int] = []

    def fake_run_debug_overlay(camera_index: int = 0, control: bool = False) -> int:
        received_camera_index.append(camera_index)
        assert control is False
        return 0

    monkeypatch.setattr(app, "run_debug_overlay", fake_run_debug_overlay)

    exit_code = main(["--debug", "--camera-index", "3"])

    assert exit_code == 0
    assert received_camera_index == [3]


def test_main_rejects_control_without_debug() -> None:
    """Input injection must only be enabled within the visible debug runtime."""
    with pytest.raises(SystemExit, match="2"):
        main(["--control"])


def test_run_debug_overlay_returns_one_when_camera_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing/unusable camera should be reported as a clean failure, not a crash."""

    class _FakeUnavailableCamera:
        def __init__(
            self,
            device_index: int = 0,
            width: int | None = None,
            height: int | None = None,
        ) -> None:
            del device_index, width, height

        def __enter__(self) -> _FakeUnavailableCamera:
            raise CameraUnavailableError("no camera in this test environment")

        def __exit__(self, *exc_info: object) -> None:
            return None

    monkeypatch.setattr(app, "Camera", _FakeUnavailableCamera)

    exit_code = app.run_debug_overlay(camera_index=0)

    assert exit_code == 1
