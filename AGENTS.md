# AGENTS.md — Onboarding for AI Agents & Contributors

This file is the fast-path for any AI coding agent (or human) picking up this
repo cold. Read this before touching code.

> Status: repo scaffold not yet created. This file describes the *target*
> structure and conventions this project commits to as soon as M0 lands; treat
> it as the contract to build toward, and update it in the same commit if
> reality ever diverges from what's written here.

## What this project is

A local-first, offline, cross-platform (macOS/Windows/Linux) tool that lets a
user control mouse/keyboard/navigation using webcam-tracked hand gestures
and/or offline voice commands. Full product context: [`docs/PRD.md`](docs/PRD.md).

## One-command setup

```bash
./scripts/setup_env.sh   # creates venv, installs pinned deps
source .venv/bin/activate
```

## Running things

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
