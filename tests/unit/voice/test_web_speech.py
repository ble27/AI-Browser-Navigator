"""Tests for the Chrome Web Speech streaming bridge."""

from __future__ import annotations

import json
import urllib.request

import pytest
from gesture_control.voice.stream_contracts import TranscriptEvent, TranscriptEventKind
from gesture_control.voice.web_speech import WebSpeechStreamingTranscriber


def test_loopback_only() -> None:
    with pytest.raises(ValueError, match="loopback"):
        WebSpeechStreamingTranscriber(host="0.0.0.0")


def test_stop_before_start_is_safe() -> None:
    WebSpeechStreamingTranscriber().stop()


def test_partial_and_final_share_a_line_then_advance() -> None:
    events: list[TranscriptEvent] = []
    transcriber = WebSpeechStreamingTranscriber()
    transcriber.start(events.append)
    try:
        transcriber.submit({"kind": "partial", "text": "open reddit"})
        transcriber.submit({"kind": "partial", "text": "open reddit"})
        transcriber.submit({"kind": "final", "text": "open  reddit"})
        transcriber.submit({"kind": "partial", "text": "next tab"})
    finally:
        transcriber.stop()

    assert [(event.kind, event.text, event.line_id) for event in events] == [
        (TranscriptEventKind.PARTIAL, "open reddit", 0),
        (TranscriptEventKind.FINAL, "open reddit", 0),
        (TranscriptEventKind.PARTIAL, "next tab", 1),
    ]


def test_blank_and_unknown_payloads_are_ignored() -> None:
    events: list[TranscriptEvent] = []
    transcriber = WebSpeechStreamingTranscriber()
    transcriber.start(events.append)
    try:
        assert transcriber.submit({"kind": "partial", "text": "   "}) is None
        assert transcriber.submit({"kind": "caption", "text": "open reddit"}) is None
        assert transcriber.submit("open reddit") is None
    finally:
        transcriber.stop()
    assert events == []


def test_http_post_reaches_the_agent_sink() -> None:
    events: list[TranscriptEvent] = []
    opened: list[str] = []
    transcriber = WebSpeechStreamingTranscriber(
        open_browser=True,
        browser_opener=opened.append,
    )
    transcriber.start(events.append)
    try:
        assert opened == [transcriber.control_url]
        page = urllib.request.urlopen(transcriber.control_url, timeout=2)
        html = page.read().decode("utf-8")
        assert "webkitSpeechRecognition" in html
        body = json.dumps({"kind": "final", "text": "next tab"}).encode("utf-8")
        request = urllib.request.Request(
            transcriber.control_url + "transcript",
            data=body,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            assert response.status == 204
    finally:
        transcriber.stop()

    assert len(events) == 1
    assert events[0].kind is TranscriptEventKind.FINAL
    assert events[0].text == "next tab"
    assert events[0].line_id == 0
