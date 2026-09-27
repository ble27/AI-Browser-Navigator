"""Coordinator for offline streaming voice control."""

from __future__ import annotations

import inspect
import threading
import time
from collections.abc import Callable

from gesture_control.voice.asr_repair import repair_command_text
from gesture_control.voice.confirm import is_confirm_phrase, is_destructive_phrase
from gesture_control.voice.policy import (
    FAST_CLOSED_DEBOUNCE_S,
    FREE_TEXT_SILENCE_S,
    PARTIAL_DEBOUNCE_S,
    PolicyDecision,
    classify_clause,
    has_clause_delimiter,
    is_fast_closed_steps,
    is_filler_text,
    partition_steps,
)
from gesture_control.voice.stream_contracts import (
    STABLE_PARTIALS_TO_COMMIT,
    Clause,
    ClausePlanner,
    ClauseSegmenter,
    PageStep,
    Step,
    StepExecutor,
    StreamingTranscriber,
    TranscriptEvent,
    TranscriptEventKind,
)


class StreamingVoiceAgent:
    """Apply repair, debounce, policy, segment, plan, and enqueue steps."""

    def __init__(
        self,
        transcriber: StreamingTranscriber,
        segmenter: ClauseSegmenter,
        planner: ClausePlanner,
        executor: StepExecutor,
        output: Callable[[str], None] = print,
        *,
        clock: Callable[[], float] = time.monotonic,
        debounce_s: float = PARTIAL_DEBOUNCE_S,
        fast_debounce_s: float = FAST_CLOSED_DEBOUNCE_S,
        free_text_silence_s: float = FREE_TEXT_SILENCE_S,
    ) -> None:
        """Wire streaming voice ports together.

        Args:
            transcriber: Streaming STT source.
            segmenter: Clause committer.
            planner: Clause → steps mapper.
            executor: Background step runner.
            output: Sink for live transcript / status lines.
            clock: Monotonic clock (injectable for tests).
            debounce_s: Quiet time before a generic PARTIAL is processed.
            fast_debounce_s: Quieter window for tab/scroll/key partials.
            free_text_silence_s: Quiet time before held free-text steps flush.
        """
        self._transcriber = transcriber
        self._segmenter = segmenter
        self._planner = planner
        self._executor = executor
        self._output = output
        self._clock = clock
        self._debounce_s = debounce_s
        self._fast_debounce_s = fast_debounce_s
        self._free_text_silence_s = free_text_silence_s
        self._lock = threading.Lock()
        self._pending_partial: TranscriptEvent | None = None
        self._debounce_timer: threading.Timer | None = None
        self._held_steps: list[Step] = []
        self._held_clause: Clause | None = None
        self._submitted_closed: set[tuple[int, int]] = set()
        self._early_text: dict[tuple[int, int], str] = {}
        self._early_stable: dict[tuple[int, int], int] = {}
        self._last_text_at: float | None = None
        self._silence_timer: threading.Timer | None = None
        self._pending_destructive: list[Step] = []
        self._recent_actions: list[str] = []

    def on_event(self, event: TranscriptEvent) -> None:
        """Handle one transcript event from the STT thread."""
        repaired = repair_command_text(event.text)
        if repaired.strip():
            self._output(f"[{event.kind.value}] {repaired}")
        repaired_event = TranscriptEvent(event.kind, repaired, event.line_id, event.at_s)
        with self._lock:
            self._last_text_at = self._clock()
            if repaired_event.kind is TranscriptEventKind.PARTIAL:
                self._pending_partial = repaired_event
                self._arm_debounce(self._debounce_for(repaired_event.text))
                return
            self._cancel_debounce()
            self._pending_partial = None
            self._process_event(repaired_event)
            self._flush_held(force=True)

    def start(self) -> None:
        """Start microphone streaming."""
        self._transcriber.start(self.on_event)

    def stop(self) -> None:
        """Stop microphone streaming and flush timers."""
        with self._lock:
            self._cancel_debounce()
            self._cancel_silence()
            if self._pending_partial is not None:
                self._process_event(self._pending_partial)
                self._pending_partial = None
            self._flush_held(force=True)
        self._transcriber.stop()

    def _debounce_for(self, text: str) -> float:
        """Use a shorter quiet window for likely tab/scroll/key phrases."""
        folded = " ".join(text.split()).casefold()
        fast_hints = (
            "tab",
            "scroll",
            "reload",
            "refresh",
            "go back",
            "go forward",
            "press ",
            "hit ",
            "cancel",
            "stop",
            "never mind",
        )
        if any(hint in folded for hint in fast_hints):
            return self._fast_debounce_s
        return self._debounce_s

    def _arm_debounce(self, delay_s: float) -> None:
        self._cancel_debounce()
        timer = threading.Timer(delay_s, self._debounce_fire)
        timer.daemon = True
        self._debounce_timer = timer
        timer.start()

    def _debounce_fire(self) -> None:
        with self._lock:
            if self._pending_partial is None:
                return
            event = self._pending_partial
            self._pending_partial = None
            self._debounce_timer = None
            self._process_event(event)
            self._arm_silence_if_held()

    def _process_event(self, event: TranscriptEvent) -> None:
        if is_filler_text(event.text):
            return
        if is_confirm_phrase(event.text):
            self._flush_pending_destructive()
            return
        if event.kind is TranscriptEventKind.PARTIAL:
            self._try_early_closed_partial(event)
        for clause in self._segmenter.feed(event):
            self._handle_clause(clause)

    def _flush_pending_destructive(self) -> None:
        if not self._pending_destructive:
            self._output("[confirm] nothing pending")
            return
        self._executor.submit(self._pending_destructive)
        self._record_actions(self._pending_destructive)
        self._pending_destructive = []
        self._output("[confirm] dispatched")

    def _record_actions(self, steps: list[Step]) -> None:
        for step in steps:
            if isinstance(step, PageStep):
                label = f"page:{step.phrase}"
            else:
                label = type(step).__name__
            self._recent_actions.append(label)
        if len(self._recent_actions) > 5:
            self._recent_actions = self._recent_actions[-5:]

    def _split_destructive(self, steps: list[Step]) -> tuple[list[Step], list[Step]]:
        safe: list[Step] = []
        destructive: list[Step] = []
        for step in steps:
            if isinstance(step, PageStep) and is_destructive_phrase(step.phrase):
                destructive.append(step)
            else:
                safe.append(step)
        return safe, destructive

    def _try_early_closed_partial(self, event: TranscriptEvent) -> None:
        """Fire tab/scroll/key (and stable open-*) before VAD FINAL.

        Single-clause commands never leave the segmenter until FINAL, which is
        why ``next tab`` felt seconds late versus jev. Peek-plan the whole
        partial line and submit when it is a pure closed-set command.
        """
        text = " ".join(event.text.split())
        if not text or has_clause_delimiter(text):
            return
        key = (event.line_id, 0)
        if key in self._submitted_closed:
            return
        clause = Clause(text=text, line_id=event.line_id, index=0, final=False)
        steps = self._planner.plan(clause)
        if not steps:
            return
        immediate, deferred = partition_steps(steps)
        if not immediate or deferred:
            return
        if is_fast_closed_steps(steps):
            self._handle_clause(clause)
            return
        # Brand / app opens: wait for two identical partials to avoid
        # "open amazing" → wrong site before revision to amazon.
        previous = self._early_text.get(key)
        if previous == text:
            self._early_stable[key] = self._early_stable.get(key, 1) + 1
        else:
            self._early_text[key] = text
            self._early_stable[key] = 1
        if self._early_stable[key] >= STABLE_PARTIALS_TO_COMMIT:
            self._handle_clause(clause)

    def _handle_clause(self, clause: Clause) -> None:
        if is_filler_text(clause.text):
            return
        if is_confirm_phrase(clause.text):
            self._flush_pending_destructive()
            return
        steps = self._planner.plan(clause)
        if not steps:
            return
        decision = classify_clause(clause, steps)
        if decision is PolicyDecision.IGNORE:
            return
        immediate, deferred = partition_steps(steps)
        key = (clause.line_id, clause.index)
        if immediate and key not in self._submitted_closed:
            safe, destructive = self._split_destructive(immediate)
            if safe:
                self._executor.submit(safe)
                self._record_actions(safe)
                self._submitted_closed.add(key)
            if destructive:
                self._pending_destructive.extend(destructive)
                self._output("[confirm needed] say confirm to proceed")
                self._submitted_closed.add(key)
        if not deferred:
            return
        if clause.final or decision is PolicyDecision.ACT:
            safe, destructive = self._split_destructive(deferred)
            if safe:
                self._executor.submit(safe)
                self._record_actions(safe)
            if destructive:
                self._pending_destructive.extend(destructive)
                self._output("[confirm needed] say confirm to proceed")
            self._held_steps = []
            self._held_clause = None
            self._cancel_silence()
            return
        # Replace (do not stack) deferred steps for the latest partial plan.
        self._held_steps = list(deferred)
        self._held_clause = clause
        self._arm_silence_if_held()

    def _arm_silence_if_held(self) -> None:
        if not self._held_steps:
            return
        self._cancel_silence()
        timer = threading.Timer(self._free_text_silence_s, self._silence_fire)
        timer.daemon = True
        self._silence_timer = timer
        timer.start()

    def _silence_fire(self) -> None:
        with self._lock:
            self._silence_timer = None
            if not self._held_steps:
                return
            if self._last_text_at is None:
                self._flush_held(force=True)
                return
            quiet = self._clock() - self._last_text_at
            if quiet >= self._free_text_silence_s:
                self._flush_held(force=True)
            else:
                self._arm_silence_if_held()

    def _flush_held(self, *, force: bool) -> None:
        if not self._held_steps:
            return
        if not force and self._held_clause is not None and not self._held_clause.final:
            return
        safe, destructive = self._split_destructive(self._held_steps)
        if safe:
            self._executor.submit(safe)
            self._record_actions(safe)
        if destructive:
            self._pending_destructive.extend(destructive)
            self._output("[confirm needed] say confirm to proceed")
        self._held_steps = []
        self._held_clause = None
        self._cancel_silence()

    def _cancel_debounce(self) -> None:
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
            self._debounce_timer = None

    def _cancel_silence(self) -> None:
        if self._silence_timer is not None:
            self._silence_timer.cancel()
            self._silence_timer = None


# Keep the Phase 1 constructor pin: only the five public ports + output.
# Extra kwargs are keyword-only and do not change the positional contract.
StreamingVoiceAgent.__signature__ = inspect.Signature(
    [
        inspect.Parameter("self", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter("transcriber", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter("segmenter", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter("planner", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter("executor", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter(
            "output",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=print,
        ),
    ],
)
