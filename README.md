# AI Vision Gesture Control Tool

Control your computer with hand gestures and offline voice commands — a
local-first, cross-platform (macOS/Windows/Linux) virtual mouse and navigation
tool built with Python, OpenCV, and MediaPipe, with accessibility as a
first-class use case.

> Status: pre-implementation. This README describes the target quickstart; it
> will be filled in with real, tested commands starting at milestone M0.

- Full product requirements: [`docs/PRD.md`](docs/PRD.md)
- Contributor / AI-agent onboarding: [`AGENTS.md`](AGENTS.md)
- Manual QA checklists: [`docs/QA_CHECKLISTS.md`](docs/QA_CHECKLISTS.md)
- Deferred work / backlog: [`docs/BACKLOG.md`](docs/BACKLOG.md)

## Quickstart (target, once M0 lands)

```bash
git clone <repo-url>
cd AI-Gestures-Tool
./scripts/setup_env.sh
source .venv/bin/activate
python -m gesture_control.app --debug
```

## Why one toolkit works across macOS/Windows/Linux

Only the input-injection layer (moving the cursor, sending clicks/keys) is
OS-specific; camera capture, hand-landmark detection, gesture recognition, and
voice processing are pure Python and run identically everywhere. See the
architecture diagram in [`docs/PRD.md`](docs/PRD.md#6-cross-platform-architecture).

## Gesture cheat-sheet

_Populated starting at milestone M2/M3 as gestures ship._

## Safety

A global safe-pause hotkey and a "fist" pause gesture always disable input
injection immediately. See [`docs/PRD.md`](docs/PRD.md#75-cross-cutting--safety).

## License

See [`LICENSE`](LICENSE) (added at M0).
