"""Destructive page-click confirmation helpers."""

from __future__ import annotations

_CONFIRM_PHRASES = frozenset(
    {
        "confirm",
        "yes confirm",
        "go ahead",
        "do it",
        "yes do it",
        "proceed",
    }
)

_DESTRUCTIVE_TOKENS = frozenset(
    {
        "buy",
        "purchase",
        "checkout",
        "submit",
        "send",
        "delete",
        "pay",
        "order now",
        "place order",
        "unsubscribe",
    }
)


def is_confirm_phrase(text: str) -> bool:
    """Return whether ``text`` is a spoken confirmation."""
    collapsed = " ".join(text.split()).casefold().strip(".,!?")
    return collapsed in _CONFIRM_PHRASES


def is_destructive_phrase(text: str) -> bool:
    """Return whether a page phrase looks destructive / irreversible."""
    collapsed = " ".join(text.split()).casefold()
    if not collapsed:
        return False
    for token in _DESTRUCTIVE_TOKENS:
        if token in collapsed:
            return True
    return False
