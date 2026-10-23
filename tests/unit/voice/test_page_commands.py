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


def test_clicking_a_textbox_focuses_it_without_submitting() -> None:
    """A spoken click on a textbox should become a focus operation."""
    elements = (PageElement(element_id="e1", role="textbox", name="Email"),)

    assert resolve_page_command("click on email", elements) == Intent(
        IntentType.FOCUS_ELEMENT,
        target_id="e1",
    )


def test_indexed_log_in_button_can_be_clicked_by_name() -> None:
    """``index_html`` and ``resolve_page_command`` compose for a Log in button."""
    elements = index_html("""<button>Log in</button>""")

    intent = resolve_page_command("click on log in", elements)

    assert intent == Intent(IntentType.CLICK_ELEMENT, target_id="e1")


def test_type_into_input_uses_the_only_textbox() -> None:
    """``into input`` means the page's only text box, whatever its label is."""
    elements = (
        PageElement(element_id="e1", role="textbox", name="Message"),
        PageElement(element_id="e2", role="button", name="Send"),
    )

    intent = resolve_page_command("type what is your name into input", elements)

    assert intent == Intent(
        IntentType.TYPE_TEXT,
        target_id="e1",
        text="what is your name",
    )


def test_type_into_input_is_ambiguous_when_several_textboxes_exist() -> None:
    elements = (
        PageElement(element_id="e1", role="textbox", name="Email"),
        PageElement(element_id="e2", role="textbox", name="Password"),
    )

    assert resolve_page_command("type hello into input box", elements) is None


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


def test_click_the_only_link_and_an_ordinal_link() -> None:
    links = (
        PageElement(element_id="e1", role="link", name="Home"),
        PageElement(element_id="e2", role="link", name="Pricing"),
        PageElement(element_id="e3", role="button", name="Buy"),
    )
    assert resolve_page_command("click the second link", links) == Intent(
        IntentType.CLICK_ELEMENT, target_id="e2"
    )
    assert resolve_page_command("open link 1", links) == Intent(
        IntentType.CLICK_ELEMENT, target_id="e1"
    )
    assert resolve_page_command("click link", links) is None
    only = (PageElement(element_id="e9", role="link", name="Docs"),)
    assert resolve_page_command("click the link", only) == Intent(
        IntentType.CLICK_ELEMENT, target_id="e9"
    )
    assert resolve_page_command("click the pricing link", links) == Intent(
        IntentType.CLICK_ELEMENT, target_id="e2"
    )


def test_press_and_partial_button_name_resolve_uniquely() -> None:
    elements = (
        PageElement(element_id="e1", role="button", name="Add to Cart"),
        PageElement(element_id="e2", role="link", name="Cart"),
    )

    assert resolve_page_command("press add to cart button", elements) == Intent(
        IntentType.CLICK_ELEMENT, target_id="e1"
    )


def test_focus_search_matches_unique_search_textbox() -> None:
    elements = (
        PageElement(element_id="search", role="textbox", name="Search Amazon"),
        PageElement(element_id="email", role="textbox", name="Email"),
    )

    assert resolve_page_command("focus on search box", elements) == Intent(
        IntentType.FOCUS_ELEMENT, target_id="search"
    )


def test_focus_app_search_bar_matches_only_unique_page_search_textbox() -> None:
    elements = (
        PageElement(element_id="search", role="textbox", name="Search Amazon"),
        PageElement(element_id="email", role="textbox", name="Email"),
    )

    for phrase in ("focus app search bar", "focus page search field"):
        assert resolve_page_command(phrase, elements) == Intent(
            IntentType.FOCUS_ELEMENT,
            target_id="search",
        )


def test_focus_app_search_bar_never_guesses_between_multiple_search_textboxes() -> None:
    elements = (
        PageElement(element_id="products", role="textbox", name="Search products"),
        PageElement(element_id="orders", role="textbox", name="Search orders"),
    )

    assert resolve_page_command("focus app search bar", elements) is None


def test_search_for_item_submits_through_page_search() -> None:
    elements = (
        PageElement(element_id="search", role="textbox", name="Search Amazon"),
        PageElement(element_id="email", role="textbox", name="Email"),
    )

    assert resolve_page_command("search for noise cancelling headphones", elements) == Intent(
        IntentType.SUBMIT_TEXT,
        target_id="search",
        text="noise cancelling headphones",
    )


def test_enter_and_fill_vocabulary_type_into_named_fields() -> None:
    elements = (PageElement(element_id="email", role="textbox", name="Email address"),)

    assert resolve_page_command("enter user@example.com into email", elements) == Intent(
        IntentType.TYPE_TEXT,
        target_id="email",
        text="user@example.com",
    )
    assert resolve_page_command("fill email with user@example.com", elements) == Intent(
        IntentType.TYPE_TEXT,
        target_id="email",
        text="user@example.com",
    )


def test_ambiguous_partial_field_name_never_guesses() -> None:
    elements = (
        PageElement(element_id="one", role="textbox", name="Search products"),
        PageElement(element_id="two", role="textbox", name="Search orders"),
    )

    assert resolve_page_command("focus search", elements) is None
    assert resolve_page_command("search for keyboard", elements) is None


def test_incomplete_and_empty_phrases_never_crash() -> None:
    elements = (
        PageElement(element_id="e1", role="button", name="Submit"),
        PageElement(element_id="e2", role="textbox", name="Email"),
    )

    for phrase in (
        "",
        "   ",
        "click",
        "click on",
        "type into email",
        "type hello into",
        "fill with hello",
        "fill email with",
        "search",
        "search for",
        "look up",
        "mouse click",
        "left click",
        "answer is",
        "the answer is",
    ):
        assert resolve_page_command(phrase, elements) is None


def test_trailing_punctuation_still_matches_click_targets() -> None:
    elements = (PageElement(element_id="e1", role="button", name="Submit"),)

    assert resolve_page_command("click submit!!!", elements) == Intent(
        IntentType.CLICK_ELEMENT, target_id="e1"
    )


def test_typed_text_may_contain_the_word_into() -> None:
    elements = (PageElement(element_id="email", role="textbox", name="Email"),)

    assert resolve_page_command("type walk into town into email", elements) == Intent(
        IntentType.TYPE_TEXT,
        target_id="email",
        text="walk into town",
    )


def test_checkbox_is_clickable_by_name() -> None:
    elements = (PageElement(element_id="e3", role="checkbox", name="Remember me"),)

    assert resolve_page_command("click remember me", elements) == Intent(
        IntentType.CLICK_ELEMENT, target_id="e3"
    )


def _search_page() -> tuple[PageElement, ...]:
    """A results page: header links first, then ads, then organic results."""
    return (
        PageElement(element_id="n1", role="link", name="Skip to main content"),
        PageElement(element_id="n2", role="link", name="Images"),
        PageElement(element_id="r1", role="link", name="Python docs", result=True),
        PageElement(element_id="r2", role="link", name="Real Python", result=True),
        PageElement(element_id="r3", role="link", name="Wikipedia", result=True),
        PageElement(element_id="b1", role="button", name="Search"),
    )


def test_first_link_on_a_results_page_is_the_first_result_not_the_header() -> None:
    page = _search_page()
    for phrase in ("click first link", "click the first link", "open the first result"):
        assert resolve_page_command(phrase, page) == Intent(
            IntentType.CLICK_ELEMENT, target_id="r1"
        ), phrase
    assert resolve_page_command("click the third result", page) == Intent(
        IntentType.CLICK_ELEMENT, target_id="r3"
    )
    assert resolve_page_command("click the second link", page) == Intent(
        IntentType.CLICK_ELEMENT, target_id="r2"
    )
    assert resolve_page_command("click the fifth result", page) is None


def test_first_link_without_results_still_counts_every_link() -> None:
    page = tuple(
        PageElement(element_id=f"e{i}", role="link", name=f"Link {i}") for i in range(1, 4)
    )
    assert resolve_page_command("click first link", page) == Intent(
        IntentType.CLICK_ELEMENT, target_id="e1"
    )
    assert resolve_page_command("click the first result", page) is None
