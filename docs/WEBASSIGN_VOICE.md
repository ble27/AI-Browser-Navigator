# WebAssign voice control (macOS)

End-to-end path for dictating answers into WebAssign (or any HTTPS page) with
the local voice agent. No Browserless / cloud browser API is required: the
Python app talks to your real Chrome tab through the first-party page bridge.

## One-time setup

```bash
cd /path/to/AI-Gestures-Tool
./scripts/setup_env.sh --voice
source .venv/bin/activate
./scripts/setup_page_bridge.sh
```

`setup_page_bridge.sh` opens `chrome://extensions` and Finder on
`chrome_extension/`. Load the unpacked extension, paste its 32-character ID
when prompted, then fully quit and reopen Chrome.

Verify the bridge against a local fixture:

```bash
python scripts/serve_bridge_fixture.py
# In Chrome open the printed webassign_fixture.html URL, keep that tab active.
python - <<'PY'
from gesture_control.browser import ChromePageBridge
with ChromePageBridge(timeout=10) as bridge:
    snap = bridge.snapshot()
    print(snap.url)
    for el in snap.elements:
        print(el.role, el.name)
PY
```

You should see an `Answer` textbox and a `Submit Answer` button.

## Live WebAssign session

1. Grant the terminal **Microphone** and **Accessibility** permissions.
2. Log into WebAssign in Google Chrome and open a question page (HTTPS).
3. Keep that tab focused.
4. Run:

```bash
source .venv/bin/activate
python -m gesture_control.app --voice
```

Discover speakable names on the focused tab anytime:

```bash
python -m gesture_control.app --dump-page
```

Useful phrases:

| Say | Effect |
| --- | --- |
| `answer is 42` | Type `42` into the unique Answer field |
| `the answer is 3.14` | Same, with spoken article |
| `type 42 into answer` | Explicit field targeting |
| `type 9 into answer 1` / `type 8 into second answer` | Disambiguate duplicate Answer boxes |
| `submit answer` / `submit` | Click the unique Submit control |
| `click submit answer` | Same via generic click grammar |
| `focus answer` | Focus the answer box without typing |

Safe-pause remains **Control+Option+Command+P**.

## If a command is unrecognized

- Snapshot the page (script above) and speak the **exact** control name shown.
- Duplicate unlabeled fields need `answer 1` / `second answer`.
- Cross-origin iframes are not indexed; same-origin iframes are.
- CAPTCHA / canvas widgets are out of scope.

## Relation to ordinary websites

The same bridge powers Amazon/Google/apple.com/etc.: `click …`, `fill … with …`,
`search for …`, scroll, and tab commands. WebAssign-specific phrases are
extra vocabulary on top of that shared path.

On apple.com, `search for airpods` opens the collapsed **Search apple.com**
control when needed, then types into the revealed field. If names look wrong,
reload the unpacked extension and run `--dump-page` on the focused tab.

Local fixtures:

```bash
python scripts/serve_bridge_fixture.py
# open webassign_fixture.html or apple_fixture.html from the printed URLs
```
