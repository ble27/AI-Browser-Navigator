# Known Issues

Issues discovered during development/verification, with their current status
and recommended workaround. Move an entry to "Resolved" (with a link to the
fixing commit) once it's actually fixed; don't delete history.

## Open

### Debug window opens but the preview is entirely black on macOS

**Symptom**: `python -m gesture_control.app --debug` opens its debug window,
but the preview has no visible camera image.

**Mitigation**: Camera capture now prefers OpenCV's native AVFoundation backend
on macOS. If the app exits with a "returned only black frames" message, check
that the lens is uncovered, close any other app using the camera, grant the
launching terminal Camera permission in **System Settings > Privacy & Security
> Camera**, then retry. For an external camera, try another device with
`python -m gesture_control.app --debug --camera-index 1`.

**Verification pending**: this requires a physical webcam in the affected
macOS session. The camera unit tests cover backend selection and the
all-black-stream diagnostic, but cannot verify hardware availability.

## Resolved

### Link clicking failed with `unresolved page step` and `readiness timeout` on macOS

**Symptom**: `click first link` and `click second link` failed with
`[failed] unresolved page step`, while `open github first result` opened the
GitHub homepage and caused subsequent `click first link` commands to fail with
`[failed] readiness timeout`.

**Cause**:

1. On macOS APFS (case-insensitive, case-preserving), the shell workspace path
   (`/Users/.../Desktop/code/...`) and Finder's canonical path when loading the
   unpacked extension (`/Users/.../Desktop/Code/...`) hashed to different
   32-character Chrome extension IDs, so Chrome blocked `connectNative` against
   `com.ai_gestures.page_bridge.json`.
2. `parse_browser_command` matched prefix tokens in `_SITE_ALIASES` (turning
   `open github first result` into `OPEN_URL("https://github.com")` and pinning
   the planner's session host to `github.com`), and the planner did not clear
   stale session-host readiness after standalone web searches or follow-on
   clicks.
3. Unreloaded tabs without `result=True` flags fell back to counting header/skip
   links first on Google Search.

**Fix**: `ChromePageBridge.start()` now syncs both raw-path and canonical-path
extension IDs into `allowed_origins`, `parse_browser_command` requires the full
site name to match an alias, `DeterministicClausePlanner` clears stale
session-host readiness after web searches/navigation and follow-on clicks, and
`LivePageCommandResolver` infers organic results on search pages even when a tab
has not been refreshed after an extension update.

### Chrome Native Messaging host rejected Chrome's extension-origin argument

**Symptom**: `--dump-page` reported a disconnected bridge even though Chrome
started the installed native host for the correct extension ID.

**Cause**: Chrome appends the calling extension origin to the native-host
command line. The Python host's argument parser rejected that positional
argument and exited before connecting to the app's Unix socket.

**Fix**: the native host now accepts and validates the optional
`chrome-extension://<id>/` argument. The original failure changes from
`Chrome page bridge is disconnected` to a page-specific response once the
relay is connected. If that response says the receiving end does not exist,
reload the active supported page so Chrome injects the content script.

### Chrome page bridge stayed disconnected after native-host installation

**Symptom**: `--dump-page` and page commands such as `focus app search bar`
reported that the Chrome page bridge was disconnected, although the unpacked
extension and native-host manifest were present.

**Cause**: the installer resolved `.venv/bin/python` through its symlink and
wrote the base Python interpreter into the launcher. That interpreter did not
have `gesture_control` installed, so Chrome's native host exited at startup.

**Fix**: the installer now preserves the virtualenv Python path. Existing
installations must rerun `./scripts/setup_page_bridge.sh --extension-id <ID>`
or `./.venv/bin/python scripts/manage_chrome_native_host.py install
--extension-id <ID>`, then fully restart Chrome.

### Chrome page bridge did not reconnect after its Manifest V3 worker slept

**Symptom**: the native host and unpacked extension were correctly installed,
but `--dump-page` still reported a disconnected bridge after Chrome started.

**Cause**: the extension's Manifest V3 service worker can stop while idle.
Its previous code only connected the native host while that worker happened to
be running, leaving no path to reconnect when a page opened later.

**Fix**: the content script now wakes the worker on every supported page load,
and the worker also reconnects on Chrome startup and extension installation.
Reload the unpacked extension once in `chrome://extensions`, then reload the
target HTTPS tab. No native-host reinstall is needed for this fix.

### `next browser`, `previous browser`, and `close browser` controlled the Voice control window

**Symptom**: while streaming voice was active, browser navigation could reach
the separate Chrome Web Speech control window instead of the user's browsing
window. Tab switching and closing then affected the wrong window.

**Fix**: macOS navigation now checks that a normal Google Chrome browsing
window is frontmost before it sends a shortcut. It ignores commands when the
Voice control window (titled "Gesture Control") or another app has focus.

### MediaPipe HandLandmarker aborts with "Service is unavailable" on `mediapipe==1.0.0`/`1.0.1`

**Symptom**: `HandLandmarkerService()` (or `HandLandmarker.create_from_options`
directly) aborts the process with:

```
F0000 00:00:...  graph_service.h:139] Check failed: service_ Service is unavailable.
*** Check failure stack trace: ***
    ...
    @  ... -[DrishtiMetalHelper initWithCalculatorContext:]
    @  ... mediapipe::api2::TensorsToDetectionsCalculator::Open()
    ...
```

**Confirmed real bug, not a sandbox artifact**: initially suspected to be
specific to the automated agent sandbox used to build this repo (no GUI/Aqua
session), but it was independently reproduced by a human running
`python -m gesture_control.app --debug` directly in Terminal.app on the same
machine, camera included (`zsh: abort python -m gesture_control.app --debug`).
So this is a genuine `mediapipe` pip-wheel bug on this macOS/Apple Silicon
setup, not an environment quirk.

**Root cause isolated**: the crash happens at
`HandLandmarker.create_from_options()` itself (graph construction), before
any frame is even processed -- confirmed by reproducing it with a static
test image in both `RunningMode.VIDEO` and `RunningMode.IMAGE`, and with
`BaseOptions.Delegate.CPU` explicitly set. It is specific to
`mediapipe==1.0.0`/`1.0.1`'s HandLandmarker task graph, which appears to
unconditionally reference a GPU/Metal-related graph service regardless of
the requested delegate. `mediapipe==0.10.35` (the last 0.10.x release, with
the same numpy-2-compatible wheel) does **not** have this bug -- confirmed
working end-to-end (camera-free) against a static test image: model
download, `HandLandmarker.create_from_options`, `detect()`, and
`draw_hand_landmarks()` all succeeded and produced a correct skeleton
overlay for both hands.

**Fix**: pinned `mediapipe>=0.10.30,<0.11` in `pyproject.toml` (see the
comment there). Do not bump past `<0.11` without re-verifying this exact
crash is gone -- rerun the manual smoke test in
`tests/manual/verify_hand_landmarker.py` (or equivalent) against a static
image first, since it reproduces immediately at graph construction and
doesn't require a camera.

**If you still hit this after pulling the fix**: run
`pip install -e ".[dev]"` again to make sure your venv actually re-resolved
`mediapipe` to `0.10.35` (check with `python -c "import mediapipe; print(mediapipe.__version__)"`)
-- a stale venv from before this fix landed will still have `1.0.x` installed
until you reinstall.

### `black`/`ruff` crash with a CPython AST safety-check error on Python 3.12.5

**Symptom**: `black --check` fails immediately with:
```
Python 3.12.5 has a memory safety issue that can cause Black's AST safety checks to fail.
```

**Cause**: A known CPython `ast` module regression specific to the 3.12.5
patch release (fixed in 3.12.6).

**Fix**: `scripts/setup_env.sh` now prefers Python 3.11 first, falling back
to 3.12 only if 3.11 isn't available. If you must use 3.12, ensure it's
>=3.12.6.

### `SSL: CERTIFICATE_VERIFY_FAILED` when downloading the HandLandmarker model

**Symptom**: `ensure_hand_landmarker_model()` raises `RuntimeError: Failed to
download the MediaPipe HandLandmarker model ...` wrapping an
`SSLCertVerificationError: unable to get local issuer certificate`.

**Cause**: The official python.org macOS installer (as opposed to Homebrew's
Python) ships its own OpenSSL and does not use the system/Keychain CA store
by default, so `urllib` can't verify HTTPS certificates until you either run
the installer's `Install Certificates.command` or point Python at a CA
bundle.

**Fix**: Install/upgrade `certifi` (already a transitive dependency via
`mediapipe`) and point Python at its bundle for the current shell session:

```bash
export SSL_CERT_FILE="$(python -c 'import certifi; print(certifi.where())')"
```

Add this to your shell profile, or run the python.org installer's
`Install Certificates.command`, if you hit this repeatedly.
