# Streaming voice agent: implementation handoff

Goal: an offline macOS voice agent that performs tasks **while the user keeps
talking** (open sites and apps, browse, search, type, click, press keys, ask AI
assistants). Everything goes through the existing `ActionMapper` and
`InputBackend`, so the `SafePause` gate stays in force.

Full spec (frozen contracts, semantics, golden cases G1 to G17):
`~/.cursor/plans/streaming_voice_agent_ce237a8c.plan.md`. After Phase 1,
`gesture_control/voice/stream_contracts.py` and
`tests/unit/voice/test_contracts.py` become the source of truth.

## Status

- **S0 (done):** raw Moonshine failed the gate. `small_streaming` got 83% of
  brand names right; `medium_streaming` got 92% but took 515 ms.
- **S0b (done, GO):** `small_streaming` plus
  `gesture_control/voice/asr_repair.py` got **100%** of brands in 484 ms, with
  0 non-brand regressions. See `docs/research/voice-streaming-stt.md`.
- **Next: M0**, below. Nothing from S0/S0b is committed yet.

## Order of work

1. **M0, commit the finished gates.** Run `black` and `ruff --fix` on
   `tests/manual/verify_moonshine_streaming.py`, run `scripts/check.sh`, then
   make two commits:
   - `feat: add context-gated ASR brand repair for streaming STT`, containing
     `asr_repair.py` and `test_asr_repair.py`.
   - `test: add Moonshine streaming spike harness and S0/S0b results`,
     containing the harness and the research doc. Gitignore
     `tests/manual/_cache/`.
2. **Phase 1, contracts (serial; blocks everything).** Add
   `voice/stream_contracts.py`, the new intents and fields in
   `actions/mapper.py`, `LaunchableApp`, `PressableKey` and the default methods
   in `backends/base.py`, `test_contracts.py`, the golden suite in
   `test_streaming_golden.py` (every case strict-xfail), and a
   frozen-contract section in `AGENTS.md`. Commit.
3. **Phase 2, four parallel tracks with disjoint files.** One agent per
   track. Each writes its tests first and tests against fakes of the other
   tracks' contracts.
   - **STT:** `voice/moonshine_stt.py`, its tests, and the `moonshine-voice`
     pin in `pyproject.toml`.
   - **EXEC:** `voice/executor.py`, its tests, and
     `LivePageCommandResolver.current_url()` in `voice/live_page.py`.
   - **SEG:** `voice/segmenter.py` and its tests.
   - **VOCAB:** `voice/desktop.py`, aliases and browse prefixes in
     `voice/browser.py`, and `open_app` / `type_focused` / `press_key` /
     `frontmost_app_name` in `backends/macos.py`, with tests.
   The coordinator commits each track separately once it's green.
4. **Phase 3, integration (serial).** Add `voice/planner.py`,
   `voice/streaming_agent.py`, and in `app.py` the `--voice-mode` flag
   (default `utterance`) and `--voice-stt` flag (default `small_streaming`).
   Remove the xfail markers one group at a time, running the golden tests
   after each group: G1 G2 G16, then G3 G4, then G5-G7, then G8-G11, then
   G12-G14 G17, then G15. Commit.
5. **Phase 4, live QA with the user at the mic.**
   - `verify_moonshine_streaming.py --live --repair` must get at least 90% of
     brands right. If it doesn't, stop.
   - Then run the live flows: reddit, Amazon with scroll, Amazon "click
     orders", Notes, ask Claude and ChatGPT, SafePause pressed mid-queue,
     cancel, and utterance mode as a regression check.
   - Once all pass, flip the default to `streaming`, update the docs, commit,
     and tag `m5-streaming-voice`.

## Hard rules

- **Frozen:** `stream_contracts.py`, `repair_command_text`, the new
  `Intent` and backend enums, fields and signatures, `test_contracts.py`, and
  the golden expected values. If a contract blocks you, stop and ask the
  user.
- **Tests first** in every track. Removing a golden xfail marker is the only
  allowed edit to the golden file, and only in Phase 3.
- **No false success:** report `DONE` only after a real
  `ActionMapper.dispatch`. No bare `except`, no `# type: ignore`, no weakened
  assertions. Tests fake only the ports, never the unit under test.
- **Don't touch:** `voice/agent.py`, `audio.py`, `transcription.py`,
  `page.py`, `navigation.py`, `scroll.py`, `search.py`, the Chrome extension,
  `browser/bridge.py`, or any gesture or vision code. The utterance pipeline is
  the rollback path.
- **Commits:** only the coordinator commits, one at a time. Stage explicit
  paths only, never `git add -A`. The user has unrelated uncommitted edits in
  `browser/bridge.py`, `voice/page.py` and several tests. Run
  `scripts/check.sh` before every commit, and use conventional commit
  messages with the docs in the same commit. Never push.
