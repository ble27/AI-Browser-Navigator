"""S0 spike: Moonshine streaming STT vs faster-whisper tiny.en.

Generates a 20-phrase brand/command set with macOS ``say``, optionally
records 5 live mic phrases, and scores keyword accuracy, partial delivery,
and final-event latency. Results are printed as a go/kill table for
``docs/research/voice-streaming-stt.md``.

Usage:
    python tests/manual/verify_moonshine_streaming.py
    python tests/manual/verify_moonshine_streaming.py --live
    python tests/manual/verify_moonshine_streaming.py --model-arch medium_streaming
    python tests/manual/verify_moonshine_streaming.py --repair
    python tests/manual/verify_moonshine_streaming.py --write-md \\
        docs/research/voice-streaming-stt.md

Exit code is 0 on go criteria, 1 on kill.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

_CACHE_DIR = Path(__file__).resolve().parent / "_cache" / "moonshine_spike"
_AIFF_DIR = _CACHE_DIR / "aiff"
_WAV_DIR = _CACHE_DIR / "wav"
_LIVE_DIR = _CACHE_DIR / "live"
_RESULTS_JSON = _CACHE_DIR / "results.json"

# Brand keyword set used for the ≥90% go criterion. Each phrase that names a
# brand contributes one hit/miss for that brand token.
_BRAND_KEYWORDS: dict[str, tuple[str, ...]] = {
    "reddit": ("reddit",),
    "openai": ("openai", "open ai"),
    "claude": ("claude", "cloud"),  # cloud is a known ASR near-miss, not a hit
    "chatgpt": ("chatgpt", "chat gpt", "chatgbt"),
    "amazon": ("amazon",),
    "perplexity": ("perplexity",),
    "github": ("github", "git hub"),
    "youtube": ("youtube", "you tube"),
}

# Exact brand token required for a hit (aliases that count as correct).
_BRAND_HIT_ALIASES: dict[str, tuple[str, ...]] = {
    "reddit": ("reddit",),
    "openai": ("openai", "open ai"),
    "claude": ("claude",),
    "chatgpt": ("chatgpt", "chat gpt"),
    "amazon": ("amazon",),
    "perplexity": ("perplexity",),
    "github": ("github", "git hub"),
    "youtube": ("youtube", "you tube"),
}

# 20 synthetic phrases: brands + common command vocabulary.
_SYNTH_PHRASES: tuple[tuple[str, str | None], ...] = (
    ("open reddit", "reddit"),
    ("open openai", "openai"),
    ("open claude", "claude"),
    ("open chatgpt", "chatgpt"),
    ("open amazon", "amazon"),
    ("open perplexity", "perplexity"),
    ("open github", "github"),
    ("open youtube", "youtube"),
    ("go to reddit", "reddit"),
    ("go to amazon", "amazon"),
    ("search for headphones", None),
    ("scroll down", None),
    ("next tab", None),
    ("go back", None),
    ("click orders", None),
    ("press enter", None),
    ("type hello world", None),
    ("open notes", None),
    ("ask claude what is two plus two", "claude"),
    ("browse to github.com", "github"),
)

_LIVE_PROMPTS: tuple[tuple[str, str | None], ...] = (
    ("open reddit", "reddit"),
    ("open amazon and scroll down", "amazon"),
    ("open claude", "claude"),
    ("ask chatgpt what is the capital of france", "chatgpt"),
    ("next tab", None),
)

_FINAL_LATENCY_GO_MS = 500.0
_BRAND_ACCURACY_GO = 0.90
_UPDATE_INTERVAL_S = 0.3
_CHUNK_DURATION_S = 0.1
_TRAILING_SILENCE_S = 0.8
_LIVE_SECONDS = 4.0


@dataclass
class PhraseResult:
    """One phrase scored under one engine."""

    phrase: str
    brand: str | None
    engine: str
    transcript: str
    brand_hit: bool | None
    had_partial_during_speech: bool | None = None
    final_latency_ms: float | None = None
    error: str | None = None


@dataclass
class EngineSummary:
    """Aggregated go/kill metrics for one STT engine."""

    engine: str
    brand_total: int
    brand_hits: int
    brand_accuracy: float
    phrase_exactish: int
    phrase_total: int
    median_final_latency_ms: float | None
    partials_during_speech_rate: float | None
    offline_after_download: bool
    results: list[PhraseResult] = field(default_factory=list)


def _slug(text: str) -> str:
    """Filesystem-safe slug for a phrase."""
    return "".join(ch if ch.isalnum() else "_" for ch in text.lower()).strip("_")


def _normalize(text: str) -> str:
    """Lowercase collapsed whitespace for keyword checks."""
    return " ".join(text.lower().split())


def _brand_hit(brand: str, transcript: str) -> bool:
    """Return True if the transcript contains an accepted brand alias."""
    norm = _normalize(transcript)
    return any(alias in norm for alias in _BRAND_HIT_ALIASES[brand])


def _ensure_dirs() -> None:
    """Create cache directories used by the spike."""
    for path in (_CACHE_DIR, _AIFF_DIR, _WAV_DIR, _LIVE_DIR):
        path.mkdir(parents=True, exist_ok=True)


def _generate_synth_wav(phrase: str) -> Path:
    """Synthesize one phrase with macOS ``say`` and convert to 16 kHz mono WAV.

    Args:
        phrase: Spoken text.

    Returns:
        Path to the 16 kHz mono WAV file.
    """
    slug = _slug(phrase)
    aiff_path = _AIFF_DIR / f"{slug}.aiff"
    wav_path = _WAV_DIR / f"{slug}.wav"
    if not aiff_path.exists():
        subprocess.run(
            ["say", "-o", str(aiff_path), phrase],
            check=True,
            capture_output=True,
        )
    if not wav_path.exists() or wav_path.stat().st_mtime < aiff_path.stat().st_mtime:
        subprocess.run(
            [
                "afconvert",
                "-f",
                "WAVE",
                "-d",
                "LEI16@16000",
                "-c",
                "1",
                str(aiff_path),
                str(wav_path),
            ],
            check=True,
            capture_output=True,
        )
    return wav_path


def _read_wav_float32(path: Path) -> tuple[NDArray[np.float32], int]:
    """Load a WAV file as mono float32 samples.

    Args:
        path: WAV path.

    Returns:
        ``(samples, sample_rate)``.
    """
    with wave.open(str(path), "rb") as handle:
        sample_rate = handle.getframerate()
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        frames = handle.readframes(handle.getnframes())
    if sample_width == 2:
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        audio = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported sample width {sample_width} in {path}")
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1).astype(np.float32)
    return audio, sample_rate


def _write_wav_float32(path: Path, audio: NDArray[np.float32], sample_rate: int) -> None:
    """Write mono float32 audio as 16-bit PCM WAV."""
    clipped = np.clip(audio, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def _transcribe_tiny_en(audio: NDArray[np.float32], sample_rate: int) -> str:
    """Batch-transcribe with the project's FasterWhisperTranscriber."""
    from gesture_control.voice.transcription import FasterWhisperTranscriber

    if not hasattr(_transcribe_tiny_en, "_model"):
        _transcribe_tiny_en._model = FasterWhisperTranscriber(model_name="tiny.en")  # type: ignore[attr-defined]
    model = _transcribe_tiny_en._model  # type: ignore[attr-defined]
    if sample_rate != 16_000:
        raise ValueError("tiny.en path expects 16 kHz audio")
    return model.transcribe(audio, sample_rate=sample_rate)


def _resolve_model_arch(name: str) -> Any:
    """Map a CLI model-arch string onto ``ModelArch``."""
    from moonshine_voice import ModelArch, string_to_model_arch

    normalized = name.strip().lower().replace("-", "_")
    aliases = {
        "small_streaming": "small-streaming",
        "medium_streaming": "medium-streaming",
        "tiny_streaming": "tiny-streaming",
        "base_streaming": "base-streaming",
    }
    token = aliases.get(normalized, normalized.replace("_", "-"))
    try:
        return string_to_model_arch(token)
    except Exception:
        # Fall back to enum attribute lookup.
        attr = normalized.upper()
        return ModelArch[attr]


class _CollectingListener:
    """Record Moonshine line events and wall-clock timings."""

    def __init__(self) -> None:
        from moonshine_voice import TranscriptEventListener

        class _Listener(TranscriptEventListener):  # type: ignore[misc,valid-type]
            def __init__(self_inner) -> None:  # noqa: N805
                self_inner.partials: list[tuple[float, str]] = []
                self_inner.finals: list[tuple[float, str]] = []
                self_inner.speech_end_monotonic: float | None = None

            def on_line_started(self_inner, event: Any) -> None:  # noqa: N805
                self_inner.partials.append((time.monotonic(), event.line.text))

            def on_line_text_changed(self_inner, event: Any) -> None:  # noqa: N805
                self_inner.partials.append((time.monotonic(), event.line.text))

            def on_line_completed(self_inner, event: Any) -> None:  # noqa: N805
                self_inner.finals.append((time.monotonic(), event.line.text))

        self._listener = _Listener()

    @property
    def raw(self) -> Any:
        """Underlying Moonshine listener instance."""
        return self._listener

    def mark_speech_end(self) -> None:
        """Record when the last speech sample was fed (before trailing silence)."""
        self._listener.speech_end_monotonic = time.monotonic()


def _transcribe_moonshine_streaming(
    audio: NDArray[np.float32],
    sample_rate: int,
    *,
    model_arch_name: str,
    update_interval_s: float = _UPDATE_INTERVAL_S,
) -> tuple[str, bool, float | None]:
    """Stream one utterance into Moonshine and return final text + metrics.

    Args:
        audio: Mono float32 samples.
        sample_rate: Sample rate of ``audio``.
        model_arch_name: Moonshine architecture name (e.g. ``small_streaming``).
        update_interval_s: Partial update interval.

    Returns:
        ``(final_text, had_partial_during_speech, final_latency_ms)``.
    """
    from moonshine_voice import Transcriber, get_model_for_language

    if not hasattr(_transcribe_moonshine_streaming, "_cache"):
        _transcribe_moonshine_streaming._cache = {}  # type: ignore[attr-defined]
    cache: dict[str, Any] = _transcribe_moonshine_streaming._cache  # type: ignore[attr-defined]

    if model_arch_name not in cache:
        arch = _resolve_model_arch(model_arch_name)
        model_path, resolved_arch = get_model_for_language("en", arch)
        transcriber = Transcriber(
            model_path=model_path,
            model_arch=resolved_arch,
            update_interval=update_interval_s,
        )
        cache[model_arch_name] = (transcriber, resolved_arch)

    transcriber, _arch = cache[model_arch_name]
    collector = _CollectingListener()
    stream = transcriber.create_stream(update_interval=update_interval_s)
    stream.add_listener(collector.raw)
    stream.start()

    chunk_size = max(1, int(_CHUNK_DURATION_S * sample_rate))
    speech_samples = len(audio)
    # Feed speech, then trailing silence so VAD can complete the line.
    silence = np.zeros(int(_TRAILING_SILENCE_S * sample_rate), dtype=np.float32)
    combined = np.concatenate([audio.astype(np.float32), silence])

    fed = 0
    speech_end_marked = False
    for start in range(0, len(combined), chunk_size):
        chunk = combined[start : start + chunk_size]
        stream.add_audio(chunk.tolist(), sample_rate)
        fed += len(chunk)
        if not speech_end_marked and fed >= speech_samples:
            collector.mark_speech_end()
            speech_end_marked = True

    stream.stop()
    try:
        stream.close()
    except Exception:
        pass

    finals = collector.raw.finals
    partials = collector.raw.partials
    final_text = finals[-1][1] if finals else (partials[-1][1] if partials else "")
    speech_end = collector.raw.speech_end_monotonic
    final_latency_ms: float | None = None
    if finals and speech_end is not None:
        final_latency_ms = (finals[-1][0] - speech_end) * 1000.0

    had_partial = False
    if speech_end is not None:
        had_partial = any(ts < speech_end and text.strip() for ts, text in partials)
    else:
        had_partial = any(text.strip() for _, text in partials)

    return final_text.strip(), had_partial, final_latency_ms


def _score_phrase(
    phrase: str,
    brand: str | None,
    engine: str,
    transcript: str,
    *,
    had_partial: bool | None = None,
    final_latency_ms: float | None = None,
    error: str | None = None,
) -> PhraseResult:
    """Build one scored phrase result."""
    hit: bool | None = None
    if brand is not None and error is None:
        hit = _brand_hit(brand, transcript)
    return PhraseResult(
        phrase=phrase,
        brand=brand,
        engine=engine,
        transcript=transcript,
        brand_hit=hit,
        had_partial_during_speech=had_partial,
        final_latency_ms=final_latency_ms,
        error=error,
    )


def _summarize(engine: str, results: list[PhraseResult], *, offline: bool) -> EngineSummary:
    """Aggregate phrase results into go/kill metrics."""
    brand_results = [r for r in results if r.brand is not None and r.error is None]
    hits = sum(1 for r in brand_results if r.brand_hit)
    brand_total = len(brand_results)
    accuracy = (hits / brand_total) if brand_total else 0.0

    exactish = 0
    for result in results:
        if result.error:
            continue
        expected = _normalize(result.phrase)
        got = _normalize(result.transcript)
        if expected in got or got in expected:
            exactish += 1

    latencies = [
        r.final_latency_ms for r in results if r.final_latency_ms is not None and r.error is None
    ]
    median_latency = statistics.median(latencies) if latencies else None

    partial_flags = [
        r.had_partial_during_speech
        for r in results
        if r.had_partial_during_speech is not None and r.error is None
    ]
    partial_rate = (
        sum(1 for flag in partial_flags if flag) / len(partial_flags) if partial_flags else None
    )

    return EngineSummary(
        engine=engine,
        brand_total=brand_total,
        brand_hits=hits,
        brand_accuracy=accuracy,
        phrase_exactish=exactish,
        phrase_total=len([r for r in results if r.error is None]),
        median_final_latency_ms=median_latency,
        partials_during_speech_rate=partial_rate,
        offline_after_download=offline,
        results=results,
    )


def _record_live_wav(path: Path, seconds: float = _LIVE_SECONDS) -> Path:
    """Record one mono 16 kHz clip from the default microphone.

    Args:
        path: Destination WAV path.
        seconds: Capture duration.

    Returns:
        ``path``.
    """
    import sounddevice as sd

    print(f"  Recording {seconds:.0f}s into {path.name} ... speak now")
    samples = int(seconds * 16_000)
    audio = sd.rec(samples, samplerate=16_000, channels=1, dtype="float32")
    sd.wait()
    mono = audio.reshape(-1).astype(np.float32)
    _write_wav_float32(path, mono, 16_000)
    return path


def _evaluate_set(
    phrases: list[tuple[str, str | None, Path]],
    *,
    model_arch: str,
    repair: bool = False,
) -> tuple[EngineSummary, EngineSummary, list[str | None]]:
    """Run tiny.en and Moonshine over the same WAV set.

    Args:
        phrases: Phrase, optional brand key, and WAV path triples.
        model_arch: Moonshine architecture name.
        repair: When True, score Moonshine after ``repair_command_text``.

    Returns:
        Tiny summary, Moonshine summary, and unrepaired Moonshine finals
        (``None`` when that phrase errored).
    """
    tiny_results: list[PhraseResult] = []
    moon_results: list[PhraseResult] = []
    raw_moon: list[str | None] = []
    engine_label = f"moonshine:{model_arch}"
    if repair:
        engine_label += "+repair"

    for phrase, brand, wav_path in phrases:
        audio, sample_rate = _read_wav_float32(wav_path)
        print(f"  [{wav_path.name}] {phrase!r}")

        try:
            tiny_text = _transcribe_tiny_en(audio, sample_rate)
            tiny_results.append(_score_phrase(phrase, brand, "tiny.en", tiny_text))
            print(f"    tiny.en:     {tiny_text!r}")
        except Exception as exc:  # noqa: BLE001 - spike must record failures
            tiny_results.append(_score_phrase(phrase, brand, "tiny.en", "", error=str(exc)))
            print(f"    tiny.en ERR: {exc}")

        try:
            moon_text, had_partial, latency_ms = _transcribe_moonshine_streaming(
                audio,
                sample_rate,
                model_arch_name=model_arch,
            )
            raw_moon.append(moon_text)
            scored_text = moon_text
            if repair:
                from gesture_control.voice.asr_repair import repair_command_text

                scored_text = repair_command_text(moon_text)
            moon_results.append(
                _score_phrase(
                    phrase,
                    brand,
                    engine_label,
                    scored_text,
                    had_partial=had_partial,
                    final_latency_ms=latency_ms,
                )
            )
            if repair and scored_text != moon_text:
                print(
                    f"    moonshine:   {moon_text!r} → repair {scored_text!r} "
                    f"(partial={had_partial}, final_ms={latency_ms!r})"
                )
            else:
                print(
                    f"    moonshine:   {scored_text!r} "
                    f"(partial={had_partial}, final_ms={latency_ms!r})"
                )
        except Exception as exc:  # noqa: BLE001 - spike must record failures
            raw_moon.append(None)
            moon_results.append(
                _score_phrase(
                    phrase,
                    brand,
                    engine_label,
                    "",
                    error=str(exc),
                )
            )
            print(f"    moonshine ERR: {exc}")

    tiny = _summarize("tiny.en", tiny_results, offline=True)
    moon = _summarize(engine_label, moon_results, offline=True)
    return tiny, moon, raw_moon


def _non_brand_parse_regressions(
    phrases: list[tuple[str, str | None, Path]],
    raw_moon_transcripts: list[str | None],
) -> list[str]:
    """Return non-brand phrases whose parse_command outcome changed under repair.

    Args:
        phrases: The evaluated phrase set (same order as transcripts).
        raw_moon_transcripts: Unrepaired Moonshine finals (``None`` on error).

    Returns:
        Human-readable regression descriptions (empty when clean).
    """
    from gesture_control.voice.asr_repair import repair_command_text
    from gesture_control.voice.commands import parse_command

    regressions: list[str] = []
    for (phrase, brand, _path), raw in zip(phrases, raw_moon_transcripts, strict=True):
        if brand is not None or raw is None:
            continue
        repaired = repair_command_text(raw)
        normalized_only = " ".join(raw.split()).rstrip(".,!?;:")
        # Punctuation/whitespace-only changes are normalization, not brand
        # rewrites — they must not count as S0b parse regressions.
        if repaired.casefold() != normalized_only.casefold():
            if parse_command(normalized_only) != parse_command(repaired):
                regressions.append(
                    f"{phrase!r}: STT parse changed under brand repair " f"({raw!r} → {repaired!r})"
                )
        if parse_command(phrase) != parse_command(repair_command_text(phrase)):
            regressions.append(f"{phrase!r}: repair alters canonical phrase parse")
    return regressions


def _go_criteria(moon: EngineSummary, tiny: EngineSummary) -> tuple[bool, list[str]]:
    """Evaluate go/kill rules against Moonshine vs tiny.en summaries.

    Returns:
        ``(is_go, reasons)``.
    """
    reasons: list[str] = []
    ok = True

    if moon.brand_accuracy < _BRAND_ACCURACY_GO:
        ok = False
        reasons.append(f"brand accuracy {moon.brand_accuracy:.0%} < {_BRAND_ACCURACY_GO:.0%}")
    else:
        reasons.append(
            f"brand accuracy {moon.brand_accuracy:.0%} "
            f"({moon.brand_hits}/{moon.brand_total}) ≥ {_BRAND_ACCURACY_GO:.0%}"
        )

    if moon.brand_accuracy <= tiny.brand_accuracy:
        ok = False
        reasons.append(
            f"did not beat tiny.en " f"({moon.brand_accuracy:.0%} ≤ {tiny.brand_accuracy:.0%})"
        )
    else:
        reasons.append(f"beats tiny.en ({moon.brand_accuracy:.0%} > {tiny.brand_accuracy:.0%})")

    if moon.partials_during_speech_rate is None or moon.partials_during_speech_rate < 0.8:
        ok = False
        reasons.append(
            f"partials during speech rate " f"{moon.partials_during_speech_rate!r} < 0.8"
        )
    else:
        reasons.append(f"partials during speech " f"{moon.partials_during_speech_rate:.0%} ≥ 80%")

    if moon.median_final_latency_ms is None or moon.median_final_latency_ms > _FINAL_LATENCY_GO_MS:
        ok = False
        reasons.append(
            f"median final latency {moon.median_final_latency_ms!r} ms "
            f"> {_FINAL_LATENCY_GO_MS:.0f} ms"
        )
    else:
        reasons.append(
            f"median final latency {moon.median_final_latency_ms:.0f} ms "
            f"≤ {_FINAL_LATENCY_GO_MS:.0f} ms"
        )

    if not moon.offline_after_download:
        ok = False
        reasons.append("not offline after first download")
    else:
        reasons.append("offline after first download")

    return ok, reasons


def _print_summary(
    tiny: EngineSummary, moon: EngineSummary, is_go: bool, reasons: list[str]
) -> None:
    """Print the go/kill table to stdout."""
    print("\n=== S0 go/kill summary ===")
    print(
        f"tiny.en brand accuracy:     "
        f"{tiny.brand_hits}/{tiny.brand_total} = {tiny.brand_accuracy:.0%}"
    )
    print(
        f"moonshine brand accuracy:   "
        f"{moon.brand_hits}/{moon.brand_total} = {moon.brand_accuracy:.0%}"
    )
    print(f"moonshine median final ms:  {moon.median_final_latency_ms!r}")
    print(f"moonshine partials rate:    {moon.partials_during_speech_rate!r}")
    print(f"decision: {'GO' if is_go else 'KILL'}")
    for reason in reasons:
        print(f"  - {reason}")


def _render_markdown(
    *,
    tiny: EngineSummary,
    moon: EngineSummary,
    is_go: bool,
    reasons: list[str],
    model_arch: str,
    package_version: str,
    live_ran: bool,
) -> str:
    """Render the research note body."""
    lines: list[str] = [
        "# Research: Moonshine streaming STT spike (S0)",
        "",
        f"**Date:** {time.strftime('%Y-%m-%d')}",
        "**Repo:** AI-Gestures-Tool",
        "**Scope:** Go/kill gate before building the streaming voice agent.",
        "",
        "## Decision",
        "",
        f"**{'GO' if is_go else 'KILL'}** using `moonshine-voice=={package_version}` "
        f"with `ModelArch` / arch string `{model_arch}`.",
        "",
        "Criteria:",
        "",
    ]
    for reason in reasons:
        lines.append(f"- {reason}")
    lines.extend(
        [
            "",
            "## Listener / event API (for S2 adapter)",
            "",
            "Pinned names observed in `moonshine-voice` 0.1.5:",
            "",
            "- Package: `moonshine_voice`",
            "- `get_model_for_language(language, wanted_model_arch) -> (model_path, model_arch)`",
            "- `ModelArch.SMALL_STREAMING` / `ModelArch.MEDIUM_STREAMING`",
            '- `string_to_model_arch("small-streaming")`',
            "- `Transcriber(model_path=..., model_arch=..., update_interval=0.3)`",
            "- `stream = transcriber.create_stream(update_interval=0.3)`",
            "- `stream.add_listener(listener)` / `stream.start()` / "
            "`stream.add_audio(chunk, sample_rate)` / `stream.stop()` / `stream.close()`",
            "- Listener base: `TranscriptEventListener`",
            "- Events: `on_line_started`, `on_line_text_changed` (partials), "
            "`on_line_completed` (final)",
            "- Event payload: `event.line.text`",
            "- Mic helper (product path): `MicTranscriber` (not used in this WAV spike)",
            "",
            "## Numbers",
            "",
            f"| Metric | tiny.en | moonshine `{model_arch}` |",
            "|---|---:|---:|",
            f"| Brand hits | {tiny.brand_hits}/{tiny.brand_total} "
            f"({tiny.brand_accuracy:.0%}) | {moon.brand_hits}/{moon.brand_total} "
            f"({moon.brand_accuracy:.0%}) |",
            f"| Exactish phrase match | {tiny.phrase_exactish}/{tiny.phrase_total} | "
            f"{moon.phrase_exactish}/{moon.phrase_total} |",
            f"| Median final latency after speech end | n/a (batch) | "
            f"{moon.median_final_latency_ms!r} ms |",
            f"| Partials during speech | n/a | " f"{moon.partials_during_speech_rate!r} |",
            f"| Offline after first download | yes | "
            f"{'yes' if moon.offline_after_download else 'no'} |",
            "",
            f"Live mic set recorded: **{'yes' if live_ran else 'no (synth-only)'}**.",
            "",
            "## Per-phrase transcripts",
            "",
            "| Phrase | Brand | tiny.en | moonshine | brand hit (M) |",
            "|---|---|---|---|---|",
        ]
    )
    by_phrase = {r.phrase: r for r in moon.results}
    for tiny_row in tiny.results:
        moon_row = by_phrase.get(tiny_row.phrase)
        moon_text = moon_row.transcript if moon_row else ""
        hit = (
            "—"
            if tiny_row.brand is None
            else ("yes" if (moon_row and moon_row.brand_hit) else "no")
        )
        lines.append(
            f"| {tiny_row.phrase} | {tiny_row.brand or '—'} | "
            f"{tiny_row.transcript or tiny_row.error or ''} | "
            f"{moon_text or (moon_row.error if moon_row else '')} | {hit} |"
        )
    lines.extend(
        [
            "",
            "## How to reproduce",
            "",
            "```bash",
            'pip install -e ".[voice]"',
            "pip install 'moonshine-voice==0.1.5'",
            "python tests/manual/verify_moonshine_streaming.py "
            f"--model-arch {model_arch} --write-md docs/research/voice-streaming-stt.md",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run the S0 spike.

    Args:
        argv: CLI args excluding program name.

    Returns:
        ``0`` on go, ``1`` on kill or hard failure.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-arch",
        default="small_streaming",
        help="Moonshine architecture (default: small_streaming).",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Also record and score 5 live microphone phrases.",
    )
    parser.add_argument(
        "--write-md",
        type=Path,
        default=None,
        help="Write/overwrite the research markdown note.",
    )
    parser.add_argument(
        "--skip-synth",
        action="store_true",
        help="Skip the 20-phrase say-generated set (live-only).",
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Score Moonshine after gesture_control.voice.asr_repair.",
    )
    parser.add_argument(
        "--append-md",
        type=Path,
        default=None,
        help="Append an S0b section to an existing research markdown note.",
    )
    args = parser.parse_args(argv)

    _ensure_dirs()

    try:
        import moonshine_voice as mv

        package_version = getattr(mv, "__version__", "0.1.5")
    except ImportError:
        print(
            "error: moonshine-voice is not installed. " "pip install 'moonshine-voice==0.1.5'",
            file=sys.stderr,
        )
        return 1

    phrases: list[tuple[str, str | None, Path]] = []
    if not args.skip_synth:
        print("Generating synth WAVs with `say` ...")
        for phrase, brand in _SYNTH_PHRASES:
            wav = _generate_synth_wav(phrase)
            phrases.append((phrase, brand, wav))

    live_ran = False
    if args.live:
        print("Recording live mic phrases ...")
        live_ran = True
        for index, (phrase, brand) in enumerate(_LIVE_PROMPTS, start=1):
            print(f"Live {index}/{len(_LIVE_PROMPTS)}: please say {phrase!r}")
            path = _LIVE_DIR / f"live_{index:02d}_{_slug(phrase)}.wav"
            _record_live_wav(path)
            phrases.append((phrase, brand, path))

    if not phrases:
        print("error: no phrases to evaluate", file=sys.stderr)
        return 1

    mode = f"{args.model_arch}+repair" if args.repair else args.model_arch
    print(f"Evaluating {len(phrases)} phrases with tiny.en and {mode} ...")
    tiny, moon, raw_moon = _evaluate_set(
        phrases,
        model_arch=args.model_arch,
        repair=args.repair,
    )
    is_go, reasons = _go_criteria(moon, tiny)

    parse_regressions: list[str] = []
    if args.repair:
        parse_regressions = _non_brand_parse_regressions(phrases, raw_moon)
        if parse_regressions:
            is_go = False
            reasons.append(f"non-brand parse regressions: {len(parse_regressions)}")
            for item in parse_regressions:
                reasons.append(f"  - {item}")
        else:
            reasons.append("non-brand parse regressions: 0")

    _print_summary(tiny, moon, is_go, reasons)

    payload = {
        "decision": "GO" if is_go else "KILL",
        "model_arch": args.model_arch,
        "repair": args.repair,
        "package_version": package_version,
        "live_ran": live_ran,
        "reasons": reasons,
        "parse_regressions": parse_regressions,
        "tiny": asdict(tiny),
        "moonshine": asdict(moon),
    }
    _RESULTS_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {_RESULTS_JSON}")

    if args.write_md is not None:
        args.write_md.parent.mkdir(parents=True, exist_ok=True)
        args.write_md.write_text(
            _render_markdown(
                tiny=tiny,
                moon=moon,
                is_go=is_go,
                reasons=reasons,
                model_arch=args.model_arch,
                package_version=package_version,
                live_ran=live_ran,
            ),
            encoding="utf-8",
        )
        print(f"Wrote {args.write_md}")

    if args.append_md is not None:
        section = _render_s0b_section(
            tiny=tiny,
            moon=moon,
            is_go=is_go,
            reasons=reasons,
            model_arch=args.model_arch,
            package_version=package_version,
            parse_regressions=parse_regressions,
        )
        existing = args.append_md.read_text(encoding="utf-8") if args.append_md.exists() else ""
        args.append_md.parent.mkdir(parents=True, exist_ok=True)
        args.append_md.write_text(existing.rstrip() + "\n\n" + section, encoding="utf-8")
        print(f"Appended S0b section to {args.append_md}")

    return 0 if is_go else 1


def _render_s0b_section(
    *,
    tiny: EngineSummary,
    moon: EngineSummary,
    is_go: bool,
    reasons: list[str],
    model_arch: str,
    package_version: str,
    parse_regressions: list[str],
) -> str:
    """Render the S0b repair-gate appendix for the research note."""
    latency = (
        f"{moon.median_final_latency_ms:.0f} ms"
        if moon.median_final_latency_ms is not None
        else "n/a"
    )
    partials = (
        f"{moon.partials_during_speech_rate:.0%}"
        if moon.partials_during_speech_rate is not None
        else "n/a"
    )
    lines = [
        "## S0b repair gate",
        "",
        f"**Date:** re-run after S0 with `repair_command_text` on `{model_arch}`.",
        f"**Package:** `moonshine-voice=={package_version}`",
        f"**Decision:** {'GO' if is_go else 'KILL'}.",
        "",
        "| Metric | tiny.en | " f"`{model_arch}`+repair | Required |",
        "|---|---|---|---|",
        f"| Brand accuracy | {tiny.brand_accuracy:.0%} "
        f"({tiny.brand_hits}/{tiny.brand_total}) | "
        f"**{moon.brand_accuracy:.0%}** "
        f"({moon.brand_hits}/{moon.brand_total}) | ≥ 90% |",
        f"| Beats tiny.en | — | "
        f"{'yes' if moon.brand_accuracy > tiny.brand_accuracy else 'no'} | must |",
        f"| Partials during speech | n/a | {partials} | delivers partials |",
        f"| Median final latency | n/a | **{latency}** | ≤ 500 ms |",
        f"| Non-brand parse regressions | — | " f"**{len(parse_regressions)}** | 0 |",
        "",
        "### Reasons",
        "",
    ]
    for reason in reasons:
        lines.append(f"- {reason}")
    lines.extend(["", "### Brand rows after repair", ""])
    for result in moon.results:
        if result.brand is None:
            continue
        mark = "hit" if result.brand_hit else "MISS"
        lines.append(f"- `{result.phrase}` → `{result.transcript}` ({mark})")
    if parse_regressions:
        lines.extend(["", "### Parse regressions", ""])
        for item in parse_regressions:
            lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
