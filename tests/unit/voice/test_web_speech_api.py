"""Tests for the pill UI API served by the Web Speech bridge."""

from __future__ import annotations

import http.client
import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from gesture_control.voice.status_hub import StatusHub
from gesture_control.voice.stream_contracts import TranscriptEvent
from gesture_control.voice.web_speech import WebSpeechStreamingTranscriber


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[WebSpeechStreamingTranscriber, StatusHub, list]]:
    (tmp_path / "index.html").write_text("<html>pill</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("nope")
    hub = StatusHub()
    events: list[TranscriptEvent] = []
    bridge = WebSpeechStreamingTranscriber(hub=hub, static_dir=tmp_path)
    bridge.start(events.append)
    try:
        yield bridge, hub, events
    finally:
        bridge.stop()
        hub.close()


def _request(
    bridge: WebSpeechStreamingTranscriber,
    method: str,
    path: str,
    body: object | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    conn = http.client.HTTPConnection("127.0.0.1", bridge.port, timeout=3)
    payload = None if body is None else json.dumps(body)
    conn.request(method, path, body=payload, headers=headers or {})
    response = conn.getresponse()
    data = response.read()
    result = (response.status, data, dict(response.getheaders()))
    conn.close()
    return result


def test_state_endpoint_reports_enabled_flag(served) -> None:
    bridge, hub, _events = served
    status, body, _ = _request(bridge, "GET", "/api/state")
    assert status == 200
    assert json.loads(body)["enabled"] is True
    hub.set_enabled(False)
    assert json.loads(_request(bridge, "GET", "/api/state")[1])["enabled"] is False


def test_enabled_endpoint_toggles_hub(served) -> None:
    bridge, hub, _events = served
    status, body, _ = _request(bridge, "POST", "/api/enabled", {"enabled": False})
    assert status == 200 and json.loads(body) == {"enabled": False}
    assert hub.enabled is False


@pytest.mark.parametrize("payload", [{"enabled": "yes"}, {"enabled": 1}, {}, [], "on"])
def test_enabled_endpoint_rejects_non_bool(served, payload: object) -> None:
    bridge, hub, _events = served
    assert _request(bridge, "POST", "/api/enabled", payload)[0] == 400
    assert hub.enabled is True


def test_transcripts_are_dropped_while_disabled(served) -> None:
    bridge, hub, events = served
    hub.set_enabled(False)
    assert _request(bridge, "POST", "/transcript", {"kind": "final", "text": "next tab"})[0] == 204
    assert events == []
    hub.set_enabled(True)
    _request(bridge, "POST", "/transcript", {"kind": "final", "text": "next tab"})
    assert [event.text for event in events] == ["next tab"]


def test_transcript_is_mirrored_to_the_ui(served) -> None:
    bridge, hub, _events = served
    sub = hub.subscribe()
    _request(bridge, "POST", "/transcript", {"kind": "partial", "text": "open reddit"})
    assert sub.get(1.0) == {"type": "transcript", "kind": "partial", "text": "open reddit"}


def test_sse_stream_sends_state_then_live_events(served) -> None:
    bridge, hub, _events = served
    conn = http.client.HTTPConnection("127.0.0.1", bridge.port, timeout=3)
    conn.request("GET", "/api/events")
    response = conn.getresponse()
    assert response.status == 200
    assert response.getheader("Content-Type") == "text/event-stream"
    first = response.fp.readline().decode()  # type: ignore[union-attr]
    assert first.startswith("data: ") and json.loads(first[6:])["type"] == "state"
    response.fp.readline()  # type: ignore[union-attr]
    hub.publish({"type": "log", "line": "hello"})
    line = response.fp.readline().decode()  # type: ignore[union-attr]
    assert json.loads(line[6:]) == {"type": "log", "line": "hello"}
    conn.close()


def test_stop_ends_open_event_streams_promptly(served) -> None:
    bridge, _hub, _events = served
    conn = http.client.HTTPConnection("127.0.0.1", bridge.port, timeout=3)
    conn.request("GET", "/api/events")
    response = conn.getresponse()
    response.fp.readline()  # type: ignore[union-attr]
    started = time.monotonic()
    stopper = threading.Thread(target=bridge.stop)
    stopper.start()
    stopper.join(timeout=5)
    assert not stopper.is_alive()
    assert time.monotonic() - started < 4
    conn.close()


def test_static_ui_is_served_and_cannot_escape_root(served) -> None:
    bridge, _hub, _events = served
    status, body, headers = _request(bridge, "GET", "/")
    assert status == 200 and body == b"<html>pill</html>"
    assert headers["Content-Type"].startswith("text/html")
    status, body, headers = _request(bridge, "GET", "/assets/app.js")
    assert status == 200 and "javascript" in headers["Content-Type"]
    assert _request(bridge, "GET", "/%2e%2e/secret.txt")[0] == 404
    assert _request(bridge, "GET", "/..%2fsecret.txt")[0] == 404
    assert _request(bridge, "GET", "/assets/missing.js")[0] == 404


def test_foreign_origin_and_host_are_rejected(served) -> None:
    bridge, hub, events = served
    evil = {"Origin": "https://evil.example"}
    assert _request(bridge, "POST", "/transcript", {"kind": "final", "text": "x"}, evil)[0] == 403
    assert _request(bridge, "POST", "/api/enabled", {"enabled": False}, evil)[0] == 403
    assert _request(bridge, "GET", "/api/state", headers={"Host": "evil.example"})[0] == 403
    assert hub.enabled is True and events == []


def test_settings_round_trip_and_reject_unknown_values(served) -> None:
    bridge, hub, _events = served
    status, body, _headers = _request(bridge, "GET", "/api/settings")
    assert status == 200
    assert json.loads(body)["scroll"] == "medium"
    status, body, _headers = _request(
        bridge, "POST", "/api/settings", {"scroll": "large", "highContrast": True}
    )
    assert status == 200
    assert json.loads(body)["scroll"] == "large"
    assert hub.preferences().high_contrast is True
    assert _request(bridge, "POST", "/api/settings", {"scroll": "huge"})[0] == 400
    assert hub.preferences().scroll == "large"


def test_same_origin_is_accepted(served) -> None:
    bridge, _hub, _events = served
    origin = {"Origin": f"http://127.0.0.1:{bridge.port}"}
    assert _request(bridge, "GET", "/api/state", headers=origin)[0] == 200


def test_api_is_absent_without_a_hub() -> None:
    bridge = WebSpeechStreamingTranscriber()
    bridge.start(lambda _event: None)
    try:
        assert _request(bridge, "GET", "/api/state")[0] == 404
        assert _request(bridge, "POST", "/api/enabled", {"enabled": True})[0] == 404
    finally:
        bridge.stop()
