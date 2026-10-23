"""Tests for desktop streaming voice parsers."""

from __future__ import annotations

from gesture_control.actions import Intent, IntentType
from gesture_control.backends.base import FocusedPageFieldAction, LaunchableApp, PressableKey
from gesture_control.voice.commands import parse_command
from gesture_control.voice.desktop import (
    parse_app_command,
    parse_ask_command,
    parse_chrome_omnibox_focus_command,
    parse_control_command,
    parse_focused_page_field_command,
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


def test_parse_key_command_accepts_click_and_return_phrasing() -> None:
    for phrase in ("click enter", "tap enter", "hit return", "press return", "click return"):
        assert parse_key_command(phrase) == Intent(IntentType.PRESS_KEY, key=PressableKey.ENTER)


def test_parse_key_command_accepts_bare_enter_and_done() -> None:
    for phrase in ("enter", "done"):
        assert parse_key_command(phrase) == Intent(IntentType.PRESS_KEY, key=PressableKey.ENTER)


def test_parse_key_command_accepts_mac_return_phrasing() -> None:
    for phrase in ("return", "tap return", "press the return key", "hit the return key"):
        assert parse_command(phrase) == Intent(IntentType.PRESS_KEY, key=PressableKey.ENTER)


def test_parse_chrome_omnibox_focus_command_is_explicit() -> None:
    for phrase in (
        "focus Chrome search bar",
        "focus Chrome address bar",
        "focus Chrome omnibox",
    ):
        assert parse_chrome_omnibox_focus_command(phrase) == Intent(IntentType.FOCUS_CHROME_OMNIBOX)
    assert parse_chrome_omnibox_focus_command("focus app search bar") is None


def test_focused_page_field_commands_are_exact_and_targeted() -> None:
    for phrase in (
        "unfocus",
        "unfocus app search bar",
        "unfocus composer",
        "stop focus",
        "stop focusing",
        "stop focus on search bar",
    ):
        assert parse_focused_page_field_command(phrase) == Intent(
            IntentType.EDIT_FOCUSED_PAGE_FIELD,
            field_action=FocusedPageFieldAction.UNFOCUS,
        )
    assert parse_focused_page_field_command("delete line") == Intent(
        IntentType.EDIT_FOCUSED_PAGE_FIELD,
        field_action=FocusedPageFieldAction.DELETE_LINE,
    )
    for phrase in ("clear search", "clear search bar", "delete search"):
        assert parse_focused_page_field_command(phrase) == Intent(
            IntentType.EDIT_FOCUSED_PAGE_FIELD,
            field_action=FocusedPageFieldAction.CLEAR_SEARCH,
        )
    for phrase in ("delete word", "delete previous word"):
        assert parse_focused_page_field_command(phrase) == Intent(
            IntentType.EDIT_FOCUSED_PAGE_FIELD,
            field_action=FocusedPageFieldAction.DELETE_WORD,
        )
    assert parse_focused_page_field_command("unfocus notes") is None


def test_delete_commands_do_not_filter_literal_dictation_or_searches() -> None:
    assert parse_command("type delete word") == Intent(
        IntentType.TYPE_FOCUSED,
        text="delete word",
    )
    assert parse_command("search for delete word") == Intent(
        IntentType.SEARCH_WEB,
        text="delete word",
    )


def test_one_shot_parser_supports_focus_compose_sequence_phrases() -> None:
    assert parse_command("focus Chrome search bar") == Intent(IntentType.FOCUS_CHROME_OMNIBOX)
    assert parse_command("type hello world") == Intent(IntentType.TYPE_FOCUSED, text="hello world")
    assert parse_command("done") == Intent(IntentType.PRESS_KEY, key=PressableKey.ENTER)


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
    assert parse_type_command("Type, I love you").text == "I love you"
    assert parse_type_command("type I love you in notes").text == "I love you"


def test_parse_ask_command_claude() -> None:
    ask = parse_ask_command("ask claude what is two plus two")
    assert ask is not None
    assert ask.url == "https://claude.ai/new"
    assert ask.host == "claude.ai"
    assert "two plus two" in ask.query


def test_parse_ask_bare_opens_assistant() -> None:
    ask = parse_ask_command("ask chatgpt")
    assert ask is not None
    assert ask.url == "https://chatgpt.com"
    assert ask.query == ""
