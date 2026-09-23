"""Homework / WebAssign-oriented page command vocabulary tests."""

from __future__ import annotations

from gesture_control.actions import Intent, IntentType
from gesture_control.voice.page import PageElement, index_html, resolve_page_command


def test_answer_is_types_into_unique_answer_field() -> None:
    elements = (
        PageElement("a1", "textbox", "Answer"),
        PageElement("s1", "button", "Submit Answer"),
    )

    assert resolve_page_command("answer is 42", elements) == Intent(
        IntentType.TYPE_TEXT, target_id="a1", text="42"
    )
    assert resolve_page_command("the answer is 3.14", elements) == Intent(
        IntentType.TYPE_TEXT, target_id="a1", text="3.14"
    )


def test_answer_falls_back_to_sole_textbox() -> None:
    elements = (PageElement("only", "textbox", "Response"),)

    assert resolve_page_command("answer is hello world", elements) == Intent(
        IntentType.TYPE_TEXT, target_id="only", text="hello world"
    )


def test_submit_answer_clicks_unique_submit_button() -> None:
    elements = (
        PageElement("a1", "textbox", "Answer"),
        PageElement("s1", "button", "Submit Answer"),
    )

    assert resolve_page_command("submit answer", elements) == Intent(
        IntentType.CLICK_ELEMENT, target_id="s1"
    )
    assert resolve_page_command("submit", elements) == Intent(
        IntentType.CLICK_ELEMENT, target_id="s1"
    )


def test_numbered_answer_fields_are_addressable() -> None:
    elements = (
        PageElement("a1", "textbox", "Answer"),
        PageElement("a2", "textbox", "Answer"),
        PageElement("s1", "button", "Submit"),
    )

    assert resolve_page_command("type 9 into answer 1", elements) == Intent(
        IntentType.TYPE_TEXT, target_id="a1", text="9"
    )
    assert resolve_page_command("type 8 into second answer", elements) == Intent(
        IntentType.TYPE_TEXT, target_id="a2", text="8"
    )
    assert resolve_page_command("answer is 7", elements) is None


def test_index_html_names_submit_input_from_value() -> None:
    elements = index_html(
        '<label for="answer">Answer</label>'
        '<input id="answer" name="answer" type="text">'
        '<input type="submit" value="Submit Answer">'
    )

    assert any(el.role == "button" and el.name == "Submit Answer" for el in elements)
    assert resolve_page_command("submit answer", elements) is not None
