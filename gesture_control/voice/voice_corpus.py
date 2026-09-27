"""Real-voice corpus helpers for the streaming STT accuracy gate (S3b)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

# Held-out / expandable live prompts for brand + command coverage.
# Brand key is the substring that must appear in the repaired transcript.
CORPUS_PROMPTS: tuple[tuple[str, str | None], ...] = (
    ("open reddit", "reddit"),
    ("open amazon", "amazon"),
    ("open claude", "claude"),
    ("open chatgpt", "chatgpt"),
    ("open openai", "openai"),
    ("open gemini", "gemini"),
    ("open github", "github"),
    ("open youtube", "youtube"),
    ("open perplexity", "perplexity"),
    ("go to amazon", "amazon"),
    ("browse to github.com", "github"),
    ("open amazon and scroll down", "amazon"),
    ("open notes", None),
    ("next tab", None),
    ("previous tab", None),
    ("close tab", None),
    ("scroll down", None),
    ("go back", None),
    ("press enter", None),
    ("type hello world", None),
    ("search for headphones", None),
    ("click orders", None),
    ("ask claude what is two plus two", "claude"),
    ("ask chatgpt what is the capital of france", "chatgpt"),
    ("cancel", None),
)


@dataclass(frozen=True, slots=True)
class CorpusEntry:
    """One recorded utterance and its scoring fields."""

    index: int
    expected: str
    brand: str | None
    wav_path: str
    raw_transcript: str
    repaired_transcript: str
    brand_hit: bool | None
    had_partial: bool
    final_latency_ms: float | None


@dataclass(frozen=True, slots=True)
class CorpusReport:
    """Aggregate brand-accuracy report for a recorded corpus."""

    entries: tuple[CorpusEntry, ...]
    brand_total: int
    brand_hits: int
    brand_accuracy: float

    @property
    def passes_gate(self) -> bool:
        """Return whether brand accuracy clears the 90% live gate."""
        return self.brand_total > 0 and self.brand_accuracy >= 0.90


def brand_hit(repaired: str, brand: str | None) -> bool | None:
    """Score whether ``repaired`` contains the expected brand token."""
    if brand is None:
        return None
    return brand.casefold() in repaired.casefold()


def write_corpus_manifest(path: Path, entries: list[CorpusEntry]) -> CorpusReport:
    """Write ``manifest.json`` and return the aggregate report.

    Args:
        path: Destination JSON path (parent dirs created as needed).
        entries: Recorded corpus rows.

    Returns:
        Aggregate :class:`CorpusReport`.
    """
    brand_total = sum(1 for entry in entries if entry.brand is not None)
    brand_hits = sum(1 for entry in entries if entry.brand_hit is True)
    accuracy = (brand_hits / brand_total) if brand_total else 0.0
    report = CorpusReport(
        entries=tuple(entries),
        brand_total=brand_total,
        brand_hits=brand_hits,
        brand_accuracy=accuracy,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "brand_total": report.brand_total,
        "brand_hits": report.brand_hits,
        "brand_accuracy": report.brand_accuracy,
        "passes_gate": report.passes_gate,
        "entries": [asdict(entry) for entry in entries],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return report


def load_corpus_manifest(path: Path) -> CorpusReport:
    """Load a previously written corpus manifest."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = [CorpusEntry(**row) for row in payload["entries"]]
    return CorpusReport(
        entries=tuple(entries),
        brand_total=int(payload["brand_total"]),
        brand_hits=int(payload["brand_hits"]),
        brand_accuracy=float(payload["brand_accuracy"]),
    )
