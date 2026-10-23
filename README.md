# AI Browser Navigator

Hands-free control of your computer with **offline hand-gesture tracking** and
**voice commands**. Say "search for hand tracking", then "click the first
link", and Chrome does it. Move your index finger to steer the cursor and pinch
to click.

<p align="center">
  <img src="docs/images/pill.png" alt="The voice pill with its settings panel" width="460">
</p>

*The voice pill: an on/off switch, a live soundwave, what was heard, and Settings
for scroll distance, typing response, text size, and contrast.*

## Why it is useful

- **Accessibility first.** Browse, search, scroll, and click without a mouse or
  keyboard. Settings cover scroll distance, typing speed, text size, and contrast.
- **Local by design.** Camera and hand tracking run on your machine. The command
  agent that turns speech into actions is local too.
- **One shared action layer.** Gestures and voice produce the same intents, and a
  global safe-pause hotkey stops all injected input at once.

> Status: macOS is the supported platform for input and voice automation. Chrome
> is required for browser control. Hardware QA items remain open in
> [`docs/QA_CHECKLISTS.md`](docs/QA_CHECKLISTS.md).

## Requirements

| Requirement | Notes |
|---|---|
| macOS | Input injection and voice are macOS-only today |
| Google Chrome | Voice recognition and page control run through Chrome |
| Python 3.11 or 3.12 | Installed into an isolated `.venv` |
| Node.js 18+ and npm | Builds the pill UI |
| Webcam and microphone | Webcam for gestures, microphone for voice |

## Quick start

```bash
git clone https://github.com/ble27/AI-Gestures-Tool.git
cd AI-Gestures-Tool
./scripts/setup_env.sh --voice
source .venv/bin/activate
(cd ui && npm install && npm run build)
./scripts/setup_page_bridge.sh          # one-time Chrome extension setup, see below
python -m gesture_control.app --voice --voice-mode streaming
```

A Chrome window with the pill opens. Allow the microphone when asked, leave that
window open, and speak. Commands act on your **other** Chrome window.

## Setup and installation

### 1. Python environment

```bash
./scripts/setup_env.sh --voice      # voice + gestures
./scripts/setup_env.sh              # gestures only, no audio stack
source .venv/bin/activate
```

### 2. macOS permissions

In **System Settings > Privacy & Security**, grant your terminal app:

- **Accessibility** (required to move the cursor and send keys)
- **Microphone**
- **Camera** (gestures only)

### 3. Build the pill UI

```bash
cd ui && npm install && npm run build && cd ..
```

### 4. Chrome page bridge (needed for clicking links, buttons, and typing)

```bash
./scripts/setup_page_bridge.sh
```

Or manually:

1. Open `chrome://extensions`, enable **Developer mode**, click **Load
   unpacked**, and select the repository's `chrome_extension/` folder.
2. Copy the 32-character extension ID shown on the card.
3. Install the native host from the activated `.venv`:

   ```bash
   python scripts/manage_chrome_native_host.py install --extension-id YOUR_EXTENSION_ID
   ```

4. Fully quit and reopen Chrome, then reload any tab you want to control.

After updating the repository, click **Reload** on the extension card and
refresh the page. Details: [`docs/CHROME_PAGE_BRIDGE.md`](docs/CHROME_PAGE_BRIDGE.md).

### 5. Verify

```bash
./scripts/check.sh                                  # lint, types, tests
python -m gesture_control.app --dump-page           # lists controls the bridge can see
```

## Usage

### Voice

```bash
python -m gesture_control.app --voice --voice-mode streaming   # recommended
python -m gesture_control.app --voice                          # offline utterance mode
python -m gesture_control.app --command "next tab"             # one-shot test, no microphone
```

Try these on a Google results page:

| Say | Result |
|---|---|
| "open github" | Opens the site in Chrome |
| "search for hand tracking" | Searches Google |
| "click the first link" / "open the first result" | Opens the first organic result |
| "click the second link" | Opens the second link |
| "scroll down" / "scroll to top" | Scrolls the page |
| "next tab" / "go back" / "reload" | Browser navigation |
| "focus search", then "type hello", then "enter" | Types into a field |

Full phrase list: [`docs/VOICE_COMMANDS.md`](docs/VOICE_COMMANDS.md).

Streaming mode uses Chrome's Web Speech API, so that audio is sent to Google.
Utterance mode (`--voice` alone) transcribes locally with faster-whisper.

### Hand gestures

```bash
python -m gesture_control.app --debug               # camera preview with landmarks
python -m gesture_control.app --debug --control     # also move the cursor and click
```

- Move your **index fingertip** to move the cursor.
- **Pinch** thumb and index together to left-click.
- More options: `--camera-index 1`, `--cursor-point palm`, `--edge-margin 0.2`.

### Safety

Press **Control+Option+Command+P** at any time to pause or resume all injected
input. `--control` is opt-in because it moves your real cursor.

## Troubleshooting

- **"click first link" does nothing:** reload the extension at
  `chrome://extensions`, refresh the tab, and restart the Python session.
- **Bridge not connecting:** rerun `./scripts/setup_page_bridge.sh`, then fully
  quit and reopen Chrome.
- **Camera or model errors:** see [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md).

## Documentation

- [`docs/VOICE_COMMANDS.md`](docs/VOICE_COMMANDS.md): every voice phrase
- [`docs/CHROME_PAGE_BRIDGE.md`](docs/CHROME_PAGE_BRIDGE.md): extension setup
- [`docs/WEBASSIGN_VOICE.md`](docs/WEBASSIGN_VOICE.md): homework-page phrases
- [`docs/PRD.md`](docs/PRD.md): product requirements and architecture
- [`docs/QA_CHECKLISTS.md`](docs/QA_CHECKLISTS.md), [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md), [`docs/BACKLOG.md`](docs/BACKLOG.md)
- [`AGENTS.md`](AGENTS.md): contributor and AI-agent onboarding

## License

See [`LICENSE`](LICENSE).
