"""Background step executor for the streaming voice agent."""

from __future__ import annotations

import inspect
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from urllib.parse import urlparse

from gesture_control.actions import ActionMapper, Intent
from gesture_control.backends.base import SafePause
from gesture_control.voice.live_page import PageCommandUnavailableError
from gesture_control.voice.stream_contracts import (
    READY_POLL_INTERVAL_S,
    AppFocusPort,
    CancelStep,
    PagePort,
    PageStep,
    Readiness,
    ResolvedStep,
    Step,
    StepOutcome,
    StepReport,
)

_SHUTDOWN = object()


def _hostname(url: str | None) -> str | None:
    if not url:
        return None
    host = urlparse(url).hostname
    if host is None:
        return None
    return host.removeprefix("www.").casefold()


def _host_matches(current: str | None, expected: str) -> bool:
    if current is None:
        return False
    expected_folded = expected.removeprefix("www.").casefold()
    if current == expected_folded:
        return True
    return current.endswith(f".{expected_folded}")


class QueuedStepExecutor:
    """Run planned steps on a single worker thread."""

    def __init__(
        self,
        mapper: ActionMapper,
        page: PagePort | None,
        focus: AppFocusPort | None,
        safe_pause: SafePause,
        report: Callable[[StepReport], None],
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create an executor with injectable timing for tests."""
        self._mapper = mapper
        self._page = page
        self._focus = focus
        self._safe_pause = safe_pause
        self._report = report
        self._sleep = sleep
        self._clock = clock
        self._deque: deque[Step | object] = deque()
        self._cond = threading.Condition()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def submit(self, steps: Sequence[Step]) -> None:
        """Enqueue steps without blocking the caller."""
        with self._cond:
            for step in steps:
                if isinstance(step, CancelStep):
                    self._drain_cancelled(detail="user cancel")
                    self._deque.appendleft(step)
                else:
                    self._deque.append(step)
            self._cond.notify()

    def close(self, timeout_s: float = 2.0) -> None:
        """Drain the worker and shut down."""
        with self._cond:
            self._deque.append(_SHUTDOWN)
            self._cond.notify()
        self._worker.join(timeout=timeout_s)

    def _run(self) -> None:
        while True:
            with self._cond:
                while not self._deque:
                    self._cond.wait()
                step = self._deque.popleft()
            if step is _SHUTDOWN:
                return
            assert isinstance(step, (ResolvedStep, PageStep, CancelStep))
            if isinstance(step, CancelStep):
                self._drain_cancelled(detail="user cancel")
                self._report(
                    StepReport(step=step, outcome=StepOutcome.DONE, detail="cancelled queue"),
                )
                continue
            if self._safe_pause.is_paused:
                self._report(
                    StepReport(
                        step=step,
                        outcome=StepOutcome.SKIPPED_PAUSED,
                        detail="safe pause active",
                    ),
                )
                self._drain_cancelled(detail="safe pause")
                continue
            outcome = self._execute(step)
            if outcome is StepOutcome.FAILED:
                self._cancel_line(step.source.line_id, detail="step failed")

    def _execute(self, step: ResolvedStep | PageStep) -> StepOutcome:
        if isinstance(step, ResolvedStep):
            return self._execute_resolved(step)
        return self._execute_page(step)

    def _execute_resolved(self, step: ResolvedStep) -> StepOutcome:
        wait_result = self._wait_ready(step.ready)
        if wait_result == "cancelled":
            self._report(
                StepReport(step=step, outcome=StepOutcome.CANCELLED, detail="user cancel"),
            )
            return StepOutcome.CANCELLED
        if wait_result == "paused":
            self._report(
                StepReport(
                    step=step,
                    outcome=StepOutcome.SKIPPED_PAUSED,
                    detail="safe pause during readiness",
                ),
            )
            self._drain_cancelled(detail="safe pause")
            return StepOutcome.SKIPPED_PAUSED
        if not wait_result:
            self._report(
                StepReport(step=step, outcome=StepOutcome.FAILED, detail="readiness timeout"),
            )
            self._report(
                StepReport(
                    step=CancelStep(source=step.source),
                    outcome=StepOutcome.CANCELLED,
                    detail="line cancelled after readiness timeout",
                ),
            )
            self._cancel_line(step.source.line_id, detail="readiness timeout")
            return StepOutcome.FAILED
        try:
            self._mapper.dispatch(step.intent)
        except ValueError as exc:
            self._report(
                StepReport(step=step, outcome=StepOutcome.FAILED, detail=str(exc)),
            )
            return StepOutcome.FAILED
        self._report(StepReport(step=step, outcome=StepOutcome.DONE, detail="dispatched"))
        return StepOutcome.DONE

    def _execute_page(self, step: PageStep) -> StepOutcome:
        wait_result = self._wait_ready(step.ready)
        if wait_result == "cancelled":
            self._report(
                StepReport(step=step, outcome=StepOutcome.CANCELLED, detail="user cancel"),
            )
            return StepOutcome.CANCELLED
        if wait_result == "paused":
            self._report(
                StepReport(
                    step=step,
                    outcome=StepOutcome.SKIPPED_PAUSED,
                    detail="safe pause during readiness",
                ),
            )
            self._drain_cancelled(detail="safe pause")
            return StepOutcome.SKIPPED_PAUSED
        if not wait_result:
            self._report(
                StepReport(step=step, outcome=StepOutcome.FAILED, detail="readiness timeout"),
            )
            self._report(
                StepReport(
                    step=CancelStep(source=step.source),
                    outcome=StepOutcome.CANCELLED,
                    detail="line cancelled after readiness timeout",
                ),
            )
            self._cancel_line(step.source.line_id, detail="readiness timeout")
            return StepOutcome.FAILED
        intent: Intent | None = None
        unavailable_detail: str | None = None
        if self._page is not None:
            try:
                intent = self._page.resolve(step.phrase)
            except PageCommandUnavailableError as exc:
                unavailable_detail = str(exc) or "page bridge unavailable"
                intent = None
        if intent is None:
            intent = step.fallback
        if intent is None:
            self._report(
                StepReport(
                    step=step,
                    outcome=StepOutcome.FAILED,
                    detail=unavailable_detail or "unresolved page step",
                ),
            )
            return StepOutcome.FAILED
        try:
            self._mapper.dispatch(intent)
        except ValueError as exc:
            self._report(
                StepReport(step=step, outcome=StepOutcome.FAILED, detail=str(exc)),
            )
            return StepOutcome.FAILED
        self._report(StepReport(step=step, outcome=StepOutcome.DONE, detail="dispatched"))
        return StepOutcome.DONE

    def _wait_ready(self, ready: Readiness | None) -> bool | str:
        if ready is None:
            return True
        if ready.host is None and ready.app is None:
            return True
        deadline = self._clock() + ready.max_wait_s
        null_host_streak = 0
        while self._clock() < deadline:
            if self._safe_pause.is_paused:
                # Same contract as pause-at-dequeue: skip + drain, never
                # report a readiness timeout for an intentional pause.
                return "paused"
            if self._take_cancel_if_queued():
                return "cancelled"
            if ready.host is not None and self._page is not None:
                observed_host = _hostname(self._page.current_url())
                if observed_host is None:
                    # Bridge down / no active tab URL: waiting full timeout only
                    # stalls the FIFO queue behind unresolved PageSteps.
                    null_host_streak += 1
                    if null_host_streak >= 3:
                        return False
                else:
                    null_host_streak = 0
                if _host_matches(observed_host, ready.host):
                    return True
            if ready.app is not None and self._focus is not None:
                observed_app = self._focus.frontmost_app()
                if observed_app is not None and observed_app == ready.app.value:
                    return True
            self._sleep(READY_POLL_INTERVAL_S)
        return False

    def _take_cancel_if_queued(self) -> bool:
        with self._cond:
            if self._deque and isinstance(self._deque[0], CancelStep):
                self._deque.popleft()
                self._drain_cancelled(detail="user cancel")
                return True
        return False

    def _cancel_line(self, line_id: int, detail: str) -> None:
        with self._cond:
            kept: deque[Step | object] = deque()
            while self._deque:
                item = self._deque.popleft()
                if not isinstance(item, (ResolvedStep, PageStep)):
                    kept.append(item)
                    continue
                if item.source.line_id == line_id:
                    self._report(
                        StepReport(step=item, outcome=StepOutcome.CANCELLED, detail=detail),
                    )
                else:
                    kept.append(item)
            self._deque = kept

    def _drain_cancelled(self, detail: str) -> None:
        with self._cond:
            kept: deque[Step | object] = deque()
            while self._deque:
                item = self._deque.popleft()
                if isinstance(item, (ResolvedStep, PageStep)):
                    self._report(
                        StepReport(step=item, outcome=StepOutcome.CANCELLED, detail=detail),
                    )
                elif isinstance(item, CancelStep):
                    kept.append(item)
                else:
                    kept.append(item)
            self._deque = kept


QueuedStepExecutor.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
    [
        inspect.Parameter("self", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter("mapper", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter("page", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter("focus", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter("safe_pause", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter("report", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter(
            "sleep",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=time.sleep,
        ),
        inspect.Parameter(
            "clock",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=time.monotonic,
        ),
    ],
)
