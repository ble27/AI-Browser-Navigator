# Voice and Chrome Page Commands

## Voice commands (macOS)

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
down. macOS converts each page to five fixed pynput notches. A plain
`scroll up` or `scroll down` uses the pill's scroll setting (small is 1 page,
medium is 3, large is 6). Without that setting, holding the phrase longer
scales from 3 to at most 10 pages using captured audio duration. Explicit
size and page phrases always win.

Unknown names (`open my bank`), localhost/IP/private hosts, whitespace,
non-HTTPS schemes, and URLs with credentials are rejected. Extra unknown words
are rejected by the navigation grammar. Each backend operation checks
SafePause immediately, though the
one-shot `--command` process does not start the global pause hotkey listener.
Wake word activation and TTS are not part of this slice. An independently
installed Chrome page bridge adds active-page commands:

- `click Add to Cart` / `press Log in` / `hit submit` / `pick Continue` /
  `push the Buy button` / `mouse click on search`
- `click the pricing link` / `click the second link` / `click the link` when
  only one link is on the page. On a Google, Bing, or DuckDuckGo results page,
  `click the first link`, `click the first result`, `open the first result`,
  `click top link`, and `open <topic> first result` open the first matching
  organic result, skipping header, navigation, and sponsored links. Link clicks
  scroll the link into view and follow its `https` address when the page does
  not handle the click itself.
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

- `focus search bar` or `focus Chrome search bar` focuses Chrome's **omnibox**
  (address/search bar) with Command+L. `focus address bar`, `focus url bar`,
  and `focus omnibox` are aliases. It needs Chrome's browser window in front,
  not the voice pill.
- `focus app search bar` focuses the active app's unique HTML search field.
  It requires the Chrome page bridge; `focus page search field` is an alias.
- After either focus command, `type <text>` enters literal text in that focused
  field. Streaming dictation starts about 0.2 seconds after the words stop
  changing, instead of waiting for Chrome to finalize the utterance. A later
  correction appends only the new letters. `enter`, `return`, or `done`
  presses the Mac Return key (not the keypad Enter key) to submit it. No
  focus command types or submits text.
- `unfocus` blurs a focused app search field or page composer. `delete word`
  removes the word before the cursor in that field, and `clear search` clears
  only a focused search field.
- `delete line` presses Command+Right, Command+Shift+Left, then Delete, so it
  removes the text on the line where the blinking cursor is, in any focused
  text field. It needs no page bridge, and it reports an error if the voice
  pill has keyboard focus instead of your page. `unfocus`, `delete word` and
  `clear search` require the page bridge. None of these match phrases such as
  `type delete word` or `search for delete word`.

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
