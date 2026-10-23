"""Tests for pill accessibility settings."""

from __future__ import annotations

from gesture_control.actions import Intent, IntentType
from gesture_control.voice.planner import DeterministicClausePlanner
from gesture_control.voice.preferences import VoicePreferences, merge_preferences
from gesture_control.voice.scroll import parse_scroll_command
from gesture_control.voice.status_hub import StatusHub
from gesture_control.voice.stream_contracts import Clause, ResolvedStep


def test_plain_scroll_uses_the_selected_distance() -> None:
    assert parse_scroll_command("scroll down", default_pages=1) == Intent(
        IntentType.SCROLL, amount=-1
    )
    assert parse_scroll_command("scroll up", default_pages=6) == Intent(IntentType.SCROLL, amount=6)
    # Explicit counts and the little/large phrases still win.
    assert parse_scroll_command("scroll down 4 pages", default_pages=1) == Intent(
        IntentType.SCROLL, amount=-4
    )
    little = parse_scroll_command("scroll a little down", default_pages=6)
    assert little is not None and little.amount == -1


def test_planner_reads_live_scroll_preference() -> None:
    current = VoicePreferences(scroll="small")
    planner = DeterministicClausePlanner(preferences=lambda: current)
    step = planner.plan(Clause("scroll down", 0, 0, True))[0]
    assert isinstance(step, ResolvedStep)
    assert step.intent.amount == -1
    current = VoicePreferences(scroll="large")
    planner = DeterministicClausePlanner(preferences=lambda: current)
    step = planner.plan(Clause("scroll down", 0, 0, True))[0]
    assert isinstance(step, ResolvedStep)
    assert step.intent.amount == -6


def test_merge_rejects_unknown_values_and_keeps_omissions() -> None:
    current = VoicePreferences()
    assert merge_preferences(current, {"scroll": "huge"}) is None
    assert merge_preferences(current, {"highContrast": "yes"}) is None
    assert merge_preferences(current, []) is None
    merged = merge_preferences(current, {"textSize": "large"})
    assert merged == VoicePreferences(text_size="large")


def test_hub_publishes_a_settings_change_once() -> None:
    hub = StatusHub()
    sub = hub.subscribe()
    updated = hub.update_preferences({"scroll": "small", "typing": "steady"})
    assert updated is not None
    assert updated.scroll_pages() == 1
    assert updated.type_silence_s() == 0.6
    event = sub.get(0.2)
    assert event is not None
    assert event["type"] == "settings"
    assert event["scroll"] == "small"
    assert hub.update_preferences({"scroll": "small"}) == updated
    assert sub.get(0.01) is None
    stored = hub.snapshot()["settings"]
    assert isinstance(stored, dict)
    assert stored["typing"] == "steady"
