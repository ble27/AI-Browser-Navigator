"""Tests for the pill status hub."""

from __future__ import annotations

import threading

from gesture_control.actions import Intent, IntentType
from gesture_control.voice.status_hub import StatusHub, describe_step, report_event
from gesture_control.voice.stream_contracts import (
    CancelStep,
    Clause,
    PageStep,
    ResolvedStep,
    StepOutcome,
    StepReport,
)

_CLAUSE = Clause("scroll down", 0, 0, True)


def test_publish_reaches_every_subscriber() -> None:
    hub = StatusHub()
    first, second = hub.subscribe(), hub.subscribe()
    hub.publish({"type": "log", "line": "hi"})
    assert first.get(0.1) == {"type": "log", "line": "hi"}
    assert second.get(0.1) == {"type": "log", "line": "hi"}


def test_unsubscribed_consumer_gets_nothing() -> None:
    hub = StatusHub()
    sub = hub.subscribe()
    hub.unsubscribe(sub)
    hub.unsubscribe(sub)
    hub.publish({"type": "log"})
    assert sub.get(0.01) is None


def test_set_enabled_publishes_only_on_change() -> None:
    hub = StatusHub(enabled=True)
    sub = hub.subscribe()
    hub.set_enabled(True)
    assert sub.get(0.01) is None
    hub.set_enabled(False)
    assert sub.get(0.1) == {"type": "enabled", "enabled": False}
    assert hub.enabled is False


def test_snapshot_reports_state_and_recent_history() -> None:
    hub = StatusHub()
    for index in range(30):
        hub.publish({"type": "log", "n": index})
    snap = hub.snapshot()
    assert snap["enabled"] is True
    assert len(snap["events"]) == 20
    assert snap["events"][-1] == {"type": "log", "n": 29}


def test_slow_subscriber_drops_oldest_instead_of_blocking() -> None:
    hub = StatusHub()
    sub = hub.subscribe()
    for index in range(1000):
        hub.publish({"type": "log", "n": index})
    first = sub.get(0.1)
    assert first is not None and first["n"] >= 1000 - 256


def test_close_wakes_consumers_and_stops_publishing() -> None:
    hub = StatusHub()
    sub = hub.subscribe()
    seen: list[object] = []
    thread = threading.Thread(target=lambda: seen.append(sub.get(2.0)))
    thread.start()
    hub.close()
    thread.join(timeout=2.0)
    assert seen == [None]
    assert hub.closed
    hub.publish({"type": "log"})
    assert hub.snapshot()["events"] == []
    assert hub.subscribe().get(0.1) is None


def test_concurrent_publishers_lose_nothing_within_buffer() -> None:
    hub = StatusHub()
    sub = hub.subscribe()

    def work(base: int) -> None:
        for index in range(25):
            hub.publish({"type": "log", "n": base + index})

    threads = [threading.Thread(target=work, args=(base * 100,)) for base in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    received = 0
    while sub.get(0.01) is not None:
        received += 1
    assert received == 200


def test_step_labels() -> None:
    assert describe_step(PageStep(_CLAUSE, "click orders")) == "click orders"
    assert describe_step(ResolvedStep(_CLAUSE, Intent(IntentType.SCROLL, amount=3))) == "scroll"
    assert describe_step(CancelStep(_CLAUSE)) == "cancel"


def test_report_event_shape() -> None:
    report = StepReport(PageStep(_CLAUSE, "click orders"), StepOutcome.FAILED, "unresolved")
    assert report_event(report) == {
        "type": "step",
        "outcome": "failed",
        "label": "click orders",
        "detail": "unresolved",
    }
