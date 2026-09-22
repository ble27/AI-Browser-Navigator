# Known Issues

Issues discovered during development/verification, with their current status
and recommended workaround. Move an entry to "Resolved" (with a link to the
fixing commit) once it's actually fixed; don't delete history.

## Open

(none currently -- see Resolved below)

## Resolved

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
