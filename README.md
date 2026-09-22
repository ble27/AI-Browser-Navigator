# AI Vision Gesture Control Tool

Control your computer with hand gestures and offline voice commands — a
local-first, cross-platform (macOS/Windows/Linux) virtual mouse and navigation
tool built with Python, OpenCV, and MediaPipe, with accessibility as a
first-class use case.

> Status: M0 (scaffold), M1 (camera + hand-landmark debug overlay), and M2
> (macOS virtual mouse) are implemented and unit-tested. M2 awaits its final
> hardware verification pass.

- Full product requirements: [`docs/PRD.md`](docs/PRD.md)
- Contributor / AI-agent onboarding: [`AGENTS.md`](AGENTS.md)
- Manual QA checklists: [`docs/QA_CHECKLISTS.md`](docs/QA_CHECKLISTS.md)
- Deferred work / backlog: [`docs/BACKLOG.md`](docs/BACKLOG.md)
- Known issues / environment gotchas: [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md)

## Quickstart

```bash
git clone <repo-url>
cd AI-Gestures-Tool
./scripts/setup_env.sh
source .venv/bin/activate
python -m gesture_control.app --debug   # opens a webcam window with a hand-landmark overlay
```

The first `--debug` run downloads the MediaPipe HandLandmarker model
(~8 MB, cached under `models/`). If the download fails with an SSL error, or
the debug window crashes on launch, see
[`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md) before assuming your setup is
broken -- both a real, fixable gotcha and an unresolved
environment-specific crash are documented there.

Options:

```bash
python -m gesture_control.app --debug --camera-index 1   # use a non-default webcam
python -m gesture_control.app --debug --control           # enable macOS cursor + pinch click
python -m gesture_control.app --version
```

`--control` is explicit because it injects input. On macOS, grant the
launching terminal **Accessibility** permission in **System Settings > Privacy
& Security > Accessibility**. Move the index fingertip to move the pointer;
touch the thumb and index fingertips together once to click. Press
**Control+Option+Command+P** at any time to pause or resume all injected
input.

## Why one toolkit works across macOS/Windows/Linux

Only the input-injection layer (moving the cursor, sending clicks/keys) is
OS-specific; camera capture, hand-landmark detection, gesture recognition, and
voice processing are pure Python and run identically everywhere. See the
architecture diagram in [`docs/PRD.md`](docs/PRD.md#6-cross-platform-architecture).

## Gesture cheat-sheet

- Move index fingertip: move cursor.
- Thumb-index pinch: left-click.
- Control+Option+Command+P: pause/resume all injected input.

Double-click, right-click, drag, scrolling, fist pause, and navigation
gestures are scheduled for M3.

## Safety

A global safe-pause hotkey and a "fist" pause gesture always disable input
injection immediately. See [`docs/PRD.md`](docs/PRD.md#75-cross-cutting--safety).

## License

See [`LICENSE`](LICENSE) (added at M0).
