# Backlog / Deferred Items

Tracked here instead of inline `TODO`s so `main` stays clean. Move items out
(with a link to the commit/PR that resolved them) once done.

## Deferred past v1

- Mobile OS support (iOS/Android).
- Full sign-language recognition.
- Cursor "sticky snap" to clickable UI elements via platform accessibility
  APIs (needs separate per-OS accessibility-tree integration — bigger than a
  v1 stretch item).
- Optional local LLM (Ollama) fallback for free-form voice phrasing beyond the
  deterministic command grammar.
- Optional FINAL redecode with a stronger local STT (`mlx-whisper` /
  `whisper.cpp` / `parakeet-mlx`) if faster-whisper ``base.en`` via
  `--voice-redecode` is still insufficient on the real-voice corpus.
- Local-only streaming STT as the default (Moonshine / MLX Whisper /
  Parakeet). Streaming default is Chrome Web Speech; local models stay an
  optional `--voice-stt` path. See `docs/STREAMING_VOICE_HANDOFF.md`.
- Full Wayland parity (compositor-specific quirks beyond the documented
  `ydotool` best-effort path).

## Later voice / browser milestone

- Windows and Linux adapters for `InputBackend.open_url` (Chrome binary + URL).
  macOS uses `open -a "Google Chrome"`. The continuous `--voice` runtime is
  likewise macOS-only until those platforms have input backends and QA.
- Wake word (`openWakeWord`) and confirmation TTS. The current `--voice`
  session starts listening only after explicit user launch and prints text
  feedback.
- User-editable named-site aliases in config. Built-in common aliases and
  validated public domains are available now.

## Ideas to evaluate later (not committed to v1 scope)

- Head-pose or eye-tracking as an additional input modality for users with no
  functional hand use.
- Per-application gesture profiles (e.g., different swipe bindings in a
  browser vs. a presentation app).
- Cloud/optional telemetry for crash reporting — must remain strictly opt-in
  given the project's offline/privacy commitment.
- Relative (trackpad-style) cursor mapping as an alternative to absolute
  camera-to-screen mapping — may reduce overshoot for large displays once
  absolute tip tracking + approach-freeze is live-verified.
- Skip-frame MediaPipe inference with optical-flow / Kalman interpolation
  between detections — only worth it if live FPS stays well below camera rate
  after the 320×240 + async capture path is confirmed.
- MediaPipe GPU/Metal delegate for HandLandmarker on Apple Silicon — blocked
  until a mediapipe build exists that does not abort at graph construction
  (see `docs/KNOWN_ISSUES.md`); CPU remains the supported path.
