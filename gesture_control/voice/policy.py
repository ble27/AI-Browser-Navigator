"""Local wait/act policy for streaming voice clauses (jev-inspired, offline)."""

from __future__ import annotations

from enum import StrEnum

from gesture_control.actions import IntentType
from gesture_control.voice.stream_contracts import (
    CancelStep,
    Clause,
    PageStep,
    ResolvedStep,
    Step,
)

# Decision latency budgets (seconds).
# Nav/tab commands use a shorter debounce so they feel closer to jev (~100 ms).
PARTIAL_DEBOUNCE_S = 0.2
FAST_CLOSED_DEBOUNCE_S = 0.1
FREE_TEXT_SILENCE_S = 0.6
# Bare "type …" / "write …" commits once the words stop changing. Short enough
# that dictation does not wait out Chrome's final result, long enough to avoid
# cutting a word in half. Users who pause while speaking can choose the longer
# free-text window from the pill settings.
TYPE_COMMAND_SILENCE_S = 0.2

_FILLER = frozenset(
    {
        "okay",
        "ok",
        "you",
        "uh",
        "um",
        "uhm",
        "hullo",
        "hello",
        "hey",
        "yeah",
        "yes",
        "yep",
        "no",
        "nope",
        "hmm",
        "hm",
        "ah",
        "oh",
    }
)

_CLOSED_INTENT_TYPES = frozenset(
    {
        IntentType.OPEN_URL,
        IntentType.OPEN_APP,
        IntentType.PRESS_KEY,
        IntentType.SCROLL,
        IntentType.NEXT_TAB,
        IntentType.PREVIOUS_TAB,
        IntentType.NEW_TAB,
        IntentType.CLOSE_TAB,
        IntentType.GO_BACK,
        IntentType.GO_FORWARD,
        IntentType.RELOAD_PAGE,
        IntentType.REOPEN_TAB,
    }
)

# Short browser controls: act on the first grammar-complete partial (no brand
# revision risk). Open-site/app still want a second stable partial.
_FAST_CLOSED_INTENT_TYPES = frozenset(
    {
        IntentType.PRESS_KEY,
        IntentType.SCROLL,
        IntentType.NEXT_TAB,
        IntentType.PREVIOUS_TAB,
        IntentType.NEW_TAB,
        IntentType.CLOSE_TAB,
        IntentType.GO_BACK,
        IntentType.GO_FORWARD,
        IntentType.RELOAD_PAGE,
        IntentType.REOPEN_TAB,
    }
)

_FREE_TEXT_INTENT_TYPES = frozenset(
    {
        IntentType.TYPE_FOCUSED,
        IntentType.SEARCH_WEB,
    }
)

_CLAUSE_DELIMITER_MARKERS = (" and ", " then ", ", then ", "; ")


class PolicyDecision(StrEnum):
    """Whether a planned step should run now, wait, or be dropped."""

    IGNORE = "ignore"
    WAIT = "wait"
    ACT = "act"


def is_filler_text(text: str) -> bool:
    """Return True when ``text`` is a lone acknowledgement / non-command.

    Args:
        text: Clause or transcript text.

    Returns:
        Whether the text should be ignored without planning.
    """
    collapsed = " ".join(text.split()).casefold().strip(".,!?;:")
    return not collapsed or collapsed in _FILLER


def has_clause_delimiter(text: str) -> bool:
    """Return whether ``text`` already contains a clause split marker."""
    padded = f" {text.casefold()} "
    return any(marker in padded for marker in _CLAUSE_DELIMITER_MARKERS)


def _is_free_text_step(step: Step) -> bool:
    """Return whether ``step`` carries a free-text payload that should wait."""
    if isinstance(step, ResolvedStep):
        return step.intent.kind in _FREE_TEXT_INTENT_TYPES
    if isinstance(step, PageStep):
        if step.fallback is not None and step.fallback.kind in _FREE_TEXT_INTENT_TYPES:
            return True
        # Bare page clicks/focus: wait for a complete clause.
        return True
    return False


def partition_steps(steps: list[Step]) -> tuple[list[Step], list[Step]]:
    """Split steps into immediate (closed-set) and deferred (free-text) lists.

    Ask macros become open-now + type/enter-later: once a free-text step
    appears, every following step in the same plan stays deferred so enter
    cannot race ahead of typing. Bare page clicks wait until the clause is
    complete so partial junk does not resolve against the page.

    Args:
        steps: Planner output for one clause.

    Returns:
        ``(immediate, deferred)`` step lists (either may be empty).
    """
    immediate: list[Step] = []
    deferred: list[Step] = []
    seen_free = False
    for step in steps:
        if isinstance(step, CancelStep):
            immediate.append(step)
            continue
        if _is_free_text_step(step):
            seen_free = True
            deferred.append(step)
            continue
        if seen_free:
            deferred.append(step)
            continue
        if isinstance(step, ResolvedStep) and step.intent.kind in _CLOSED_INTENT_TYPES:
            immediate.append(step)
        else:
            deferred.append(step)
    return immediate, deferred


def is_type_only_steps(steps: list[Step]) -> bool:
    """Return whether every step is dictation into a field.

    Ask macros include a following Enter and are not type-only, so they keep
    the longer free-text wait.

    Args:
        steps: Planner output for one clause.

    Returns:
        True when committing early cannot press Enter ahead of the text.
    """
    if not steps:
        return False
    for step in steps:
        if isinstance(step, ResolvedStep) and step.intent.kind in {
            IntentType.TYPE_FOCUSED,
            IntentType.TYPE_TEXT,
        }:
            continue
        if isinstance(step, PageStep) and step.phrase.casefold().lstrip().startswith(
            ("type ", "write ")
        ):
            continue
        return False
    return True


def is_fast_closed_steps(steps: list[Step]) -> bool:
    """Return True when every step is a low-risk closed control (tabs, scroll).

    Args:
        steps: Planner output for one clause.

    Returns:
        Whether the plan is safe to fire on the first complete partial.
    """
    if not steps:
        return False
    for step in steps:
        if isinstance(step, CancelStep):
            continue
        if not isinstance(step, ResolvedStep):
            return False
        if step.intent.kind not in _FAST_CLOSED_INTENT_TYPES:
            return False
    return True


def classify_clause(
    clause: Clause,
    steps: list[Step],
    *,
    silence_s: float | None = None,
) -> PolicyDecision:
    """Classify a planned clause as ignore, wait, or act.

    Args:
        clause: Committed clause from the segmenter.
        steps: Steps produced by the planner for ``clause``.
        silence_s: Seconds since the transcript last grew, if known.

    Returns:
        Policy decision for the whole clause when not partitioning.
        Prefer :func:`partition_steps` for ask macros; use this for
        filler / empty / all-deferred completeness checks.
    """
    if is_filler_text(clause.text) or not steps:
        return PolicyDecision.IGNORE
    if any(isinstance(step, CancelStep) for step in steps):
        return PolicyDecision.ACT
    _, deferred = partition_steps(steps)
    if not deferred:
        return PolicyDecision.ACT
    if clause.final:
        return PolicyDecision.ACT
    if silence_s is not None and silence_s >= FREE_TEXT_SILENCE_S:
        return PolicyDecision.ACT
    return PolicyDecision.WAIT
