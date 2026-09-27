# Streaming voice agent: implementation handoff

Goal: a macOS voice agent that performs tasks **while the user keeps talking**
(open sites and apps, browse, search, type, click, press keys, ask AI
assistants). Everything goes through the existing `ActionMapper` and
`InputBackend`, so the `SafePause` gate stays in force.

Full streaming contracts:
`gesture_control/voice/stream_contracts.py` and
`~/.cursor/plans/streaming_voice_agent_ce237a8c.plan.md`.

Jev-inspired hardening plan:
`~/.cursor/plans/jev-inspired_voice_pipeline_8c8c916b.plan.md`.

## Locked plan (2026-09-27)

Streaming STT is **Chrome/Edge Web Speech API** (free browser recognizer;
audio goes to Google). The **agent stays local and open-source**: repair →
segmenter → spans → policy → planner → executor → `ActionMapper`. No TypeSafe
Jev, no paid Cloud Speech-to-Text, no local Whisper/Moonshine required for the
default streaming path.

```
Chrome page (SpeechRecognition)
  interim / final text
        │  localhost WebSocket or HTTP
        ▼
Python StreamingVoiceAgent (existing)
  → ActionMapper / InputBackend
```

- Web Speech only exists in a browser page, so a small local control page
  bridges recognition events into `TranscriptEvent`s. Downstream contracts stay
  the same.
- Moonshine / MLX Whisper stay optional `--voice-stt` backends, not the default
  streaming bet.
- Utterance mode (`faster-whisper`) stays the offline rollback path.
- Default stays `utterance` until a live Web Speech session clears the M5
  checklist.

## Status

- **Phases 1–3 + Jev S1–S5 (done):** streaming behind `--voice-mode streaming`.
  Policy/debounce, spans, fuzzy repair, ranked clicks + `warm()`, SafePause
  skip+drain, early tab/scroll from partials, session readiness, destructive
  click confirm. Those stages stay.
- **Web Speech bridge (landed):** `--voice-stt web_speech` is the streaming
  default. A localhost control page posts Chrome `SpeechRecognition` results
  into `WebSpeechStreamingTranscriber`.
- **Next (you at the mic):**
  `python -m gesture_control.app --voice --voice-mode streaming`
  Allow the mic in the control window, click Start microphone, then re-run
  the M5 streaming checklist.

## Hard rules

- Frozen contracts in `stream_contracts.py` / `test_contracts.py` stay read-only
  without approval.
- Utterance rollback path (`agent.py`, `audio.py`, `transcription.py`, …) stays
  intact; default remains `utterance` until a live Web Speech session passes
  the M5 checklist.
- No false success: `DONE` only after real `ActionMapper.dispatch`.
- Commits: explicit paths only; never push unless asked.
