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


def test_submit_returns_quickly_while_waiting() -> None:
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
