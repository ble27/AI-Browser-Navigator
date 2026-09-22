"""Command-line entrypoint for the gesture control application.

Milestone status: M2 adds opt-in macOS cursor movement and pinch clicking to
the M1 camera and hand-landmark debug overlay.
"""

from __future__ import annotations

import argparse
import sys
from contextlib import ExitStack

import cv2

from gesture_control import __version__
from gesture_control.actions import ActionMapper, Intent, IntentType
from gesture_control.backends.macos import MacOSInputBackend, SafePauseHotkey
from gesture_control.gestures.cursor import CursorMapper, PointerGestureRecognizer
from gesture_control.vision.camera import Camera, CameraUnavailableError
from gesture_control.vision.geometry import HandObservation
from gesture_control.vision.hand_landmarker import HandLandmarkerService
from gesture_control.vision.overlay import draw_hand_landmarks

_DEBUG_WINDOW_TITLE = "gesture-control debug (press 'q' to quit)"
_QUIT_KEY = ord("q")
_CONTROL_CAPTURE_WIDTH = 640
_CONTROL_CAPTURE_HEIGHT = 480


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the top-level command-line argument parser.

    Returns:
        A configured :class:`argparse.ArgumentParser` for the application.
    """
    parser = argparse.ArgumentParser(
        prog="gesture-control",
        description="Control your computer with hand gestures and voice.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show a debug window with the camera feed and hand landmark overlay.",
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=0,
        help="OS camera device index to open (default: 0, the default webcam).",
    )
    parser.add_argument(
        "--control",
        action="store_true",
        help=(
            "Enable macOS cursor movement and pinch-click input. Requires --debug; "
            "press Ctrl+Option+Command+P at any time to pause or resume input."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def run_debug_overlay(camera_index: int = 0, control: bool = False) -> int:
    """Run a live debug window showing the camera feed with hand-landmark overlays.

    Opens the requested camera and the MediaPipe HandLandmarker model (which
    triggers a one-time download on first run; see
    :func:`gesture_control.vision.model_download.ensure_hand_landmarker_model`),
    then loops: read a frame, detect hands, draw the overlay, display it.
    Press 'q' in the debug window to exit.

    Args:
        camera_index: OS camera device index to open.
        control: Whether to enable M2 cursor movement and pinch clicking.

    Returns:
        A process exit code (``0`` on a clean exit, ``1`` if the camera
        could not be used).
    """
    try:
        with ExitStack() as stack:
            camera = stack.enter_context(
                Camera(
                    device_index=camera_index,
                    width=_CONTROL_CAPTURE_WIDTH if control else None,
                    height=_CONTROL_CAPTURE_HEIGHT if control else None,
                )
            )
            landmarker = stack.enter_context(HandLandmarkerService(num_hands=1 if control else 2))
            action_mapper: ActionMapper | None = None
            cursor_mapper: CursorMapper | None = None
            pointer_recognizer: PointerGestureRecognizer | None = None
            if control:
                backend = MacOSInputBackend()
                screen_width, screen_height = backend.screen_size()
                action_mapper = ActionMapper(backend)
                cursor_mapper = CursorMapper(screen_width, screen_height)
                pointer_recognizer = PointerGestureRecognizer()
                stack.enter_context(
                    SafePauseHotkey(
                        backend.safe_pause,
                        on_toggle=lambda paused: print(
                            f"Input {'paused' if paused else 'resumed'} " "(Ctrl+Option+Command+P)."
                        ),
                    )
                )
                print("Input enabled. Press Ctrl+Option+Command+P to pause or resume.")
            print(f"Debug window open ('{_DEBUG_WINDOW_TITLE}'). Press 'q' to quit.")
            while True:
                frame = camera.read_frame()
                hands = landmarker.detect(frame)
                draw_hand_landmarks(frame, hands)
                if (
                    action_mapper is not None
                    and cursor_mapper is not None
                    and pointer_recognizer is not None
                ):
                    _dispatch_pointer_intents(
                        hands,
                        pointer_recognizer,
                        cursor_mapper,
                        action_mapper,
                    )
                cv2.imshow(_DEBUG_WINDOW_TITLE, frame)
                if cv2.waitKey(1) & 0xFF == _QUIT_KEY:
                    break
    except CameraUnavailableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        cv2.destroyAllWindows()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the gesture control application.

    Args:
        argv: Command-line arguments, excluding the program name. Defaults to
            ``sys.argv[1:]`` when ``None``.

    Returns:
        A process exit code (``0`` on success).
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.control and not args.debug:
        parser.error("--control requires --debug.")
    if args.control and sys.platform != "darwin":
        parser.error("--control is currently supported on macOS only.")
    if args.debug:
        return run_debug_overlay(camera_index=args.camera_index, control=args.control)

    print(f"gesture-control {__version__} -- see README.md to get started.")
    return 0


def _dispatch_pointer_intents(
    hands: list[HandObservation],
    pointer_recognizer: PointerGestureRecognizer,
    cursor_mapper: CursorMapper,
    action_mapper: ActionMapper,
) -> None:
    """Map the most confidently detected hand into M2 cursor intents.

    Args:
        hands: Hand observations from the current camera frame.
        pointer_recognizer: Stateful pinch recognizer.
        cursor_mapper: Stateful cursor smoothing mapper.
        action_mapper: Shared intent dispatch boundary.
    """
    if not hands:
        pointer_recognizer.reset()
        return
    selected_hand = max(hands, key=lambda hand: hand.score)
    pointer = pointer_recognizer.recognize(selected_hand)
    x, y = cursor_mapper.map(pointer.x, pointer.y)
    action_mapper.dispatch(Intent(IntentType.MOVE_CURSOR, x=x, y=y))
    if pointer.pinch_started:
        action_mapper.dispatch(Intent(IntentType.CLICK_LEFT))


if __name__ == "__main__":
    raise SystemExit(main())
