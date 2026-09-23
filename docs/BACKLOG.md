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
- Full Wayland parity (compositor-specific quirks beyond the documented
  `ydotool` best-effort path).

## Later voice / browser milestone

- Live in-page actions in the user's already-open Chrome (click, type) via a
  first-party extension and Native Messaging. The offline name resolver is
  landing first. Do not attach the DevTools Protocol to the default Chrome
  profile. See `docs/research/voice-html-navigation.md`.
- Windows and Linux adapters for `InputBackend.open_url` (Chrome binary + URL).
  macOS uses `open -a "Google Chrome"`. The continuous `--voice` runtime is
  likewise macOS-only until those platforms have input backends and QA.
- Wake word (`openWakeWord`) and confirmation TTS. The current `--voice`
  session starts listening only after explicit user launch and prints text
  feedback.
- User-editable site allowlist in config. The built-in list is Cursor and Apple
  plus an explicit `https://` URL.

## Ideas to evaluate later (not committed to v1 scope)

- Head-pose or eye-tracking as an additional input modality for users with no
  functional hand use.
- Per-application gesture profiles (e.g., different swipe bindings in a
  browser vs. a presentation app).
- Cloud/optional telemetry for crash reporting — must remain strictly opt-in
  given the project's offline/privacy commitment.
