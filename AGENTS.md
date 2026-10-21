# AGENTS.md — Onboarding for AI Agents & Contributors

This file is the fast-path for any AI coding agent (or human) picking up this
repo cold. Read this before touching code.

> Status: M0 (repo scaffold), M1 (camera + hand-landmark pipeline), and M2
> (macOS virtual mouse: cursor, pinch click, safe-pause) have landed and pass
> `scripts/check.sh`. A real mediapipe==1.0.x crash was found and fixed by
> pinning `mediapipe>=0.10.30,<0.11` (see `docs/KNOWN_ISSUES.md`);
> model/inference correctness is confirmed via
> `tests/manual/verify_hand_landmarker.py`, and the live-camera path is
> pending one more confirmation pass (see `docs/QA_CHECKLISTS.md`). The wider
> gesture vocabulary and voice start at M3.

## What this project is

A local-first, offline, cross-platform (macOS/Windows/Linux) tool that lets a
user control mouse/keyboard/navigation using webcam-tracked hand gestures
and/or offline voice commands. Full product context: [`docs/PRD.md`](docs/PRD.md).
Known environment gotchas (read before debugging a crash):
[`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md).

## One-command setup

```bash
./scripts/setup_env.sh   # creates venv, installs pinned deps
source .venv/bin/activate
```

## Running things

The pill UI lives in `ui/` (`npm install` once). `./scripts/check_ui.sh` runs its
typecheck, tests, and build; run it with `scripts/check.sh` before committing UI work.

```bash
python -m gesture_control.app --debug   # run with camera debug overlay
./scripts/check.sh                       # lint + type-check + unit tests (must pass before every commit)
pytest tests/unit                        # unit tests only
```

## Directory map — what owns what

```
gesture_control/
  vision/      # OpenCV capture + MediaPipe HandLandmarker wrapper. No OS-specific
               # input code lives here — this module only produces landmark data.
  gestures/    # Pure-Python gesture recognizer / state machine over normalized
               # landmark coordinates. No OS calls. Fully unit-testable.
  actions/     # Action Mapper: the single contract that both gestures and voice
               # go through. Defines the `Intent` dataclass and maps
               # Intent -> InputBackend calls.
  backends/    # The ONLY OS-specific layer. One `InputBackend` interface
               # (move_to, click, scroll, key, switch_app, ...) with adapters:
               # macos.py, windows.py, linux_x11.py, linux_wayland.py.
               # Runtime OS/session detection picks the right one.
  voice/       # openWakeWord (wake word) -> faster-whisper (offline STT) ->
               # intent parser -> Piper (offline TTS). Lazy-imported so
               # gesture-only usage never requires audio deps.
  config/      # Settings schema (pydantic/dataclasses) + YAML loader. Includes
               # accessibility profiles (Standard / Limited mobility / Voice-primary).
  app.py       # Entrypoint / tray app; wires vision -> gestures -> actions and
               # voice -> intents -> actions together.
tests/
  unit/        # Hardware-free tests: gesture math, smoothing, Action Mapper,
               # config parsing, intent parsing. These run in CI/scripts/check.sh.
  manual/      # Scripts to aid manual QA of camera/mouse/voice hardware paths.
docs/
  PRD.md              # Full product requirements.
  QA_CHECKLISTS.md     # Manual verification checklists per milestone (hardware-dependent).
  BACKLOG.md           # Explicitly tracked deferred items — NOT inline TODOs.
```

## The core contracts (read before adding a feature)

- **`Intent`** (in `gesture_control/actions/`): the shared shape both a
  recognized gesture and a parsed voice command produce. If you add a new
  gesture or voice command, it must resolve to an `Intent` the Action Mapper
  already understands, or you extend the Action Mapper — never call an
  `InputBackend` directly from `gestures/` or `voice/`.
- **`InputBackend`** (in `gesture_control/backends/`): the only place OS-specific
  code is allowed to live. New OS support = new adapter implementing this
  interface, nothing else changes.

## How to add a new gesture

1. Add detection logic in `gesture_control/gestures/` (pure function over
   landmarks -> gesture label). Add a unit test with synthetic landmark data.
2. Map the new gesture label to an `Intent` in the Action Mapper.
3. Add a manual QA checklist entry in `docs/QA_CHECKLISTS.md`.
4. Update the gesture cheat-sheet in `README.md`.
5. Commit as its own small `feat:` commit.

## How to add a new voice command

1. Extend the deterministic command grammar in `gesture_control/voice/` and add
   a unit test asserting the phrase parses to the expected `Intent`.
2. If it needs a new `Intent`, add it to the Action Mapper (shared with gestures).
3. Add a QA checklist entry, update docs, commit as its own `feat:` commit.

## Coding conventions (non-negotiable)

- Full type hints on every function signature (params + return).
- Google-style docstrings (`Args:`, `Returns:`, `Raises:`) on every public
  module/class/function. Inline `#` comments on non-obvious logic (thresholds,
  smoothing math, coordinate transforms) — explain *why*, not just *what*.
- `snake_case` functions/vars, `PascalCase` classes, `UPPER_SNAKE` constants.
- One responsibility per module. No God-objects.
- No commented-out code, no inline `TODO`s on `main` — track deferred work in
  `docs/BACKLOG.md` instead.
- `scripts/check.sh` (black + ruff + mypy + pytest) must exit 0 before any
  commit. Format with `black`, lint with `ruff`, type-check with `mypy`.
- Small, atomic, conventional-commit-style commits (`feat:`, `fix:`, `test:`,
  `docs:`, `chore:`, `refactor:`). Every milestone gets a `git tag mN-<name>`.
- Docs are updated in the *same commit* as the code they describe — never a
  follow-up commit.

## Safety-critical invariant

Any code path that can move the cursor or inject input MUST respect the global
safe-pause hotkey and the "fist" pause gesture. Never add an input-injection
code path that bypasses `InputBackend`'s pause check.

## Streaming voice agent (M5) — frozen contracts

Offline streaming voice (`--voice-mode streaming`, planned) is built in phases.
See [`docs/STREAMING_VOICE_HANDOFF.md`](docs/STREAMING_VOICE_HANDOFF.md) for
status and milestone order.

**Read-only without user approval:**

- `gesture_control/voice/stream_contracts.py`
- `gesture_control/voice/asr_repair.repair_command_text` (signature and semantics)
- New `IntentType` / `Intent` fields and dispatch rules in `actions/mapper.py`
- `LaunchableApp`, `PressableKey`, and desktop method signatures in
  `backends/base.py`
- `tests/unit/voice/test_contracts.py` and expected values in
  `tests/unit/voice/test_streaming_golden.py` (only removing `@pytest.mark.xfail`
  is allowed, and only in Phase 3 integration)

**Phase gates:** Phase 2 parallel tracks start only after Phase 1 contracts are
committed. Phase 3 waits for all four Phase 2 tracks. Do not edit the utterance
pipeline rollback path (`voice/agent.py`, `audio.py`, `transcription.py`,
`page.py`, `navigation.py`, `scroll.py`, `search.py`, `browser/bridge.py`).

**Parallel track file ownership (Phase 2):**

| Track | Owns |
|-------|------|
| STT | `voice/moonshine_stt.py`, `test_moonshine_stt.py`, voice extra in `pyproject.toml` |
| EXEC | `voice/executor.py`, `test_executor.py`, `live_page.current_url()` |
| SEG | `voice/segmenter.py`, `test_segmenter.py` |
| VOCAB | `voice/desktop.py`, `test_desktop_commands.py`, `browser.py`, `backends/macos.py` |

Tracks test against port fakes only; the coordinator runs `scripts/check.sh` and
commits one track at a time.
