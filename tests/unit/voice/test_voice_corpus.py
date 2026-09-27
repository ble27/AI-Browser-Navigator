"""Tests for the real-voice corpus helpers."""

from __future__ import annotations

from pathlib import Path

from gesture_control.voice.voice_corpus import (
    CORPUS_PROMPTS,
    CorpusEntry,
    brand_hit,
    load_corpus_manifest,
    write_corpus_manifest,
)


def test_corpus_prompts_cover_brands_and_controls() -> None:
    assert len(CORPUS_PROMPTS) >= 20
    brands = {brand for _phrase, brand in CORPUS_PROMPTS if brand}
    assert {"reddit", "amazon", "claude", "chatgpt"}.issubset(brands)


def test_brand_hit_and_manifest_roundtrip(tmp_path: Path) -> None:
    assert brand_hit("open claude", "claude") is True
    assert brand_hit("open cloud", "claude") is False
    assert brand_hit("next tab", None) is None

    entries = [
        CorpusEntry(
            index=1,
            expected="open claude",
            brand="claude",
            wav_path="a.wav",
            raw_transcript="Open Cloud",
            repaired_transcript="Open claude",
            brand_hit=True,
            had_partial=True,
            final_latency_ms=200.0,
        ),
    ]
    path = tmp_path / "manifest.json"
    report = write_corpus_manifest(path, entries)
    assert report.passes_gate
    loaded = load_corpus_manifest(path)
    assert loaded.brand_hits == 1
    assert loaded.entries[0].expected == "open claude"
