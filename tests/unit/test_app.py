"""Tests for the command-line entrypoint (:mod:`gesture_control.app`).

These tests stay hardware-free by monkeypatching the camera/landmarker
boundary rather than opening a real webcam -- see ``tests/manual`` and
``docs/QA_CHECKLISTS.md`` for the manual, hardware-in-the-loop verification
of ``--debug`` itself.
"""

from __future__ import annotations

import pytest
from gesture_control import app
from gesture_control.actions import Intent, IntentType
from gesture_control.app import build_arg_parser, main
from gesture_control.backends.base import BrowserAction, InputBackend
from gesture_control.vision.camera import CameraUnavailableError
from gesture_control.vision.geometry import HandLandmarkIndex, HandObservation, Landmark


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


class _RecordingActionMapper:
    """Collect dispatched intents without injecting any operating-system input."""

    def __init__(self) -> None:
        self.intents: list[Intent] = []

    def dispatch(self, intent: Intent) -> None:
        """Record one intent."""
        self.intents.append(intent)


def _hand(index_tip: Landmark, thumb_tip: Landmark) -> HandObservation:
    """Build a hand observation with a unit-sized pinch reference."""
    landmarks = [Landmark(0.2, 0.2, 0.0) for _ in range(21)]
    landmarks[HandLandmarkIndex.WRIST] = Landmark(0.0, 0.0, 0.0)
    landmarks[HandLandmarkIndex.INDEX_FINGER_MCP] = Landmark(1.0, 0.0, 0.0)
    landmarks[HandLandmarkIndex.INDEX_FINGER_TIP] = index_tip
    landmarks[HandLandmarkIndex.THUMB_TIP] = thumb_tip
    return HandObservation(tuple(landmarks), "Right", 0.99)


def test_pointer_dispatch_freezes_cursor_for_the_duration_of_a_pinch() -> None:
    """Pinching should click the established target without jittering away from it."""
    action_mapper = _RecordingActionMapper()
    recognizer = app.PointerGestureRecognizer()
    cursor_mapper = app.CursorMapper(101, 101, edge_margin=0.0)
    open_hand = _hand(Landmark(0.8, 0.5, 0.0), Landmark(0.0, 0.5, 0.0))
    pinched_hand = _hand(Landmark(0.2, 0.5, 0.0), Landmark(0.15, 0.5, 0.0))

    presence = app.HandPresenceHold()
    app._dispatch_pointer_intents(
        [open_hand], recognizer, cursor_mapper, action_mapper, presence, timestamp_s=0.0
    )
    app._dispatch_pointer_intents(
        [pinched_hand], recognizer, cursor_mapper, action_mapper, presence, timestamp_s=0.1
    )
    app._dispatch_pointer_intents(
        [pinched_hand], recognizer, cursor_mapper, action_mapper, presence, timestamp_s=0.2
    )

    assert [intent.kind for intent in action_mapper.intents] == [
        IntentType.MOVE_CURSOR,
        IntentType.CLICK_LEFT,
    ]


def test_pointer_dispatch_bridges_a_single_missed_frame() -> None:
    """One empty detection must not drop the pointer or arm a second click."""
    action_mapper = _RecordingActionMapper()
    recognizer = app.PointerGestureRecognizer()
    cursor_mapper = app.CursorMapper(101, 101, edge_margin=0.0)
    presence = app.HandPresenceHold(hold_s=0.12)
    open_hand = _hand(Landmark(0.8, 0.5, 0.0), Landmark(0.0, 0.5, 0.0))
    pinched_hand = _hand(Landmark(0.2, 0.5, 0.0), Landmark(0.15, 0.5, 0.0))

    app._dispatch_pointer_intents(
        [open_hand], recognizer, cursor_mapper, action_mapper, presence, timestamp_s=0.0
    )
    app._dispatch_pointer_intents(
        [pinched_hand], recognizer, cursor_mapper, action_mapper, presence, timestamp_s=0.05
    )
    app._dispatch_pointer_intents(
        [], recognizer, cursor_mapper, action_mapper, presence, timestamp_s=0.10
    )
    app._dispatch_pointer_intents(
        [pinched_hand], recognizer, cursor_mapper, action_mapper, presence, timestamp_s=0.16
    )

    assert [intent.kind for intent in action_mapper.intents] == [
        IntentType.MOVE_CURSOR,
        IntentType.CLICK_LEFT,
    ]


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
            drop_stale_frames: bool = False,
        ) -> None:
            del device_index, width, height, drop_stale_frames

        def __enter__(self) -> _FakeUnavailableCamera:
            raise CameraUnavailableError("no camera in this test environment")

        def __exit__(self, *exc_info: object) -> None:
            return None

    monkeypatch.setattr(app, "Camera", _FakeUnavailableCamera)

    exit_code = app.run_debug_overlay(camera_index=0)

    assert exit_code == 1


def test_build_arg_parser_accepts_command() -> None:
    """``--command`` should accept a phrase and default to ``None`` when omitted."""
    parser = build_arg_parser()

    assert parser.parse_args(["--command", "open cursor webpage"]).command == (
        "open cursor webpage"
    )
    assert parser.parse_args([]).command is None


def test_main_command_opens_cursor_in_the_injected_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--command`` should open a parsed URL through the injected backend."""
    opened_urls: list[str] = []

    class _RecordingBackend(InputBackend):
        """Record open_url calls without launching Chrome or a camera."""

        def screen_size(self) -> tuple[int, int]:
            return 100, 100

        def move_to(self, x: int, y: int) -> None:
            del x, y

        def click_left(self) -> None:
            return None

        def open_url(self, url: str) -> None:
            opened_urls.append(url)

        def navigate_browser(self, action: BrowserAction) -> None:
            del action

        def click_element(self, target_id: str) -> None:
            del target_id

        def type_text(self, target_id: str, text: str) -> None:
            del target_id, text

    def _fail_overlay(*args: object, **kwargs: object) -> int:
        raise AssertionError("run_debug_overlay must not start for --command")

    monkeypatch.setattr(app, "MacOSInputBackend", _RecordingBackend)
    monkeypatch.setattr(app, "run_debug_overlay", _fail_overlay)
    monkeypatch.setattr(app.sys, "platform", "darwin")

    exit_code = main(["--command", "open cursor webpage"])

    assert exit_code == 0
    assert opened_urls == ["https://cursor.com"]


def test_main_command_dispatches_browser_navigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--command`` should route navigation through the shared mapper."""
    browser_actions: list[BrowserAction] = []

    class _RecordingBackend(InputBackend):
        """Record browser navigation without injecting keyboard input."""

        def screen_size(self) -> tuple[int, int]:
            return 100, 100

        def move_to(self, x: int, y: int) -> None:
            del x, y

        def click_left(self) -> None:
            return None

        def open_url(self, url: str) -> None:
            del url

        def navigate_browser(self, action: BrowserAction) -> None:
            browser_actions.append(action)

        def click_element(self, target_id: str) -> None:
            del target_id

        def type_text(self, target_id: str, text: str) -> None:
            del target_id, text

    monkeypatch.setattr(app, "MacOSInputBackend", _RecordingBackend)
    monkeypatch.setattr(app.sys, "platform", "darwin")

    exit_code = main(["--command", "next tab"])

    assert exit_code == 0
    assert browser_actions == [BrowserAction.NEXT_TAB]


def test_main_command_unknown_phrase_opens_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unrecognized ``--command`` phrase must exit non-zero without opening."""
    opened_urls: list[str] = []

    class _RecordingBackend(InputBackend):
        """Record open_url calls without launching Chrome or a camera."""

        def screen_size(self) -> tuple[int, int]:
            return 100, 100

        def move_to(self, x: int, y: int) -> None:
            del x, y

        def click_left(self) -> None:
            return None

        def open_url(self, url: str) -> None:
            opened_urls.append(url)

        def navigate_browser(self, action: BrowserAction) -> None:
            del action

        def click_element(self, target_id: str) -> None:
            del target_id

        def type_text(self, target_id: str, text: str) -> None:
            del target_id, text

    def _fail_overlay(*args: object, **kwargs: object) -> int:
        raise AssertionError("run_debug_overlay must not start for --command")

    monkeypatch.setattr(app, "MacOSInputBackend", _RecordingBackend)
    monkeypatch.setattr(app, "run_debug_overlay", _fail_overlay)
    monkeypatch.setattr(app.sys, "platform", "darwin")

    exit_code = main(["--command", "open my bank"])

    assert exit_code == 1
    assert opened_urls == []
