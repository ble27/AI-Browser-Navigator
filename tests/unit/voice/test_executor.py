"""Tests for :class:`QueuedStepExecutor`."""

from __future__ import annotations

import time

from gesture_control.actions import ActionMapper, Intent, IntentType
from gesture_control.backends.base import InputBackend, SafePause
from gesture_control.voice.executor import QueuedStepExecutor
from gesture_control.voice.stream_contracts import (
    Clause,
    PageStep,
    Readiness,
    ResolvedStep,
    StepOutcome,
    StepReport,
)


class _RecordingBackend(InputBackend):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def screen_size(self) -> tuple[int, int]:
        return 1, 1

    def move_to(self, x: int, y: int) -> None:
        del x, y

    def click_left(self) -> None:
        return None

    def open_url(self, url: str) -> None:
        if not self.safe_pause.is_paused:
            self.calls.append(url)

    def navigate_browser(self, action: object) -> None:
        del action

    def search_web(self, text: str) -> None:
        if not self.safe_pause.is_paused:
            self.calls.append(text)

    def scroll(self, amount: int) -> None:
        del amount

    def click_element(self, target_id: str) -> None:
        del target_id

    def type_text(self, target_id: str, text: str) -> None:
        del target_id, text


class _FakePage:
    def __init__(self, url: str | None) -> None:
        self.url = url

    def current_url(self) -> str | None:
        return self.url

    def resolve(self, phrase: str) -> Intent | None:
        del phrase
        return None


class _FakeFocus:
    def __init__(self, app: str | None) -> None:
        self.app = app

    def frontmost_app(self) -> str | None:
        return self.app


def _clause(text: str, line_id: int = 0) -> Clause:
    return Clause(text=text, line_id=line_id, index=0, final=True)


def test_fifo_dispatch_reports_done() -> None:
    backend = _RecordingBackend()
    reports: list[StepReport] = []
    executor = QueuedStepExecutor(
        mapper=ActionMapper(backend),
        page=None,
        focus=None,
        safe_pause=SafePause(),
        report=reports.append,
    )
    step = ResolvedStep(
        source=_clause("open reddit"),
        intent=Intent(IntentType.OPEN_URL, url="https://www.reddit.com"),
    )
    executor.submit([step])
    executor.close()
    assert backend.calls == ["https://www.reddit.com"]
    assert reports[0].outcome is StepOutcome.DONE


def test_readiness_waits_for_host() -> None:
    backend = _RecordingBackend()
    page = _FakePage("https://example.com/")
    reports: list[StepReport] = []
    clock = iter([0.0, 0.0, 1.0]).__next__

    def advance_sleep(_duration: float) -> None:
        page.url = "https://www.amazon.com/"

    executor = QueuedStepExecutor(
        mapper=ActionMapper(backend),
        page=page,
        focus=None,
        safe_pause=SafePause(),
        report=reports.append,
        sleep=advance_sleep,
        clock=clock,
    )
    step = ResolvedStep(
        source=_clause("search"),
        intent=Intent(IntentType.SEARCH_WEB, text="headphones"),
        ready=Readiness(host="amazon.com", max_wait_s=6.0),
    )
    executor.submit([step])
    executor.close()
    assert backend.calls


def test_readiness_fails_fast_when_page_url_unavailable() -> None:
    backend = _RecordingBackend()
    page = _FakePage(None)
    reports: list[StepReport] = []
    ticks = iter([0.0, 0.1, 0.2, 0.3, 0.4, 0.5])

    def clock() -> float:
        return next(ticks, 1.0)

    executor = QueuedStepExecutor(
        mapper=ActionMapper(backend),
        page=page,
        focus=None,
        safe_pause=SafePause(),
        report=reports.append,
        sleep=lambda _duration: None,
        clock=clock,
    )
    step = PageStep(
        source=_clause("click orders"),
        phrase="click orders",
        ready=Readiness(host="amazon.com", max_wait_s=6.0),
    )
    trailing = ResolvedStep(
        source=_clause("next tab", line_id=1),
        intent=Intent(IntentType.NEXT_TAB),
    )
    executor.submit([step, trailing])
    executor.close()
    assert any(report.detail == "readiness timeout" for report in reports)
    # Trailing browser-wide control must still run after the stalled page step.
    assert any(
        isinstance(report.step, ResolvedStep)
        and report.step.intent.kind is IntentType.NEXT_TAB
        and report.outcome is StepOutcome.DONE
        for report in reports
    )
    backend = _RecordingBackend()
    page = _FakePage("https://example.com/")
    executor = QueuedStepExecutor(
        mapper=ActionMapper(backend),
        page=page,
        focus=None,
        safe_pause=SafePause(),
        report=lambda _report: None,
        sleep=lambda _duration: None,
        clock=lambda: 0.0,
    )
    step = PageStep(
        source=_clause("click orders"),
        phrase="click orders",
        ready=Readiness(host="amazon.com"),
    )
    start = time.monotonic()
    executor.submit([step])
    elapsed_ms = (time.monotonic() - start) * 1000.0
    executor.close()
    assert elapsed_ms < 10.0


def test_safe_pause_during_readiness_skips_and_drains() -> None:
    backend = _RecordingBackend()
    page = _FakePage("https://example.com/")
    pause = SafePause()
    reports: list[StepReport] = []
    ticks = iter([0.0, 0.1, 0.2])

    def clock() -> float:
        return next(ticks, 0.3)

    def on_sleep(_duration: float) -> None:
        if not pause.is_paused:
            pause.toggle()

    executor = QueuedStepExecutor(
        mapper=ActionMapper(backend),
        page=page,
        focus=None,
        safe_pause=pause,
        report=reports.append,
        sleep=on_sleep,
        clock=clock,
    )
    waiting = ResolvedStep(
        source=_clause("search", line_id=1),
        intent=Intent(IntentType.SEARCH_WEB, text="headphones"),
        ready=Readiness(host="amazon.com", max_wait_s=6.0),
    )
    trailing = ResolvedStep(
        source=_clause("open reddit", line_id=2),
        intent=Intent(IntentType.OPEN_URL, url="https://www.reddit.com"),
    )
    executor.submit([waiting, trailing])
    executor.close()
    assert backend.calls == []
    outcomes = [report.outcome for report in reports]
    assert StepOutcome.SKIPPED_PAUSED in outcomes
    assert StepOutcome.CANCELLED in outcomes
    assert StepOutcome.FAILED not in outcomes


def test_page_step_surfaces_bridge_unavailable_detail_when_no_fallback() -> None:
    from gesture_control.voice.live_page import PageCommandUnavailableError

    class _UnavailablePage:
        def current_url(self) -> str | None:
            return None

        def resolve(self, phrase: str) -> Intent | None:
            del phrase
            raise PageCommandUnavailableError("Chrome page bridge is disconnected")

    backend = _RecordingBackend()
    reports: list[StepReport] = []
    executor = QueuedStepExecutor(
        mapper=ActionMapper(backend),
        page=_UnavailablePage(),
        focus=None,
        safe_pause=SafePause(),
        report=reports.append,
    )
    executor.submit([PageStep(source=_clause("click first link"), phrase="click first link")])
    executor.close()
    assert len(reports) == 1
    assert reports[0].outcome is StepOutcome.FAILED
    assert "disconnected" in reports[0].detail
