"""Tests for resolving spoken click commands onto indexed page elements.

These tests specify ``resolve_page_command`` only. They intentionally stay red
until ``CLICK_ELEMENT``, ``Intent.target_id``, and the resolver exist. No
Chrome, extension, or network is involved.
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
