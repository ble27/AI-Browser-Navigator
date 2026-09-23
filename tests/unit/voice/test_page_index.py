"""Tests for indexing interactive elements from an HTML string.

These tests specify ``index_html`` and ``PageElement`` only. They intentionally
stay red until ``gesture_control.voice.page`` exists — no Chrome, network, or
subprocess is involved.
"""

from __future__ import annotations

from gesture_control.voice.page import PageElement, index_html


def test_button_text_becomes_a_button_named_log_in() -> None:
    """A button's inner text becomes its accessible name."""
    html = """<button>Log in</button>"""

    elements = index_html(html)

    assert elements == (PageElement(element_id="e1", role="button", name="Log in"),)


def test_link_text_becomes_a_link() -> None:
    """An anchor's link text becomes a link named by that text."""
    html = """<a href="/home">Home</a>"""

    elements = index_html(html)

    assert elements == (PageElement(element_id="e1", role="link", name="Home"),)


def test_input_uses_aria_label_as_its_name() -> None:
    """An input with ``aria-label`` is a textbox named by that label."""
    html = """<input type="email" aria-label="Email">"""

    elements = index_html(html)

    assert elements == (PageElement(element_id="e1", role="textbox", name="Email"),)


def test_elements_are_numbered_in_document_order() -> None:
    """Multiple interactive elements get sequential ids in document order."""
    html = """<button>Log in</button><a href="/home">Home</a>"""

    elements = index_html(html)

    assert elements == (
        PageElement(element_id="e1", role="button", name="Log in"),
        PageElement(element_id="e2", role="link", name="Home"),
    )


def test_script_and_noninteractive_text_are_ignored() -> None:
    """Non-interactive markup and script content must not appear in the index."""
    html = """<p>Welcome</p><script>alert(1)</script><button>Log in</button>"""

    elements = index_html(html)

    assert elements == (PageElement(element_id="e1", role="button", name="Log in"),)


def test_button_aria_label_wins_over_inner_text() -> None:
    """``aria-label`` on a button overrides its inner text for the name."""
    html = """<button aria-label="Log in">Go</button>"""

    elements = index_html(html)

    assert elements == (PageElement(element_id="e1", role="button", name="Log in"),)
