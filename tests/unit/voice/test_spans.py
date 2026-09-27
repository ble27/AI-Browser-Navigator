"""Tests for verbatim type/ask/search span extraction."""

from __future__ import annotations

from gesture_control.voice.spans import (
    extract_ask_span,
    extract_search_span,
    extract_type_span,
)


def test_type_span_comma_and_in_app() -> None:
    span = extract_type_span("Type, I love you")
    assert span is not None
    assert span.text == "I love you"
    assert span.has_target is False

    span = extract_type_span("type I love you in notes")
    assert span is not None
    assert span.text == "I love you"


def test_type_span_into_input_keeps_the_generic_target() -> None:
    span = extract_type_span("type what is your name into input")
    assert span is not None
    assert span.text == "what is your name"
    assert span.has_target is True
    assert span.target == "input"


def test_type_span_into_target() -> None:
    span = extract_type_span("type hello into email")
    assert span is not None
    assert span.text == "hello"
    assert span.has_target is True
    assert span.target == "email"


def test_type_span_fill_with() -> None:
    span = extract_type_span("fill email with hello")
    assert span is not None
    assert span.text == "hello"
    assert span.has_target is True


def test_ask_span_with_and_without_query() -> None:
    span = extract_ask_span("ask claude what is the capital of france")
    assert span is not None
    assert span.assistant == "claude"
    assert "capital of france" in span.query

    bare = extract_ask_span("Asked Chatgpt")
    assert bare is not None
    assert bare.assistant == "chatgpt"
    assert bare.query == ""


def test_search_span_period_after_google() -> None:
    span = extract_search_span("Search Google. what is the capital, France")
    assert span is not None
    assert "capital" in span.query.casefold()
    assert "france" in span.query.casefold()
