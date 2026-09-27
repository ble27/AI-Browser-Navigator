"""Unit tests for :class:`DeterministicClauseSegmenter`."""

from __future__ import annotations

from gesture_control.voice.segmenter import DeterministicClauseSegmenter
from gesture_control.voice.stream_contracts import TranscriptEvent, TranscriptEventKind


def _partial(line_id: int, text: str, at_s: float) -> TranscriptEvent:
    return TranscriptEvent(TranscriptEventKind.PARTIAL, text, line_id, at_s)


def _final(line_id: int, text: str, at_s: float = 1.0) -> TranscriptEvent:
    return TranscriptEvent(TranscriptEventKind.FINAL, text, line_id, at_s)


def test_final_commits_single_clause() -> None:
    segmenter = DeterministicClauseSegmenter()
    clauses = segmenter.feed(_final(0, "open reddit"))
    assert len(clauses) == 1
    assert clauses[0].text == "open reddit"
    assert clauses[0].final is True


def test_partial_stable_and_commits_before_final() -> None:
    segmenter = DeterministicClauseSegmenter()
    assert segmenter.feed(_partial(0, "open amazon and", 0.1)) == []
    committed = segmenter.feed(_partial(0, "open amazon and scr", 0.2))
    assert len(committed) == 1
    assert committed[0].text == "open amazon"
    assert committed[0].final is False


def test_revision_resets_stability() -> None:
    segmenter = DeterministicClauseSegmenter()
    segmenter.feed(_partial(0, "open amazing and", 0.1))
    segmenter.feed(_partial(0, "open amazon and", 0.2))
    committed = segmenter.feed(_partial(0, "open amazon and", 0.3))
    assert len(committed) == 1
    assert committed[0].text == "open amazon"


def test_no_duplicate_line_index() -> None:
    segmenter = DeterministicClauseSegmenter()
    segmenter.feed(_partial(0, "open amazon and", 0.1))
    segmenter.feed(_partial(0, "open amazon and", 0.2))
    segmenter.feed(_final(0, "open amazon and scroll down"))
    all_texts = [c.text for c in segmenter.feed(_final(0, "open amazon and scroll down"))]
    assert all_texts == []


def test_text_verb_keeps_and_literal() -> None:
    segmenter = DeterministicClauseSegmenter()
    clauses = segmenter.feed(
        _final(0, "type buy milk and eggs then press enter"),
    )
    texts = [clause.text for clause in clauses]
    assert texts == ["type buy milk and eggs", "press enter"]
