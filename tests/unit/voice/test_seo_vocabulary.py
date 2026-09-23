"""Tests for SEO attribute naming and everyday click vocabulary."""

from __future__ import annotations

from gesture_control.actions import Intent, IntentType
from gesture_control.browser.bridge import PageSeoMeta, _parse_seo_meta, _parse_snapshot
from gesture_control.voice.page import PageElement, index_html, resolve_page_command


def test_index_html_uses_data_label_and_itemprop() -> None:
    elements = index_html(
        '<button data-label="Add to Bag">Add</button>'
        '<button itemprop="checkout">Go</button>'
        '<input data-name="Promo code" type="text">'
    )

    names = {element.name for element in elements}
    assert "Add to Bag" in names
    assert "checkout" in names
    assert "Promo code" in names


def test_everyday_click_verbs_map_to_click_intent() -> None:
    elements = (
        PageElement("e1", "button", "Submit"),
        PageElement("e2", "link", "Home"),
    )

    for phrase in (
        "hit submit",
        "pick the submit",
        "push submit",
        "open submit",
        "mouse click on submit",
        "left click submit",
    ):
        assert resolve_page_command(phrase, elements) == Intent(
            IntentType.CLICK_ELEMENT, target_id="e1"
        )


def test_write_into_field_types_text() -> None:
    elements = (PageElement("email", "textbox", "Email"),)

    assert resolve_page_command("fill email with hello", elements) == Intent(
        IntentType.TYPE_TEXT, target_id="email", text="hello"
    )


def test_parse_snapshot_accepts_seo_block_and_loopback_http() -> None:
    snapshot = _parse_snapshot(
        {
            "url": "http://127.0.0.1:8765/seo_fixture.html",
            "title": "SEO Bridge Fixture",
            "seo": {
                "description": "Demo page",
                "site_name": "AI Gestures Demo",
                "og_title": "SEO Bridge Fixture",
                "keywords": ["buy now", "mac mini"],
                "canonical_url": "http://127.0.0.1:8765/seo_fixture.html",
            },
            "elements": [{"id": "e1", "role": "button", "name": "Add to Bag"}],
        }
    )

    assert snapshot.seo == PageSeoMeta(
        description="Demo page",
        site_name="AI Gestures Demo",
        og_title="SEO Bridge Fixture",
        keywords=("buy now", "mac mini"),
        canonical_url="http://127.0.0.1:8765/seo_fixture.html",
    )
    assert snapshot.elements[0].name == "Add to Bag"


def test_parse_seo_meta_defaults_when_absent() -> None:
    assert _parse_seo_meta(None) == PageSeoMeta()
