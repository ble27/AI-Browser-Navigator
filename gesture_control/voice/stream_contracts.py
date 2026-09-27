"""Frozen contracts for the offline streaming voice agent.

Types and protocols in this module are the source of truth after Phase 1.
Do not change them without explicit user approval.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, TypeAlias

from gesture_control.backends.base import LaunchableApp

if TYPE_CHECKING:
    from gesture_control.actions.mapper import Intent

STABLE_PARTIALS_TO_COMMIT = 2
DEFAULT_READY_WAIT_S = 6.0
READY_POLL_INTERVAL_S = 0.25
MAX_TYPED_CHARS = 500


class TranscriptEventKind(StrEnum):
    """Kind of streaming STT emission."""

    PARTIAL = "partial"
    FINAL = "final"


@dataclass(frozen=True, slots=True)
class TranscriptEvent:
    """One partial or final line from the streaming transcriber.

    Attributes:
        kind: Whether this is a partial hypothesis or a finalized line.
        text: Transcript text for this emission (may grow across partials).
        line_id: Stable id for the spoken line from the STT engine.
        at_s: ``time.monotonic()`` timestamp when the event was emitted.
    """

    kind: TranscriptEventKind
    text: str
    line_id: int
    at_s: float


class StreamingTranscriber(Protocol):
    """Offline streaming speech-to-text port."""

    def start(self, sink: Callable[[TranscriptEvent], None]) -> None:
        """Begin streaming; invoke ``sink`` for each transcript event."""

    def stop(self) -> None:
        """Stop streaming and release audio resources."""


@dataclass(frozen=True, slots=True)
class Clause:
    """A committed clause extracted from one spoken line.

    Attributes:
        text: Clause text without trailing delimiters.
        line_id: Parent line id from the STT engine.
        index: Zero-based position within that line.
        final: True when committed from a FINAL transcript event.
    """

    text: str
    line_id: int
    index: int
    final: bool


class Surface(StrEnum):
    """Where subsequent desktop actions are expected to run."""

    BROWSER = "browser"
    APP = "app"


@dataclass(frozen=True, slots=True)
class Readiness:
    """Execution-time wait for a browser host or frontmost app.

    Attributes:
        host: Active tab hostname must equal or be a subdomain of this value.
        app: Frontmost application name must equal ``app.value``.
        max_wait_s: Upper bound on readiness polling for this step.
    """

    host: str | None = None
    app: LaunchableApp | None = None
    max_wait_s: float = DEFAULT_READY_WAIT_S


@dataclass(frozen=True, slots=True)
class ResolvedStep:
    """A step whose intent is known at plan time."""

    source: Clause
    intent: Intent
    ready: Readiness | None = None


@dataclass(frozen=True, slots=True)
class PageStep:
    """A step resolved against the live page at execution time."""

    source: Clause
    phrase: str
    fallback: Intent | None = None
    ready: Readiness | None = None


@dataclass(frozen=True, slots=True)
class CancelStep:
    """User cancel: drop pending work for the current queue."""

    source: Clause


Step: TypeAlias = ResolvedStep | PageStep | CancelStep


class StepOutcome(StrEnum):
    """Executor result for one queued step."""

    DONE = "done"
    SKIPPED_PAUSED = "skipped_paused"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class StepReport:
    """Outcome of executing one step."""

    step: Step
    outcome: StepOutcome
    detail: str


class ClauseSegmenter(Protocol):
    """Turns transcript events into committed clauses."""

    def feed(self, event: TranscriptEvent) -> list[Clause]:
        """Consume one event and return any newly committed clauses."""


class ClausePlanner(Protocol):
    """Maps one clause to an ordered list of execution steps."""

    @property
    def surface(self) -> Surface:
        """Current browser vs. app surface for this planner session."""

    def plan(self, clause: Clause) -> list[Step]:
        """Expand one clause into zero or more steps."""


class PagePort(Protocol):
    """Live page snapshot and phrase resolution."""

    def current_url(self) -> str | None:
        """Return the active tab URL, or None if the bridge is down."""

    def resolve(self, phrase: str) -> Intent | None:
        """Resolve a voice phrase to an intent, or None if unmatched."""


class AppFocusPort(Protocol):
    """Frontmost native application name."""

    def frontmost_app(self) -> str | None:
        """Return the frontmost app name, or None if unknown."""


class StepExecutor(Protocol):
    """Background worker that runs queued steps."""

    def submit(self, steps: Sequence[Step]) -> None:
        """Enqueue steps without blocking the caller."""

    def close(self, timeout_s: float = 2.0) -> None:
        """Drain the worker and shut down."""


@dataclass(frozen=True, slots=True)
class TypeRequest:
    """Parsed desktop type command."""

    text: str
    has_target: bool


@dataclass(frozen=True, slots=True)
class AskRequest:
    """Parsed assistant query macro."""

    url: str
    host: str
    query: str
