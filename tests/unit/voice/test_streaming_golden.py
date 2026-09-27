"""Golden replay tests for the streaming voice pipeline (strict-xfail until Phase 3)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from gesture_control.actions import ActionMapper, Intent, IntentType
from gesture_control.backends.base import (
    BrowserAction,
    FocusedPageFieldAction,
    InputBackend,
    LaunchableApp,
    PressableKey,
    SafePause,
)
from gesture_control.voice.asr_repair import repair_command_text
from gesture_control.voice.live_page import PageCommandUnavailableError
from gesture_control.voice.stream_contracts import (
    StepOutcome,
    StepReport,
    TranscriptEvent,
    TranscriptEventKind,
)


@dataclass
class _BackendCall:
    name: str
    args: tuple[Any, ...] = ()


class RecordingBackend(InputBackend):
    """Record ordered backend operations for golden assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[_BackendCall] = []

    def screen_size(self) -> tuple[int, int]:
        return 1920, 1080

    def move_to(self, x: int, y: int) -> None:
        del x, y

    def click_left(self) -> None:
        return None

    def open_url(self, url: str) -> None:
        if not self.safe_pause.is_paused:
            self.calls.append(_BackendCall("open_url", (url,)))

    def navigate_browser(self, action: BrowserAction) -> None:
        if not self.safe_pause.is_paused:
            self.calls.append(_BackendCall("navigate_browser", (action,)))

    def search_web(self, text: str) -> None:
        if not self.safe_pause.is_paused:
            self.calls.append(_BackendCall("search_web", (text,)))

    def scroll(self, amount: int) -> None:
        if not self.safe_pause.is_paused:
            self.calls.append(_BackendCall("scroll", (amount,)))

    def click_element(self, target_id: str) -> None:
        if not self.safe_pause.is_paused:
            self.calls.append(_BackendCall("click_element", (target_id,)))

    def type_text(self, target_id: str, text: str) -> None:
        if not self.safe_pause.is_paused:
            self.calls.append(_BackendCall("type_text", (target_id, text)))

    def open_app(self, app: LaunchableApp) -> None:
        if not self.safe_pause.is_paused:
            self.calls.append(_BackendCall("open_app", (app,)))

    def type_focused(self, text: str) -> None:
        if not self.safe_pause.is_paused:
            self.calls.append(_BackendCall("type_focused", (text,)))

    def press_key(self, key: PressableKey) -> None:
        if not self.safe_pause.is_paused:
            self.calls.append(_BackendCall("press_key", (key,)))

    def edit_focused_page_field(self, action: FocusedPageFieldAction) -> None:
        if not self.safe_pause.is_paused:
            self.calls.append(_BackendCall("edit_focused_page_field", (action,)))


@dataclass
class FakePagePort:
    """Mutable page URL and element resolution for readiness goldens."""

    url: str | None = "https://example.com/"
    elements: dict[str, Intent] = field(default_factory=dict)
    unavailable: bool = False

    def current_url(self) -> str | None:
        return self.url

    def resolve(self, phrase: str) -> Intent | None:
        if self.unavailable:
            raise PageCommandUnavailableError("bridge down")
        return self.elements.get(phrase.lower())


@dataclass
class FakeFocus:
    app: str | None = "Google Chrome"

    def frontmost_app(self) -> str | None:
        return self.app


def _final(line_id: int, text: str, at_s: float = 1.0) -> TranscriptEvent:
    return TranscriptEvent(TranscriptEventKind.FINAL, text, line_id, at_s)


def _partial(line_id: int, text: str, at_s: float) -> TranscriptEvent:
    return TranscriptEvent(TranscriptEventKind.PARTIAL, text, line_id, at_s)


def _run_golden(
    events: Sequence[TranscriptEvent],
    *,
    paused: bool = False,
    page: FakePagePort | None = None,
    focus: FakeFocus | None = None,
    advance_host: Callable[[FakePagePort], None] | None = None,
) -> tuple[RecordingBackend, list[StepReport]]:
    """Drive segmenter → planner → executor with repair applied to each event."""
    from gesture_control.voice.executor import QueuedStepExecutor
    from gesture_control.voice.planner import DeterministicClausePlanner
    from gesture_control.voice.segmenter import DeterministicClauseSegmenter

    backend = RecordingBackend()
    safe_pause = SafePause(paused=paused)
    backend.safe_pause = safe_pause
    mapper = ActionMapper(backend)
    page_port = page or FakePagePort()
    focus_port = focus or FakeFocus()
    reports: list[StepReport] = []
    segmenter = DeterministicClauseSegmenter()
    planner = DeterministicClausePlanner()
    clock_values = [float(index) for index in range(100)]
    clock_index = 0

    def clock() -> float:
        nonlocal clock_index
        value = clock_values[min(clock_index, len(clock_values) - 1)]
        clock_index += 1
        return value

    def sleep(_duration: float) -> None:
        if advance_host is not None:
            advance_host(page_port)

    executor = QueuedStepExecutor(
        mapper=mapper,
        page=page_port,
        focus=focus_port,
        safe_pause=safe_pause,
        report=reports.append,
        sleep=sleep,
        clock=clock,
    )
    for event in events:
        repaired = repair_command_text(event.text)
        repaired_event = TranscriptEvent(event.kind, repaired, event.line_id, event.at_s)
        for clause in segmenter.feed(repaired_event):
            executor.submit(planner.plan(clause))
    executor.close()
    return backend, reports


def test_g1_final_open_reddit() -> None:
    backend, reports = _run_golden([_final(0, "open reddit")])
    assert backend.calls == [_BackendCall("open_url", ("https://www.reddit.com",))]
    assert reports and reports[0].outcome is StepOutcome.DONE


def test_g2_final_next_tab() -> None:
    backend, _reports = _run_golden([_final(0, "next tab")])
    assert backend.calls == [_BackendCall("navigate_browser", (BrowserAction.NEXT_TAB,))]


def test_g16_paused_at_dequeue() -> None:
    _backend, reports = _run_golden(
        [_final(0, "open reddit"), _final(1, "next tab")],
        paused=True,
    )
    outcomes = [report.outcome for report in reports]
    assert StepOutcome.SKIPPED_PAUSED in outcomes
    assert StepOutcome.CANCELLED in outcomes


def test_g3_partial_amazon_before_final() -> None:
    events = [
        _partial(0, "open amazon and", 0.1),
        _partial(0, "open amazon and scr", 0.2),
        _partial(0, "open amazon and scr", 0.3),
        _final(0, "open amazon and scroll down", 1.0),
    ]
    backend, _reports = _run_golden(events)
    first = backend.calls[0]
    assert first.name == "open_url"
    assert "amazon" in first.args[0]


def test_g4_revision_does_not_open_amazing() -> None:
    events = [
        _partial(0, "open amazing and", 0.1),
        _partial(0, "open amazon and", 0.2),
        _partial(0, "open amazon and", 0.3),
        _final(0, "open amazon and scroll down", 1.0),
    ]
    backend, _reports = _run_golden(events)
    open_urls = [call.args[0] for call in backend.calls if call.name == "open_url"]
    assert open_urls.count("https://www.amazon.com") == 1


def test_g5_click_orders_after_host_ready() -> None:
    page = FakePagePort(url="https://example.com/")
    page.elements["click orders"] = Intent(IntentType.CLICK_ELEMENT, target_id="e_orders")

    def advance(port: FakePagePort) -> None:
        port.url = "https://www.amazon.com/"

    events = [_final(0, "open amazon and click orders")]
    backend, _reports = _run_golden(events, page=page, advance_host=advance)
    names = [call.name for call in backend.calls]
    assert names.index("open_url") < names.index("click_element")


def test_g6_search_after_amazon_ready() -> None:
    page = FakePagePort(url="https://example.com/")

    def advance(port: FakePagePort) -> None:
        port.url = "https://www.amazon.com/"

    backend, _reports = _run_golden(
        [_final(0, "open amazon and search for headphones")],
        page=page,
        advance_host=advance,
    )
    assert any(call.name == "search_web" and call.args[0] == "headphones" for call in backend.calls)


def test_g7_host_never_ready_cancels_line() -> None:
    page = FakePagePort(url="https://example.com/")
    reports: list[StepReport] = []
    backend, line_reports = _run_golden(
        [
            _final(0, "open amazon and click orders"),
            _final(1, "open reddit"),
        ],
        page=page,
    )
    reports.extend(line_reports)
    assert any(report.outcome is StepOutcome.FAILED for report in reports)
    assert any(report.outcome is StepOutcome.CANCELLED for report in reports)
    assert any(call.name == "open_url" and "reddit" in call.args[0] for call in backend.calls)


def test_g8_notes_macro() -> None:
    focus = FakeFocus(app=None)

    def advance(_port: FakePagePort) -> None:
        focus.app = LaunchableApp.NOTES.value

    backend, _reports = _run_golden(
        [
            _final(
                0,
                "open notes then new note then type buy milk and eggs then press enter",
            )
        ],
        focus=focus,
        advance_host=advance,
    )
    assert backend.calls[0] == _BackendCall("open_app", (LaunchableApp.NOTES,))
    assert any(
        call.name == "press_key" and call.args[0] is PressableKey.NEW_ITEM for call in backend.calls
    )
    assert any(
        call.name == "type_focused" and call.args[0] == "buy milk and eggs"
        for call in backend.calls
    )
    assert any(
        call.name == "press_key" and call.args[0] is PressableKey.ENTER for call in backend.calls
    )


def test_g9_type_into_email_via_page() -> None:
    page = FakePagePort()
    page.elements["type hello into email"] = Intent(
        IntentType.TYPE_TEXT, target_id="e_email", text="hello"
    )
    backend, _reports = _run_golden([_final(0, "type hello into email")], page=page)
    assert backend.calls == [_BackendCall("type_text", ("e_email", "hello"))]


def test_g10_type_hello_fallback_when_bridge_down() -> None:
    page = FakePagePort(unavailable=True)
    backend, _reports = _run_golden([_final(0, "type hello")], page=page)
    assert backend.calls == [_BackendCall("type_focused", ("hello",))]


def test_g11_press_enter_is_key_not_page() -> None:
    backend, _reports = _run_golden([_final(0, "press enter")])
    assert backend.calls == [_BackendCall("press_key", (PressableKey.ENTER,))]
    assert not any(call.name == "click_element" for call in backend.calls)


def test_g12_brand_opens_correct_urls() -> None:
    for phrase, url in (
        ("open claude", "https://claude.ai"),
        ("open openai", "https://openai.com"),
        ("open chatgpt", "https://chatgpt.com"),
        ("open perplexity", "https://www.perplexity.ai"),
        ("open cloud ai", "https://claude.ai"),
    ):
        backend, _reports = _run_golden([_final(0, phrase)])
        assert backend.calls == [_BackendCall("open_url", (url,))]


def test_g13_ask_claude_macro() -> None:
    page = FakePagePort(url="https://example.com/")

    def advance(port: FakePagePort) -> None:
        port.url = "https://claude.ai/new"

    backend, _reports = _run_golden(
        [_final(0, "ask claude what is the capital of france")],
        page=page,
        advance_host=advance,
    )
    assert backend.calls[0] == _BackendCall("open_url", ("https://claude.ai/new",))
    assert any(call.name == "type_focused" and "france" in call.args[0] for call in backend.calls)
    assert backend.calls[-1] == _BackendCall("press_key", (PressableKey.ENTER,))


def test_g14_browse_prefixes_open_url() -> None:
    for phrase in ("browse to github.com", "take me to youtube"):
        backend, _reports = _run_golden([_final(0, phrase)])
        assert backend.calls and backend.calls[0].name == "open_url"


def test_g15_cancel_while_waiting() -> None:
    page = FakePagePort(url="https://example.com/")
    page.elements["click orders"] = Intent(IntentType.CLICK_ELEMENT, target_id="e_orders")
    events = [
        _final(0, "open amazon and click orders"),
        _final(1, "cancel"),
    ]
    backend, reports = _run_golden(events, page=page)
    assert not any(call.name == "click_element" for call in backend.calls)
    assert any(report.outcome is StepOutcome.CANCELLED for report in reports)


def test_g17_spike_repair_outputs() -> None:
    for raw, url in (
        ("Open Cloud.", "https://claude.ai"),
        ("Open up an A.", "https://openai.com"),
        ("OpenOpene.", "https://openai.com"),
    ):
        backend, _reports = _run_golden([_final(0, raw)])
        assert backend.calls == [_BackendCall("open_url", (url,))]
    page = FakePagePort(unavailable=True)
    backend, _reports = _run_golden([_final(0, "type cloud storage")], page=page)
    assert backend.calls == [_BackendCall("type_focused", ("cloud storage",))]


def test_g18_focused_field_edit_commands_flow_through_streaming_pipeline() -> None:
    commands = (
        ("unfocus app search bar", FocusedPageFieldAction.UNFOCUS),
        ("delete line", FocusedPageFieldAction.DELETE_LINE),
        ("clear search", FocusedPageFieldAction.CLEAR_SEARCH),
        ("delete word", FocusedPageFieldAction.DELETE_WORD),
    )
    events = [_final(index, phrase) for index, (phrase, _action) in enumerate(commands)]

    backend, reports = _run_golden(events)

    assert backend.calls == [
        _BackendCall("edit_focused_page_field", (action,)) for _phrase, action in commands
    ]
    assert all(report.outcome is StepOutcome.DONE for report in reports)


def test_g19_focused_field_edits_obey_safe_pause() -> None:
    backend, reports = _run_golden([_final(0, "delete line")], paused=True)

    assert backend.calls == []
    assert any(report.outcome is StepOutcome.SKIPPED_PAUSED for report in reports)


def test_g20_edit_words_remain_literal_when_used_as_text_or_query() -> None:
    typed, _typed_reports = _run_golden([_final(0, "type delete word")])
    searched, _search_reports = _run_golden([_final(0, "search for delete word")])

    assert typed.calls == [_BackendCall("type_focused", ("delete word",))]
    assert searched.calls == [_BackendCall("search_web", ("delete word",))]
