"""Camera capture and hand-landmark detection.

This package wraps OpenCV (camera capture) and MediaPipe Tasks
(``HandLandmarker``) behind a small, OS-agnostic API. Nothing in this package
is allowed to depend on the host operating system or perform any input
injection -- it only ever *produces* landmark data for
:mod:`gesture_control.gestures` to consume.
"""
