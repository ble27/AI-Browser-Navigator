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

## Ideas to evaluate later (not committed to v1 scope)

- Head-pose or eye-tracking as an additional input modality for users with no
  functional hand use.
- Per-application gesture profiles (e.g., different swipe bindings in a
  browser vs. a presentation app).
- Cloud/optional telemetry for crash reporting — must remain strictly opt-in
  given the project's offline/privacy commitment.
