"""Tests for desktop streaming voice parsers."""

from __future__ import annotations

from gesture_control.actions import Intent, IntentType
from gesture_control.backends.base import LaunchableApp, PressableKey
from gesture_control.voice.desktop import (
    parse_app_command,
    parse_ask_command,
    parse_control_command,
    parse_key_command,
    parse_type_command,
)


def test_parse_control_command() -> None:
    assert parse_control_command("cancel") is True
    assert parse_control_command("never mind") is True
    assert parse_control_command("open reddit") is False


def test_parse_key_command_beats_page_press() -> None:
    intent = parse_key_command("press enter")
    assert intent == Intent(IntentType.PRESS_KEY, key=PressableKey.ENTER)


def test_parse_app_command_open_notes() -> None:
    intent = parse_app_command("open notes")
    assert intent == Intent(IntentType.OPEN_APP, app=LaunchableApp.NOTES)


def test_site_beats_app_without_app_suffix() -> None:
    assert parse_app_command("open cursor") is None


def test_parse_app_command_with_suffix() -> None:
    intent = parse_app_command("open cursor app")
    assert intent == Intent(IntentType.OPEN_APP, app=LaunchableApp.CURSOR)


def test_parse_type_command_literal_and_target() -> None:
    assert parse_type_command("type hello").text == "hello"
    assert parse_type_command("type hello").has_target is False
    assert parse_type_command("type hello into email").has_target is True


def test_parse_ask_command_claude() -> None:
    ask = parse_ask_command("ask claude what is two plus two")
    assert ask is not None
    assert ask.url == "https://claude.ai/new"
    assert ask.host == "claude.ai"
    assert "two plus two" in ask.query
