# AI Vision Gesture Control Tool

Control your computer with hand gestures and offline voice commands — a
local-first, cross-platform (macOS/Windows/Linux) virtual mouse and navigation
tool built with Python, OpenCV, and MediaPipe, with accessibility as a
first-class use case.

> Status: M0-M2 and the macOS M5 voice/browser slice are implemented and
> unit-tested. Local voice can open/search/navigate/scroll Chrome and, with the
> optional first-party extension, click, focus, type, and submit named controls
> on the active HTTPS page. Hardware QA checklist items remain to be completed.

- Full product requirements: [`docs/PRD.md`](docs/PRD.md)
- Contributor / AI-agent onboarding: [`AGENTS.md`](AGENTS.md)
- Manual QA checklists: [`docs/QA_CHECKLISTS.md`](docs/QA_CHECKLISTS.md)
- Chrome page bridge setup: [`docs/CHROME_PAGE_BRIDGE.md`](docs/CHROME_PAGE_BRIDGE.md)
- WebAssign / homework voice: [`docs/WEBASSIGN_VOICE.md`](docs/WEBASSIGN_VOICE.md)
- Deferred work / backlog: [`docs/BACKLOG.md`](docs/BACKLOG.md)
- Known issues / environment gotchas: [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md)

## Quickstart

Prerequisites: macOS for input/voice automation, Google Chrome for browser
control, and Python 3.11 or 3.12. The setup script creates an isolated `.venv`;
no global Python packages are required.

```bash
git clone https://github.com/ble27/AI-Gestures-Tool.git
cd AI-Gestures-Tool
./scripts/setup_env.sh --voice
source .venv/bin/activate
./scripts/check.sh
python -m gesture_control.app --voice
```

For gesture/camera development without the optional audio stack, run
`./scripts/setup_env.sh` without `--voice`.

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
python -m gesture_control.app --voice                     # utterance mode (default; macOS)
python -m gesture_control.app --voice --voice-mode streaming  # Chrome Web Speech + local agent
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
# Streaming agent (Chrome Web Speech hears; the local agent acts):
python -m gesture_control.app --voice --voice-mode streaming
# Or select another faster-whisper model for utterance mode:
python -m gesture_control.app --voice --voice-model base.en
```

Utterance mode uses `tiny.en` on CPU with int8 compute. It may download and
cache model files on first use; after that, that mode stays fully local.
Streaming mode opens a separate Chrome window and uses the free Web Speech
API, so that audio is sent to Google. The command agent still runs locally.
`--voice` waits for commands until Ctrl+C; there is no wake word yet. Use
**Control+Option+Command+P** to pause/resume injected browser actions during
the session.

`--command "<phrase>"` remains available for one-shot parser/backend testing
without microphone capture. Open commands launch Google Chrome specifically
(not the default browser); navigation commands control the focused app, so
Chrome must be focused.

- `open` / `go to` / `visit` Amazon, Google, YouTube, GitHub, Cursor, Apple,
  Reddit, Wikipedia, Netflix, Twitter/X, Bing, Facebook, or LinkedIn
- `open example.com` / `visit docs.example.com`: validated public domains,
  upgraded to HTTPS
- `open https://example.com/docs`: that exact validated HTTPS URL
- `next browser` / `next tab`; `previous browser` / `previous tab`
- `close browser` / `close tab` / `close current page`
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
installed Chrome page bridge adds active-page commands:

- `click Add to Cart` / `press Log in` / `hit submit` / `pick Continue` /
  `push the Buy button` / `mouse click on search`
- `focus search` / `click the search box`
- `type hello into email` / `fill email with hello`
- `search for mechanical keyboard` uses the page's unique named search field
  (or opens a unique collapsed search button like apple.com), then falls back
  to omnibox search when no page search target is available
- `python -m gesture_control.app --dump-page` prints speakable control names
  from the focused Chrome tab (requires the page bridge)

See [`docs/CHROME_PAGE_BRIDGE.md`](docs/CHROME_PAGE_BRIDGE.md) and
[`docs/WEBASSIGN_VOICE.md`](docs/WEBASSIGN_VOICE.md) for the one-time
unpacked-extension setup and WebAssign answer/submit phrases.

### Focus and compose fields

Voice commands keep Chrome's browser UI separate from an app's HTML controls.

- `focus Chrome search bar` focuses Chrome's **omnibox** (address/search bar).
  `focus Chrome address bar` and `focus Chrome omnibox` are aliases.
- `focus app search bar` focuses the active app's unique HTML search field.
  It requires the Chrome page bridge; `focus page search field` is an alias.
- After either focus command, `type <text>` enters literal text in that focused
  field. `enter` or `done` submits it. No focus command types or submits text.
- `unfocus` blurs a focused app search field or page composer; `delete line`
  clears that field, `delete word` removes the word before the cursor, and
  `clear search` clears only a focused search field. These commands require
  the page bridge and do not match phrases such as `type delete word` or
  `search for delete word`.

"Chrome search bar" always means the omnibox. "App search bar" always means a
web page's HTML field. This differs from `search for <text>` behavior,
which searches a unique page field when available and otherwise searches the
omnibox in one command.

### Enable live page click/type

```bash
./scripts/setup_page_bridge.sh
```

Or manually:

1. Open `chrome://extensions`, enable **Developer mode**, choose **Load
   unpacked**, and select this repository's `chrome_extension/` directory.
2. Copy the displayed 32-character extension ID.
3. From the activated `.venv`, install the allow-listed native host:

   ```bash
   python scripts/manage_chrome_native_host.py install \
     --extension-id YOUR_EXTENSION_ID
   ```

4. Fully quit and reopen Chrome, open an HTTPS page (or the local
   WebAssign fixture via `python scripts/serve_bridge_fixture.py`), and run
   `python -m gesture_control.app --voice`.

Homework-oriented phrases on WebAssign-style pages:

- `answer is 42` / `the answer is 42`
- `type 9 into answer 1` / `type 8 into second answer`
- `submit answer` / `submit`

## Voice pill (Chrome, macOS)

A small Dynamic-Island-style pill is the control surface for streaming voice.
It shows a live soundwave and what was heard, and has one switch that turns the
AI on or off for your Chrome pages.

```bash
cd ui && npm install && npm run build && cd ..   # once, builds ui/dist
python -m gesture_control.app --voice --voice-mode streaming
```

Allow the microphone in the pill window and leave it open; commands act on your
other Chrome window. Speech is recognized by Chrome (audio goes to Google); the
pipeline that turns clauses into actions stays local.

- **Switch off** stops listening and drops anything heard until you switch back on.
- **Phases:** idle, listening (interim words), working (final words), done
  (what ran), error (why it did not run, or "Input paused" under SafePause).
- UI development: `cd ui && npm run dev` (UI only), `npm test`, `npm run typecheck`.
- If `ui/dist` is missing the session falls back to the plain control page.

## Safety

A global safe-pause hotkey and a "fist" pause gesture always disable input
injection immediately. See [`docs/PRD.md`](docs/PRD.md#75-cross-cutting--safety).

## License

See [`LICENSE`](LICENSE) (added at M0).
