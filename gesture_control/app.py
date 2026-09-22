"""Command-line entrypoint for the gesture control application.

Milestone status: M1 (camera + hand-landmark pipeline) is implemented behind
``--debug``, which opens a live window overlaying detected hand landmarks on
the webcam feed. Turning detected landmarks into actual cursor/keyboard
control is added in M2 (see ``docs/PRD.md`` milestones).
"""

from __future__ import annotations

import argparse
import sys

import cv2

from gesture_control import __version__
from gesture_control.vision.camera import Camera, CameraUnavailableError
from gesture_control.vision.hand_landmarker import HandLandmarkerService
from gesture_control.vision.overlay import draw_hand_landmarks

_DEBUG_WINDOW_TITLE = "gesture-control debug (press 'q' to quit)"
_QUIT_KEY = ord("q")


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
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def run_debug_overlay(camera_index: int = 0) -> int:
    """Run a live debug window showing the camera feed with hand-landmark overlays.

    Opens the requested camera and the MediaPipe HandLandmarker model (which
    triggers a one-time download on first run; see
    :func:`gesture_control.vision.model_download.ensure_hand_landmarker_model`),
    then loops: read a frame, detect hands, draw the overlay, display it.
    Press 'q' in the debug window to exit.

    Args:
        camera_index: OS camera device index to open.

    Returns:
        A process exit code (``0`` on a clean exit, ``1`` if the camera
        could not be used).
    """
    try:
        with (
            Camera(device_index=camera_index) as camera,
            HandLandmarkerService() as landmarker,
        ):
            print(f"Debug window open ('{_DEBUG_WINDOW_TITLE}'). Press 'q' to quit.")
            while True:
                frame = camera.read_frame()
                hands = landmarker.detect(frame)
                draw_hand_landmarks(frame, hands)
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

    if args.debug:
        return run_debug_overlay(camera_index=args.camera_index)

    print(f"gesture-control {__version__} -- see README.md to get started.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
