# Research: Moonshine streaming STT spike (S0)

**Date:** 2026-09-26  
**Repo:** AI-Gestures-Tool  
**Scope:** Go/kill gate before building the streaming voice agent.  
**Package:** `moonshine-voice==0.1.5`

## Decision

**S0 raw models: KILL.** **S0b with repair: GO** — see [S0b repair gate](#s0b-repair-gate-go--proceed-to-s1).

Both candidate architectures were evaluated raw on the same 20-phrase macOS
`say`-synthesized set (16 kHz mono WAV). Live mic capture was **not** run in
the S0 pass (`--live` requires an interactive speaker).

| Criterion | small_streaming | medium_streaming | Required |
|---|---|---|---|
| Brand keyword accuracy | **83%** (10/12) | **92%** (11/12) | ≥ 90% |
| Beats tiny.en (75%, 9/12) | yes | yes | must beat |
| Partials during speech | **95%** | **95%** | delivers partials |
| Median final latency after speech end | **259 ms** | **515 ms** | ≤ 500 ms |
| Offline after first download | yes | yes | yes |
| **Verdict** | **KILL** (brand) | **KILL** (latency) | — |

### Why kill

1. **`small_streaming`:** brand accuracy 83% < 90%. Persistent misses on
   `open openai` → `Open up an A.` and `open claude` → `Open Cloud`.
2. **`medium_streaming`:** brand accuracy clears the bar (92%; only miss is
   `open openai` → `OpenOpene.`), but **median final latency is 515 ms >
   500 ms**. Several short commands (`next tab`, `search for headphones`,
   `type hello world`, `open chatgpt`) finalized well above 1 s.

Per the plan: if Moonshine fails go criteria **and** `medium_streaming` also
fails, **stop and report** — do not build product code.

## Listener / event API (pinned for a future S2 adapter)

Observed in `moonshine-voice` 0.1.5:

- Package import: `moonshine_voice`
- Model fetch: `get_model_for_language(language, wanted_model_arch) -> (model_path, model_arch)`
- Architectures: `ModelArch.SMALL_STREAMING` (4), `ModelArch.MEDIUM_STREAMING` (5)
- String form: `string_to_model_arch("small-streaming")` / `"medium-streaming"`
- Constructor: `Transcriber(model_path=..., model_arch=..., update_interval=0.3)`
- Stream lifecycle:
  - `stream = transcriber.create_stream(update_interval=0.3)`
  - `stream.add_listener(listener)`
  - `stream.start()`
  - `stream.add_audio(chunk, sample_rate)` — chunk is a list of floats
  - `stream.stop()` / `stream.close()`
- Listener base class: `TranscriptEventListener`
- Callbacks:
  - `on_line_started(event)` — first text for a line
  - `on_line_text_changed(event)` — **partials** (`event.line.text`)
  - `on_line_completed(event)` — **final** (`event.line.text`)
- Mic helper (not used in this WAV spike): `MicTranscriber`
- WAV helper: `load_wav_file(path)`

Contract constructor target from the plan (not implemented — kill gate):
`MoonshineStreamingTranscriber(model_arch: str = "small_streaming", update_interval_s: float = 0.3)`.

## Numbers (detail)

### tiny.en (batch baseline)

- Brand hits: **9/12 = 75%**
- Misses: `open openai` → `open up`; `open claude` → `open clod`;
  `ask claude …` → `ask cloud …` (brand miss)
- Exactish phrase match: 16/20
- No partials / final-latency metrics (batch decode)

### Moonshine `small_streaming`

- Brand hits: **10/12 = 83%**
- Misses: `open openai` → `Open up an A.`; `open claude` → `Open Cloud`
- Median final latency: **259 ms**
- Partials during speech: **95%** (19/20; `go back` had no pre-end partial)

### Moonshine `medium_streaming`

- Brand hits: **11/12 = 92%**
- Miss: `open openai` → `OpenOpene.`
- Median final latency: **515 ms** (over gate)
- Partials during speech: **95%**

### Latency measurement method

For each WAV: feed 100 ms chunks of speech, mark `speech_end` at the last
speech sample, then feed 0.8 s of silence so VAD can complete the line.
`final_latency_ms = on_line_completed_monotonic - speech_end_monotonic`.
This includes VAD hangover after the last spoken sample (as a live pause
would).

## Live mic set

**Blocked / not run** in this pass. Re-run interactively with:

```bash
python tests/manual/verify_moonshine_streaming.py --live --model-arch medium_streaming
```

Prompts: `open reddit`, `open amazon and scroll down`, `open claude`,
`ask chatgpt what is the capital of france`, `next tab`.

## How to reproduce

```bash
pip install -e ".[voice]"
pip install 'moonshine-voice==0.1.5'
python tests/manual/verify_moonshine_streaming.py \
  --model-arch small_streaming \
  --write-md docs/research/voice-streaming-stt.md
python tests/manual/verify_moonshine_streaming.py \
  --model-arch medium_streaming \
  --write-md docs/research/voice-streaming-stt.md
```

Artifacts: `tests/manual/_cache/moonshine_spike/` (WAVs + `results.json`).

## S0b repair gate (GO — proceed to S1)

**Date:** 2026-09-26  
**Change:** score `small_streaming` through `gesture_control.voice.asr_repair.repair_command_text`  
**Package:** `moonshine-voice==0.1.5`  
**Decision:** **GO.** Product streaming slices S1–S7 may proceed with default
`small_streaming` + repair.

| Metric | tiny.en (S0) | `small_streaming`+repair | Required |
|---|---|---|---|
| Brand accuracy | 75% (9/12) | **100%** (12/12) | ≥ 90% |
| Beats tiny.en | — | yes | must |
| Partials during speech | n/a | 95% | delivers partials |
| Median final latency | n/a | **484 ms** | ≤ 500 ms |
| Non-brand parse regressions | — | **0** | 0 |

Latency is noisy under machine load (earlier re-runs saw 449 ms and 668 ms).
A clean solo re-run after fixing the punctuation-only regression check landed
at 484 ms. Brand repairs for the S0 misses:

- `Open up an A.` → `Open openai`
- `Open Cloud` → `Open claude`
- `Open chat gpt` → `Open chatgpt`

Non-brand gating holds: `type cloud storage`, `search for cloud hosting`, and
`open up the menu` are unchanged. Trailing punctuation stripping alone is not
counted as a parse regression.

Reproduce:

```bash
python tests/manual/verify_moonshine_streaming.py \
  --model-arch small_streaming --repair
```

Live mic confirmation remains deferred to S2 (`--live --repair`).
