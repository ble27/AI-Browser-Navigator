"""Deterministic clause segmentation for streaming voice transcripts."""

from __future__ import annotations

import inspect

from gesture_control.voice.stream_contracts import (
    STABLE_PARTIALS_TO_COMMIT,
    Clause,
    TranscriptEvent,
    TranscriptEventKind,
)

_DELIMITERS = (" and ", " then ", ", then ", "; ")
_THEN_ONLY = (" then ",)
_TEXT_VERB_PREFIXES = ("type ", "write ", "ask ", "query ", "search ")


def _clause_delimiters(clause_text: str) -> tuple[str, ...]:
    """Return delimiters that may end ``clause_text`` when splitting a line."""
    folded = clause_text.casefold().lstrip()
    if any(folded.startswith(prefix) for prefix in _TEXT_VERB_PREFIXES):
        return _THEN_ONLY
    return _DELIMITERS


def _find_next_delimiter(text: str, start: int) -> tuple[int, int] | None:
    """Return ``(delimiter_start, delimiter_end)`` for the earliest delimiter."""
    best: tuple[int, int] | None = None
    clause_start_text = text[start:]
    for delimiter in _clause_delimiters(clause_start_text):
        index = text.casefold().find(delimiter, start)
        if index == -1:
            continue
        end = index + len(delimiter)
        if best is None or index < best[0]:
            best = (index, end)
    return best


def _split_complete_clauses(text: str) -> tuple[list[str], str]:
    """Split ``text`` into delimited complete clauses and a trailing fragment."""
    clauses: list[str] = []
    position = 0
    while position < len(text):
        match = _find_next_delimiter(text, position)
        if match is None:
            break
        start, end = match
        clause = text[position:start].strip()
        if clause:
            clauses.append(clause)
        position = end
    tail = text[position:].strip()
    return clauses, tail


class DeterministicClauseSegmenter:
    """Commit clauses from partial stability or a final line event."""

    def __init__(self) -> None:
        """Create an empty segmenter."""
        self._committed: set[tuple[int, int]] = set()
        self._stable_counts: dict[tuple[int, int], int] = {}
        self._last_clause_text: dict[tuple[int, int], str] = {}

    def feed(self, event: TranscriptEvent) -> list[Clause]:
        """Consume one transcript event and return newly committed clauses."""
        text = " ".join(event.text.split())
        if not text:
            return []

        if event.kind is TranscriptEventKind.FINAL:
            return self._commit_final(event.line_id, text)

        partial_text = text if text.endswith(" ") else f"{text} "
        complete, tail = _split_complete_clauses(partial_text)
        # Require the next clause to have started before committing from a
        # partial. Otherwise a mid-utterance false "and" (e.g. "Open terms and"
        # while revising toward "Open terminal") locks the wrong clause and the
        # final line is skipped as a duplicate index.
        if not tail:
            return []
        emitted: list[Clause] = []
        for index, clause_text in enumerate(complete):
            key = (event.line_id, index)
            if key in self._committed:
                continue
            previous = self._last_clause_text.get(key)
            if previous == clause_text:
                self._stable_counts[key] = self._stable_counts.get(key, 1) + 1
            else:
                self._last_clause_text[key] = clause_text
                self._stable_counts[key] = 1
            if self._stable_counts[key] >= STABLE_PARTIALS_TO_COMMIT:
                emitted.append(self._emit(key, clause_text, final=False))
        return emitted

    def _commit_final(self, line_id: int, text: str) -> list[Clause]:
        """Commit every clause in a finalized spoken line."""
        complete, tail = _split_complete_clauses(text)
        if tail:
            complete.append(tail)
        emitted: list[Clause] = []
        for index, clause_text in enumerate(complete):
            key = (line_id, index)
            if key in self._committed:
                continue
            emitted.append(self._emit(key, clause_text, final=True))
        return emitted

    def _emit(self, key: tuple[int, int], clause_text: str, *, final: bool) -> Clause:
        """Record one committed clause and return it."""
        self._committed.add(key)
        line_id, index = key
        return Clause(text=clause_text, line_id=line_id, index=index, final=final)


DeterministicClauseSegmenter.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
    [inspect.Parameter("self", inspect.Parameter.POSITIONAL_OR_KEYWORD)],
)
