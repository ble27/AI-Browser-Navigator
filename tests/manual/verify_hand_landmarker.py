"""Camera-free smoke test for the MediaPipe HandLandmarker integration.

This is deliberately *not* a pytest unit test: it downloads a real MediaPipe
sample image and runs the actual HandLandmarker model against it, which is
exactly the kind of real-inference check that caught the mediapipe==1.0.1
crash documented in docs/KNOWN_ISSUES.md. Unlike that crash, this script
needs no camera, so it's cheap to rerun whenever the `mediapipe` pin changes
or before trusting `--debug` in a new environment.

Usage:
    python tests/manual/verify_hand_landmarker.py
    python tests/manual/verify_hand_landmarker.py --overlay-out /tmp/overlay.jpg

Exit code is 0 if at least one hand was detected, 1 otherwise. A native
crash (e.g. the known mediapipe graph-service bug) will abort the process
with a non-Python traceback -- that itself is diagnostic information.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

import cv2
from gesture_control.vision.geometry import HandLandmarkIndex
from gesture_control.vision.hand_landmarker import HandLandmarkerService
from gesture_control.vision.overlay import draw_hand_landmarks

# A MediaPipe-hosted sample image with two clearly visible hands, used in
# MediaPipe's own documentation/colabs.
_SAMPLE_IMAGE_URL = "https://storage.googleapis.com/mediapipe-assets/woman_hands.jpg"
_CACHE_PATH = Path(__file__).resolve().parent / "_cache" / "woman_hands.jpg"


def _ensure_sample_image() -> Path:
    """Download the sample test image once, caching it alongside this script.

    Returns:
        Path to the cached sample image.
    """
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _CACHE_PATH.exists():
        print(f"Downloading sample image from {_SAMPLE_IMAGE_URL} ...")
        urllib.request.urlretrieve(_SAMPLE_IMAGE_URL, _CACHE_PATH)  # noqa: S310
    return _CACHE_PATH


def main(argv: list[str] | None = None) -> int:
    """Run the smoke test.

    Args:
        argv: Command-line arguments, excluding the program name.

    Returns:
        ``0`` if at least one hand was detected, ``1`` otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--overlay-out",
        type=Path,
        default=None,
        help="If set, write the detected skeleton overlay to this image path.",
    )
    args = parser.parse_args(argv)

    image_path = _ensure_sample_image()
    frame = cv2.imread(str(image_path))
    if frame is None:
        print(f"error: could not read {image_path}", file=sys.stderr)
        return 1
    print(f"Loaded sample image: {frame.shape}")

    with HandLandmarkerService(num_hands=2) as landmarker:
        hands = landmarker.detect(frame)

    print(f"Detected {len(hands)} hand(s):")
    for hand in hands:
        tip = hand.landmark(HandLandmarkIndex.INDEX_FINGER_TIP)
        print(
            f"  {hand.handedness} (confidence={hand.score:.2f}) "
            f"index_fingertip=({tip.x:.3f}, {tip.y:.3f})"
        )

    if args.overlay_out is not None:
        draw_hand_landmarks(frame, hands)
        cv2.imwrite(str(args.overlay_out), frame)
        print(f"Wrote overlay image to {args.overlay_out}")

    if not hands:
        print("error: expected at least one hand in the sample image", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
