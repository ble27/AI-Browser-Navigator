# Known Issues

Issues discovered during development/verification, with their current status
and recommended workaround. Move an entry to "Resolved" (with a link to the
fixing commit) once it's actually fixed; don't delete history.

## Open

### MediaPipe HandLandmarker may abort on some macOS setups, even with the CPU delegate

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

**What we know**: This was hit while verifying M1 in the automated agent
sandbox used to build this repo (a non-interactive shell tool with no logged-in
GUI/Aqua session). It reproduced:
- With `mediapipe==1.0.1` via the Tasks API (`HandLandmarker`), with
  `BaseOptions.Delegate.CPU` explicitly set (see
  `gesture_control/vision/hand_landmarker.py`) -- did not help.
- With the legacy `mediapipe.solutions.hands.Hands` API on `mediapipe==0.10.21`
  (a version that still ships `solutions`) -- same class of crash.
- Setting `MEDIAPIPE_DISABLE_GPU=1` did not help.

The crash is inside MediaPipe's native (compiled) code touching a Metal
helper, which several public MediaPipe GitHub issues associate with GPU
delegate/graph-service setup on macOS (e.g. google-ai-edge/mediapipe#5568,
#5136, #5265) -- though in those reports, switching to the CPU delegate
resolved it, which it did not in our sandbox. Our current hypothesis is that
this specific automated shell environment has no GUI session for MediaPipe's
Metal backend to attach to at all (unlike a normal interactive Terminal.app
session), and some part of the graph touches Metal unconditionally
regardless of the requested delegate.

**What this means for you**: This has *not* been confirmed to reproduce in a
normal interactive Terminal session on a real macOS machine. Before assuming
your setup is broken:

1. Run `python -m gesture_control.app --debug` yourself from Terminal.app (or
   iTerm, etc.) -- a real logged-in GUI session, not an SSH/CI/automation
   shell.
2. If it works there, this issue was specific to the automated verification
   environment and can be downgraded to "resolved / environment-specific"
   in this doc -- please update it.
3. If it *also* crashes for you with the same stack trace, please capture the
   full crash output plus `python --version`, `sw_vers`, and `uname -m`, and
   file/update this issue -- it would then be a real, reproducible bug worth
   investigating further (e.g. pinning a different `mediapipe` patch version,
   or filing upstream).

**Workaround to try if you hit this**: none confirmed yet. Candidates to try,
in order: (a) a different `mediapipe` patch version, (b) running from a
plain Terminal.app window rather than over SSH/tmux without a GUI session,
(c) rebuilding the venv with Python 3.12 instead of 3.11 in case it's an ABI
interaction. Update this doc with whatever works.

## Resolved

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
