"""Tests for SEO attribute naming and everyday click vocabulary."""

from __future__ import annotations

from gesture_control.actions import Intent, IntentType
from gesture_control.browser.bridge import PageSeoMeta, _parse_seo_meta, _parse_snapshot
from gesture_control.voice.page import PageElement, _seo_attr_name, index_html, resolve_page_command


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


def test_index_html_uses_nested_image_alt_for_icon_only_controls() -> None:
    elements = index_html(
        '<button><img alt="Buy now"></button>'
        '<a href="/home"><img alt="Home logo"></a>'
        '<input type="image" alt="Search submit">'
    )

    names = {element.name for element in elements}
    assert names == {"Buy now", "Home logo", "Search submit"}


def test_seo_attr_name_splits_camel_case_like_the_extension() -> None:
    assert _seo_attr_name({"itemprop": "addToCart"}) == "add To Cart"
    assert _seo_attr_name({"itemprop": "URL"}) == "URL"
    # Extension only splits a→A, so leading acronyms stay glued to the next capital.
    assert _seo_attr_name({"itemprop": "XMLHttpRequest"}) == "XMLHttp Request"


def test_index_html_caps_extremely_long_data_labels() -> None:
    elements = index_html(f'<button data-label="{"x" * 2000}">Go</button>')

    assert len(elements) == 1
    assert len(elements[0].name) == 500


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
