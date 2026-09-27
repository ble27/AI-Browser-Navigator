"""Tests for confirm / destructive phrase helpers."""

from __future__ import annotations

from gesture_control.voice.confirm import is_confirm_phrase, is_destructive_phrase


def test_confirm_phrases() -> None:
    assert is_confirm_phrase("confirm")
    assert is_confirm_phrase("Go ahead.")
    assert not is_confirm_phrase("open reddit")


def test_destructive_phrases() -> None:
    assert is_destructive_phrase("click buy now")
    assert is_destructive_phrase("press submit")
    assert is_destructive_phrase("click checkout")
    assert not is_destructive_phrase("click orders")
