"""Integration test: pill UI requests -> bridge -> agent -> backend -> UI events."""

from __future__ import annotations

import http.client
import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from gesture_control.actions import ActionMapper
from gesture_control.backends.base import SafePause
from gesture_control.voice.executor import QueuedStepExecutor
from gesture_control.voice.pill_wiring import (
    default_pill_dir,
    mirror_output,
    mirror_reports,
)
from gesture_control.voice.planner import DeterministicClausePlanner
from gesture_control.voice.segmenter import DeterministicClauseSegmenter
from gesture_control.voice.status_hub import StatusHub, Subscription
from gesture_control.voice.streaming_agent import StreamingVoiceAgent
from gesture_control.voice.web_speech import WebSpeechStreamingTranscriber

from .test_streaming_golden import FakeFocus, FakePagePort, RecordingBackend


@dataclass
class Session:
    port: int
    hub: StatusHub
    backend: RecordingBackend
    events: Subscription

    def post(self, path: str, body: object) -> int:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        conn.request("POST", path, body=json.dumps(body))
        status = conn.getresponse().status
        conn.close()
        return status

    def speak(self, kind: str, text: str) -> None:
        assert self.post("/transcript", {"kind": kind, "text": text}) == 204

    def wait_for(self, predicate: object, timeout_s: float = 3.0) -> list[dict]:
        """Collect hub events until ``predicate(events)`` holds."""
        seen: list[dict] = []
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            event = self.events.get(0.05)
            if event is not None:
                seen.append(event)
            if predicate(seen):  # type: ignore[operator]
                return seen
        raise AssertionError(f"timed out; saw {seen}")


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    (tmp_path / "index.html").write_text("<html></html>")
    hub = StatusHub()
    backend = RecordingBackend()
    pause = SafePause()
    backend.safe_pause = pause
    executor = QueuedStepExecutor(
        mapper=ActionMapper(backend),
        page=FakePagePort(),
        focus=FakeFocus(),
        safe_pause=pause,
        report=mirror_reports(hub, lambda _report: None),
    )
    transcriber = WebSpeechStreamingTranscriber(hub=hub, static_dir=tmp_path)
    agent = StreamingVoiceAgent(
        transcriber,
        DeterministicClauseSegmenter(),
        DeterministicClausePlanner(),
        executor,
        output=mirror_output(hub, lambda _line: None),
        debounce_s=0.01,
        fast_debounce_s=0.005,
    )
    agent.start()
    events = hub.subscribe()
    try:
        yield Session(transcriber.port, hub, backend, events)
    finally:
        agent.stop()
        executor.close()
        hub.close()


def test_spoken_command_runs_and_ui_sees_each_stage(session: Session) -> None:
    session.speak("partial", "scroll")
    session.speak("partial", "scroll down")
    session.speak("final", "scroll down")
    # The agent may act on the stable partial before the final arrives, so wait
    # for both rather than assuming an order.
    events = session.wait_for(
        lambda seen: any(e["type"] == "step" for e in seen)
        and any(e.get("kind") == "final" for e in seen)
    )

    assert [call.name for call in session.backend.calls] == ["scroll"]
    kinds = [(e["type"], e.get("kind")) for e in events]
    assert ("transcript", "partial") in kinds and ("transcript", "final") in kinds
    step = next(e for e in events if e["type"] == "step")
    assert step == {"type": "step", "outcome": "done", "label": "scroll", "detail": "dispatched"}
    assert any(e["type"] == "log" and "scroll down" in e["line"] for e in events)


def test_toggle_off_blocks_commands_and_toggle_on_restores_them(session: Session) -> None:
    assert session.post("/api/enabled", {"enabled": False}) == 200
    session.speak("final", "scroll down")
    time.sleep(0.2)
    assert session.backend.calls == []

    assert session.post("/api/enabled", {"enabled": True}) == 200
    session.speak("final", "scroll down")
    session.wait_for(lambda seen: any(e["type"] == "step" for e in seen))
    assert [call.name for call in session.backend.calls] == ["scroll"]


def test_unknown_page_phrase_reports_a_failure_to_the_ui(session: Session) -> None:
    session.speak("final", "click flux capacitor")
    events = session.wait_for(lambda seen: any(e["type"] == "step" for e in seen))
    step = next(e for e in events if e["type"] == "step")
    assert step["outcome"] == "failed"
    assert session.backend.calls == []


def test_default_pill_dir_requires_a_build(tmp_path: Path) -> None:
    assert default_pill_dir(tmp_path) is None
    (tmp_path / "index.html").write_text("x")
    assert default_pill_dir(tmp_path) == tmp_path
