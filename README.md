# AI Vision Gesture Control Tool

Control your computer with hand gestures and offline voice commands — a
local-first, cross-platform (macOS/Windows/Linux) virtual mouse and navigation
tool built with Python, OpenCV, and MediaPipe, with accessibility as a
first-class use case.

> Status: M0 (scaffold), M1 (camera + hand-landmark debug overlay), and M2
> (macOS virtual mouse) are implemented and unit-tested. Cursor control keeps
> the newest camera frame, tracks the index fingertip, and freezes motion
> during pinch approach so clicks stay on target. M2 awaits its final hardware
> verification pass.

- Full product requirements: [`docs/PRD.md`](docs/PRD.md)
- Contributor / AI-agent onboarding: [`AGENTS.md`](AGENTS.md)
- Manual QA checklists: [`docs/QA_CHECKLISTS.md`](docs/QA_CHECKLISTS.md)
- Chrome page bridge setup: [`docs/CHROME_PAGE_BRIDGE.md`](docs/CHROME_PAGE_BRIDGE.md)
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
python -m gesture_control.app --debug --control --cursor-point palm
python -m gesture_control.app --debug --control --edge-margin 0.2
python -m gesture_control.app --command "open cursor webpage"  # open that site in Google Chrome
python -m gesture_control.app --command "next tab"        # send a fixed Chrome shortcut
python -m gesture_control.app --command "search for hand tracking"
python -m gesture_control.app --command "scroll down 3 pages"
python -m gesture_control.app --voice                     # continuously listen locally (macOS)
python -m gesture_control.app --version
```

`--control` is explicit because it injects input. On macOS, grant the
launching terminal **Accessibility** permission in **System Settings > Privacy
& Security > Accessibility**. Point with the index fingertip to move the
pointer; touch the thumb and index fingertips together once to click.
Press **Control+Option+Command+P** at any time to pause or resume all injected
input. If the pointer needs too much arm travel, raise `--edge-margin`; if it
overshoots near edges, lower it. If pinch-click tip flex walks the target, try
`--cursor-point index_mcp` or `--cursor-point palm`.

## Why one toolkit works across macOS/Windows/Linux

Only the input-injection layer (moving the cursor, sending clicks/keys) is
OS-specific; camera capture, hand-landmark detection, gesture recognition, and
voice processing are pure Python and run identically everywhere. See the
architecture diagram in [`docs/PRD.md`](docs/PRD.md#6-cross-platform-architecture).

## Gesture cheat-sheet

- Move index fingertip: move cursor. The pointer uses a 1€ filter, freezes
  during pinch approach, and reaches screen edges from the center of the
  camera view.
- Thumb-index pinch: left-click (cursor freezes while the tips close so the
  click stays on the aimed target).
- Control+Option+Command+P: pause/resume all injected input.

Double-click, right-click, drag, scrolling, fist pause, and navigation
gestures are scheduled for M3.

## Voice cheat-sheet (macOS)

Install the optional local audio stack once:

```bash
python -m pip install -e ".[voice]"
```

Grant the launching terminal **Microphone** and **Accessibility** permissions,
focus Google Chrome, then explicitly start continuous listening:

```bash
python -m gesture_control.app --voice
# Or select another faster-whisper model/local directory:
python -m gesture_control.app --voice --voice-model base.en
```

The default `tiny.en` model runs on CPU with int8 compute. It may download and
cache model files on first use; after that, recognition is fully local. Audio
is never uploaded and no hosted API is used. `--voice` continuously waits for
commands until Ctrl+C; there is no wake word yet. Use
**Control+Option+Command+P** to pause/resume injected browser actions during
the session.

`--command "<phrase>"` remains available for one-shot parser/backend testing
without microphone capture. Open commands launch Google Chrome specifically
(not the default browser); navigation commands control the focused app, so
Chrome must be focused.

- `open` / `go to` / `visit` Amazon, Google, YouTube, GitHub, Cursor, or Apple
- `open example.com` / `visit docs.example.com`: validated public domains,
  upgraded to HTTPS
- `open https://example.com/docs`: that exact validated HTTPS URL
- `next tab` / `switch to next tab`; `previous tab` / `go to previous tab`
- `new tab`; `close tab` / `close current page` / `close browser tab`
- `reopen closed tab` / `restore closed tab`
- `go back` / `back`; `go forward` / `forward`
- `reload` / `refresh` / `refresh current page`
- `search for X` / `look up X` / `lookup X` / `google X` / `find X online`
- `page up` / `page down`; `scroll up` / `scroll down`; small, large, and
  explicit `1`-`10` page variants; `scroll to top` / `scroll to bottom`

Scroll intent amounts are signed page units: positive is up and negative is
down. macOS converts each page to five fixed pynput notches. Holding a plain
spoken `scroll up` or `scroll down` longer scales from 3 to at most 10 pages
using captured audio duration; explicit size/page modifiers win.

Unknown names (`open my bank`), localhost/IP/private hosts, whitespace,
non-HTTPS schemes, and URLs with credentials are rejected. Extra unknown words
are rejected by the navigation grammar. Each backend operation checks
SafePause immediately, though the
one-shot `--command` process does not start the global pause hotkey listener.
Wake word activation and TTS are not part of this slice. An independently
testable Chrome page bridge is available but is not wired into the voice
command or action-mapper path yet; see
[`docs/CHROME_PAGE_BRIDGE.md`](docs/CHROME_PAGE_BRIDGE.md).

## Safety

A global safe-pause hotkey and a "fist" pause gesture always disable input
injection immediately. See [`docs/PRD.md`](docs/PRD.md#75-cross-cutting--safety).

## License

See [`LICENSE`](LICENSE) (added at M0).
