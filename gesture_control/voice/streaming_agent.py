"""Coordinator for offline streaming voice control."""

from __future__ import annotations

import inspect
import threading
import time
from collections.abc import Callable

from gesture_control.actions import Intent, IntentType
from gesture_control.backends.base import PressableKey
from gesture_control.voice.asr_repair import repair_command_text
from gesture_control.voice.confirm import is_confirm_phrase, is_destructive_phrase
from gesture_control.voice.desktop import parse_type_command
from gesture_control.voice.policy import (
    FAST_CLOSED_DEBOUNCE_S,
    FREE_TEXT_SILENCE_S,
    PARTIAL_DEBOUNCE_S,
    TYPE_COMMAND_SILENCE_S,
    PolicyDecision,
    classify_clause,
    has_clause_delimiter,
    is_fast_closed_steps,
    is_filler_text,
    is_type_only_steps,
    partition_steps,
)
from gesture_control.voice.preferences import VoicePreferences
from gesture_control.voice.stream_contracts import (
    STABLE_PARTIALS_TO_COMMIT,
    Clause,
    ClausePlanner,
    ClauseSegmenter,
    PageStep,
    ResolvedStep,
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
        type_silence_s: float = TYPE_COMMAND_SILENCE_S,
        preferences: Callable[[], VoicePreferences] | None = None,
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
            type_silence_s: Quiet time before a type/write command is typed.
                Shorter than ``free_text_silence_s`` so dictation does not wait
                for the recognizer's final result. Ignored when ``preferences``
                is set.
            preferences: Live pill settings. When set, dictation uses
                ``type_silence_s()`` from the current value.
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
        self._type_silence_s = type_silence_s
        self._preferences = preferences
        # Text already inserted for a clause, so a later final appends only
        # the new suffix instead of typing the whole phrase again.
        self._typed_text: dict[tuple[int, int], str] = {}
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
            "type ",
            "write ",
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
        if event.kind is TranscriptEventKind.PARTIAL and self._queue_type_partial(event):
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
                self._submit(safe)
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
                self._submit(safe)
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
        timer = threading.Timer(self._silence_delay(), self._silence_fire)
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
            if quiet >= self._silence_delay():
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
            self._submit(safe)
        if destructive:
            self._pending_destructive.extend(destructive)
            self._output("[confirm needed] say confirm to proceed")
        self._held_steps = []
        self._held_clause = None
        self._cancel_silence()

    def _silence_delay(self) -> float:
        """Use the shorter window only for type/write dictation."""
        if is_type_only_steps(self._held_steps):
            if self._preferences is not None:
                return self._preferences().type_silence_s()
            return self._type_silence_s
        return self._free_text_silence_s

    def _queue_type_partial(self, event: TranscriptEvent) -> bool:
        """Hold a type command from the first partial instead of waiting for FINAL.

        Args:
            event: Partial transcript event.

        Returns:
            True when the partial was handled as dictation and should not also
            go through the closed-command early path.
        """
        if has_clause_delimiter(event.text):
            return False
        request = parse_type_command(event.text)
        if request is None or not request.text.strip():
            return False
        text = " ".join(event.text.split())
        self._handle_clause(Clause(text=text, line_id=event.line_id, index=0, final=False))
        return True

    def _submit(self, steps: list[Step]) -> None:
        """Submit steps, appending only new dictated characters."""
        prepared = self._prepare_type_submission(steps)
        if not prepared:
            return
        self._executor.submit(prepared)
        self._record_actions(prepared)

    def _prepare_type_submission(self, steps: list[Step]) -> list[Step]:
        """Rewrite type steps so a later final does not type the phrase twice."""
        prepared: list[Step] = []
        for step in steps:
            rewritten = self._rewrite_type_step(step)
            if rewritten is None:
                prepared.append(step)
            else:
                prepared.extend(rewritten)
        return prepared

    def _rewrite_type_step(self, step: Step) -> list[Step] | None:
        """Return replacement steps for a type action, or None to keep it.

        Bare dictation is appended. A named field is replaced with the full
        text, which is safe to send again when the phrase grows. An identical
        phrase is dropped.
        """
        described = _describe_type_step(step)
        if described is None:
            return None
        text, mode = described
        key = (step.source.line_id, step.source.index)
        previous = self._typed_text.get(key, "")
        if text == previous:
            return []
        if mode == "replace":
            self._typed_text[key] = text
            return [step]
        ready = step.ready if isinstance(step, (ResolvedStep, PageStep)) else None
        if text.startswith(previous):
            suffix = text[len(previous) :]
            self._typed_text[key] = text
            if not suffix:
                return []
            return [
                ResolvedStep(
                    source=step.source,
                    intent=Intent(IntentType.TYPE_FOCUSED, text=suffix),
                    ready=ready,
                )
            ]
        backspaces = [
            ResolvedStep(
                source=step.source,
                intent=Intent(IntentType.PRESS_KEY, key=PressableKey.BACKSPACE),
            )
            for _character in previous
        ]
        self._typed_text[key] = text
        return [
            *backspaces,
            ResolvedStep(
                source=step.source,
                intent=Intent(IntentType.TYPE_FOCUSED, text=text),
                ready=ready,
            ),
        ]

    def _cancel_debounce(self) -> None:
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
            self._debounce_timer = None

    def _cancel_silence(self) -> None:
        if self._silence_timer is not None:
            self._silence_timer.cancel()
            self._silence_timer = None


def _describe_type_step(step: Step) -> tuple[str, str] | None:
    """Return ``(full text, mode)`` for a type step.

    Mode is ``append`` for bare dictation and ``replace`` when a field name
    was spoken. Returns ``None`` for every other step.
    """
    if isinstance(step, ResolvedStep) and step.intent.kind is IntentType.TYPE_FOCUSED:
        return (step.intent.text or "", "append")
    if isinstance(step, ResolvedStep) and step.intent.kind is IntentType.TYPE_TEXT:
        return (step.intent.text or "", "replace")
    if isinstance(step, PageStep):
        request = parse_type_command(step.phrase)
        if request is None or not request.text:
            return None
        return (request.text, "replace" if request.has_target else "append")
    return None


# Keep the Phase 1 constructor pin: only the five public ports + output.
# Extra kwargs are keyword-only and do not change the positional contract.
StreamingVoiceAgent.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
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
