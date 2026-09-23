"""Tests for resolving spoken page commands onto indexed elements.

Covers click and type-into-field resolution via ``resolve_page_command``. Type
cases stay red until ``TYPE_TEXT`` and ``Intent.text`` exist. No Chrome,
extension, or network is involved.
"""

from __future__ import annotations

from gesture_control.actions import Intent, IntentType
from gesture_control.voice.page import PageElement, index_html, resolve_page_command


def test_click_on_log_in_selects_the_matching_button() -> None:
    """``click on log in`` should target the button named Log in."""
    elements = (
        PageElement(element_id="e1", role="button", name="Log in"),
        PageElement(element_id="e2", role="link", name="Home"),
    )

    intent = resolve_page_command("click on log in", elements)

    assert intent == Intent(IntentType.CLICK_ELEMENT, target_id="e1")


def test_click_phrase_is_case_insensitive() -> None:
    """Mixed-case click phrases should still match the Log in button."""
    elements = (
        PageElement(element_id="e1", role="button", name="Log in"),
        PageElement(element_id="e2", role="link", name="Home"),
    )

    intent = resolve_page_command("Click on LOG IN", elements)

    assert intent == Intent(IntentType.CLICK_ELEMENT, target_id="e1")


def test_click_without_on_still_matches() -> None:
    """``click`` without ``on`` should still select the Home link."""
    elements = (
        PageElement(element_id="e1", role="button", name="Log in"),
        PageElement(element_id="e2", role="link", name="Home"),
    )

    intent = resolve_page_command("click home", elements)

    assert intent == Intent(IntentType.CLICK_ELEMENT, target_id="e2")


def test_unknown_name_returns_none() -> None:
    """A spoken name with no matching element must return None."""
    elements = (
        PageElement(element_id="e1", role="button", name="Log in"),
        PageElement(element_id="e2", role="link", name="Home"),
    )

    assert resolve_page_command("click on settings", elements) is None


def test_two_buttons_with_the_same_name_are_ambiguous() -> None:
    """Two clickable elements sharing a name must not pick one at random."""
    elements = (
        PageElement(element_id="e1", role="button", name="Log in"),
        PageElement(element_id="e2", role="button", name="Log in"),
    )

    assert resolve_page_command("click on log in", elements) is None


def test_click_does_not_activate_a_textbox() -> None:
    """Click resolution must ignore textboxes even when the name matches."""
    elements = (PageElement(element_id="e1", role="textbox", name="Email"),)

    assert resolve_page_command("click on email", elements) is None


def test_indexed_log_in_button_can_be_clicked_by_name() -> None:
    """``index_html`` and ``resolve_page_command`` compose for a Log in button."""
    elements = index_html("""<button>Log in</button>""")

    intent = resolve_page_command("click on log in", elements)

    assert intent == Intent(IntentType.CLICK_ELEMENT, target_id="e1")


def test_type_hello_into_email_targets_the_textbox() -> None:
    """``type hello into email`` should target the Email textbox."""
    elements = (
        PageElement(element_id="e1", role="textbox", name="Email"),
        PageElement(element_id="e2", role="button", name="Log in"),
    )

    intent = resolve_page_command("type hello into email", elements)

    assert intent == Intent(IntentType.TYPE_TEXT, target_id="e1", text="hello")


def test_type_phrase_matches_the_field_name_case_insensitively() -> None:
    """Field matching is case-insensitive; typed text casing is preserved."""
    elements = (
        PageElement(element_id="e1", role="textbox", name="Email"),
        PageElement(element_id="e2", role="button", name="Log in"),
    )

    intent = resolve_page_command("Type HELLO into EMAIL", elements)

    assert intent == Intent(IntentType.TYPE_TEXT, target_id="e1", text="HELLO")


def test_type_allows_spaces_in_the_typed_text() -> None:
    """Multi-word typed text between ``type`` and ``into`` must be kept."""
    elements = (
        PageElement(element_id="e1", role="textbox", name="Email"),
        PageElement(element_id="e2", role="button", name="Log in"),
    )

    intent = resolve_page_command("type hello world into email", elements)

    assert intent == Intent(IntentType.TYPE_TEXT, target_id="e1", text="hello world")


def test_type_into_a_button_returns_none() -> None:
    """Type resolution must ignore buttons even when the name matches."""
    elements = (PageElement(element_id="e1", role="button", name="Log in"),)

    assert IntentType.TYPE_TEXT
    assert resolve_page_command("type hello into log in", elements) is None


def test_two_email_fields_are_ambiguous() -> None:
    """Two textboxes sharing a name must not pick one at random."""
    elements = (
        PageElement(element_id="e1", role="textbox", name="Email"),
        PageElement(element_id="e2", role="textbox", name="Email"),
    )

    assert IntentType.TYPE_TEXT
    assert resolve_page_command("type hello into email", elements) is None


def test_type_without_into_returns_none() -> None:
    """A type phrase missing ``into <field>`` is incomplete and returns None."""
    elements = (
        PageElement(element_id="e1", role="textbox", name="Email"),
        PageElement(element_id="e2", role="button", name="Log in"),
    )

    assert IntentType.TYPE_TEXT
    assert resolve_page_command("type hello", elements) is None
