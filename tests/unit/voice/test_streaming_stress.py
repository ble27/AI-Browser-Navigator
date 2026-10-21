"""Stress tests for the streaming voice pipeline, end to end.

These drive the real ``StreamingVoiceAgent`` (repair, debounce, policy,
segmenter, planner, executor, ``ActionMapper``) with word-by-word partials,
real timers, and a recording backend. No microphone, browser, or OS input.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import pytest
from gesture_control.actions import ActionMapper
from gesture_control.backends.base import SafePause
from gesture_control.voice.executor import QueuedStepExecutor
from gesture_control.voice.planner import DeterministicClausePlanner
from gesture_control.voice.segmenter import DeterministicClauseSegmenter
from gesture_control.voice.stream_contracts import (
    StepOutcome,
    StepReport,
    TranscriptEvent,
    TranscriptEventKind,
)
from gesture_control.voice.streaming_agent import StreamingVoiceAgent

from .test_streaming_golden import (
    FakeFocus,
    FakePagePort,
    RecordingBackend,
    _BackendCall,
)


class _FollowingBackend(RecordingBackend):
    """Recording backend whose fake page URL follows ``open_url`` calls."""

    def __init__(self, page: FakePagePort) -> None:
        super().__init__()
        self._page = page

    def open_url(self, url: str) -> None:
        if not self.safe_pause.is_paused:
            self._page.url = url
        super().open_url(url)


class _ManualTranscriber:
    """Transcriber stand-in that lets the test push events directly."""

    def __init__(self) -> None:
        self.sink: Callable[[TranscriptEvent], None] | None = None

    def start(self, sink: Callable[[TranscriptEvent], None]) -> None:
        self.sink = sink

    def stop(self) -> None:
        self.sink = None


@dataclass
class Rig:
    """Fully wired pipeline plus the observation points tests need."""

    agent: StreamingVoiceAgent
    backend: _FollowingBackend
    pause: SafePause
    transcriber: _ManualTranscriber
    reports: list[StepReport] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    _line: int = 0

    def speak(self, text: str, *, jitter: random.Random | None = None) -> None:
        """Emit ``text`` as growing word partials followed by one FINAL."""
        assert self.transcriber.sink is not None
        line_id = self._line
        self._line += 1
        words = text.split()
        for count in range(1, len(words) + 1):
            self.transcriber.sink(
                TranscriptEvent(
                    TranscriptEventKind.PARTIAL,
                    " ".join(words[:count]),
                    line_id,
                    time.monotonic(),
                )
            )
            if jitter is not None:
                time.sleep(jitter.uniform(0.0, 0.004))
        self.transcriber.sink(
            TranscriptEvent(TranscriptEventKind.FINAL, text, line_id, time.monotonic())
        )

    def calls(self, name: str) -> list[_BackendCall]:
        """Return recorded backend calls with the given operation name."""
        return [call for call in self.backend.calls if call.name == name]

    def wait_idle(self, quiet_s: float = 0.25) -> None:
        """Block until no new backend call or report appears for ``quiet_s``."""
        last = (-1, -1)
        stable_since = time.monotonic()
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            now = (len(self.backend.calls), len(self.reports))
            if now != last:
                last = now
                stable_since = time.monotonic()
            elif time.monotonic() - stable_since >= quiet_s:
                return
            time.sleep(0.01)
        raise AssertionError("pipeline never went idle")


@contextmanager
def _rig(*, paused: bool = False) -> Iterator[Rig]:
    page = FakePagePort(url="https://example.com/")
    backend = _FollowingBackend(page)
    pause = SafePause(paused=paused)
    backend.safe_pause = pause
    reports: list[StepReport] = []
    lines: list[str] = []
    executor = QueuedStepExecutor(
        mapper=ActionMapper(backend),
        page=page,
        focus=FakeFocus(),
        safe_pause=pause,
        report=reports.append,
        sleep=lambda _s: time.sleep(0.001),
    )
    transcriber = _ManualTranscriber()
    agent = StreamingVoiceAgent(
        transcriber,
        DeterministicClauseSegmenter(),
        DeterministicClausePlanner(),
        executor,
        output=lines.append,
        debounce_s=0.01,
        fast_debounce_s=0.005,
        free_text_silence_s=0.05,
    )
    agent.start()
    rig = Rig(agent, backend, pause, transcriber, reports, lines)
    try:
        yield rig
    finally:
        agent.stop()
        executor.close()


# (spoken phrase, expected ordered backend operation names)
_CORPUS: list[tuple[str, list[str]]] = [
    ("open reddit", ["open_url"]),
    ("open github", ["open_url"]),
    ("open youtube", ["open_url"]),
    ("next tab", ["navigate_browser"]),
    ("previous tab", ["navigate_browser"]),
    ("scroll down", ["scroll"]),
    ("scroll up", ["scroll"]),
    ("press enter", ["press_key"]),
    ("go back", ["navigate_browser"]),
    ("reload", ["navigate_browser"]),
    ("search for wireless headphones", ["search_web"]),
    ("open amazon and scroll down", ["open_url", "scroll"]),
    ("open reddit then next tab", ["open_url", "navigate_browser"]),
    ("open youtube and scroll down and next tab", ["open_url", "scroll", "navigate_browser"]),
]


@pytest.mark.parametrize(("phrase", "expected"), _CORPUS)
def test_each_phrase_dispatches_exactly_once_despite_partials(
    phrase: str, expected: list[str]
) -> None:
    """A phrase spoken word-by-word must act once, not once per partial."""
    with _rig() as rig:
        rig.speak(phrase)
        rig.wait_idle()
        assert [call.name for call in rig.backend.calls] == expected
        assert all(r.outcome is StepOutcome.DONE for r in rig.reports)


def test_corpus_replayed_back_to_back_with_jitter() -> None:
    """Every corpus phrase in a row, with random inter-word timing."""
    jitter = random.Random(7)
    with _rig() as rig:
        expected: list[str] = []
        for phrase, ops in _CORPUS:
            rig.speak(phrase, jitter=jitter)
            expected.extend(ops)
        rig.wait_idle()
        assert [call.name for call in rig.backend.calls] == expected


def test_rapid_fire_two_hundred_lines_no_loss_no_duplicates() -> None:
    """Hammer the agent with 200 closed-set commands as fast as possible."""
    with _rig() as rig:
        for _ in range(200):
            rig.speak("scroll down")
        rig.wait_idle(quiet_s=0.4)
        assert len(rig.calls("scroll")) == 200
        assert not [r for r in rig.reports if r.outcome is StepOutcome.FAILED]


def test_misheard_revision_never_opens_wrong_site() -> None:
    """Partials that revise ``amazing`` -> ``amazon`` must open Amazon only."""
    with _rig() as rig:
        assert rig.transcriber.sink is not None
        sink = rig.transcriber.sink
        for text in ("open amazing", "open amazon", "open amazon"):
            sink(TranscriptEvent(TranscriptEventKind.PARTIAL, text, 0, time.monotonic()))
            time.sleep(0.03)
        sink(TranscriptEvent(TranscriptEventKind.FINAL, "open amazon", 0, time.monotonic()))
        rig.wait_idle()
        urls = [call.args[0] for call in rig.calls("open_url")]
        assert urls == ["https://www.amazon.com"]


def test_safe_pause_blocks_everything_then_resume_recovers() -> None:
    """Paused input injects nothing; after resume the pipeline works again."""
    with _rig(paused=True) as rig:
        for phrase in ("open reddit", "next tab", "scroll down", "press enter"):
            rig.speak(phrase)
        rig.wait_idle()
        assert rig.backend.calls == []
        assert any(r.outcome is StepOutcome.SKIPPED_PAUSED for r in rig.reports)

        rig.pause.toggle()
        rig.speak("scroll down")
        rig.wait_idle()
        assert [c.name for c in rig.backend.calls] == ["scroll"]


def test_pause_toggled_while_speaking_never_leaks_input() -> None:
    """Toggle pause from another thread during a burst; no call under pause."""
    with _rig() as rig:
        stop = threading.Event()
        violations: list[str] = []
        original = rig.backend.scroll

        def guarded_scroll(amount: int) -> None:
            if rig.pause.is_paused:
                violations.append("scroll ran while paused")
            original(amount)

        rig.backend.scroll = guarded_scroll  # type: ignore[method-assign]

        def toggler() -> None:
            while not stop.is_set():
                rig.pause.toggle()
                time.sleep(0.002)

        thread = threading.Thread(target=toggler, daemon=True)
        thread.start()
        try:
            for _ in range(60):
                rig.speak("scroll down")
        finally:
            stop.set()
            thread.join(timeout=2.0)
        rig.wait_idle()
        assert violations == []


def test_cancel_drops_queued_work() -> None:
    """``cancel`` after an unready page step must not let the step fire."""
    with _rig() as rig:
        rig.speak("open amazon and click orders")
        rig.speak("cancel")
        rig.wait_idle(quiet_s=0.4)
        assert not rig.calls("click_element")


def test_duplicate_final_events_do_not_double_dispatch() -> None:
    """The same FINAL delivered with a new line id is a new utterance; the
    identical event repeated on one line id must not repeat the action."""
    with _rig() as rig:
        assert rig.transcriber.sink is not None
        for _ in range(3):
            rig.transcriber.sink(
                TranscriptEvent(TranscriptEventKind.FINAL, "next tab", 0, time.monotonic())
            )
        rig.wait_idle()
        assert len(rig.calls("navigate_browser")) <= 1


_NEUTRAL_WORDS = [
    "banana",
    "purple",
    "elephant",
    "umbrella",
    "mountain",
    "guitar",
    "window",
    "river",
    "pencil",
    "sunset",
]


def test_non_command_chatter_never_injects_input() -> None:
    """Ordinary conversation must not move the mouse or press keys."""
    rng = random.Random(1234)
    with _rig() as rig:
        for _ in range(40):
            sentence = " ".join(rng.choice(_NEUTRAL_WORDS) for _ in range(rng.randint(2, 9)))
            rig.speak(sentence)
        rig.wait_idle()
        assert rig.backend.calls == []


_FUZZ_VOCAB = [
    "open",
    "click",
    "type",
    "search",
    "for",
    "scroll",
    "tab",
    "next",
    "press",
    "enter",
    "and",
    "then",
    "the",
    "up",
    "down",
    "reddit",
    "amazon",
    "cancel",
    "confirm",
    "delete",
    "close",
    "",
    "...",
    "ÜñíçødE",
]


def test_fuzzed_word_salad_never_raises_or_hangs() -> None:
    """Random command-ish words in random order: no crash, no hang."""
    rng = random.Random(99)
    with _rig() as rig:
        for _ in range(150):
            text = " ".join(rng.choice(_FUZZ_VOCAB) for _ in range(rng.randint(1, 12)))
            rig.speak(text or "x")
        rig.wait_idle(quiet_s=0.5)
        # Every report is a legal outcome; the worker thread is still alive.
        assert all(isinstance(r.outcome, StepOutcome) for r in rig.reports)
        assert not rig.pause.is_paused
        rig.speak("scroll down")
        rig.wait_idle()
        assert rig.calls("scroll")


def test_destructive_click_needs_confirmation() -> None:
    """A destructive page phrase is held until the user says confirm."""
    with _rig() as rig:
        rig.speak("click delete account")
        rig.wait_idle()
        before = len(rig.calls("click_element"))
        assert before == 0
        assert any("confirm needed" in line for line in rig.lines)
