"""Verbatim span extraction for type / ask / search voice payloads.

Code owns the string spans (jev-style): parsers pick a span from the
transcript instead of relying on a single brittle regex alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_TYPE_PREFIXES = ("type", "write")
_ASK_PREFIXES = ("ask", "asked", "query")
_SEARCH_PREFIXES = (
    "search google for",
    "search google",
    "search for",
    "look up",
    "lookup",
    "google",
)

_INTO = re.compile(r"^(?P<body>.+?)\s+into\s+(?P<target>.+)$", re.IGNORECASE)
_FILL = re.compile(r"^fill\s+(?P<target>.+?)\s+with\s+(?P<body>.+)$", re.IGNORECASE)
_IN_APP = re.compile(r"\s+in\s+(?P<app>[a-z0-9 ]+)$", re.IGNORECASE)
_FIND_ONLINE = re.compile(r"^find\s+(?P<body>.+)\s+online$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class TypeSpan:
    """Literal text to type, optionally aimed at a named control."""

    text: str
    has_target: bool
    target: str | None = None


@dataclass(frozen=True, slots=True)
class AskSpan:
    """Assistant name plus optional query payload."""

    assistant: str
    query: str


@dataclass(frozen=True, slots=True)
class SearchSpan:
    """Web-search query payload."""

    query: str


def _collapse(text: str) -> str:
    return " ".join(text.replace("\u00a0", " ").split())


def _strip_payload(text: str) -> str:
    # Keep ``!`` inside typed/search payloads (e.g. ``exact phrase!``).
    return text.strip(" \t.,?;:")


def extract_type_span(text: str) -> TypeSpan | None:
    """Extract a type/write/fill span from ``text``.

    Args:
        text: One clause or transcript line.

    Returns:
        A :class:`TypeSpan` when a type verb is present, else ``None``.
    """
    collapsed = _collapse(text)
    if not collapsed:
        return None
    fill = _FILL.match(collapsed)
    if fill is not None:
        body = _strip_payload(fill.group("body"))
        target = _strip_payload(fill.group("target"))
        if body and target:
            return TypeSpan(text=body, has_target=True, target=target)
        return None

    folded = collapsed.casefold()
    for prefix in _TYPE_PREFIXES:
        # Allow "type," / "type:" / "type " after the verb.
        if not folded.startswith(prefix):
            continue
        rest = collapsed[len(prefix) :]
        if rest[:1] not in {"", " ", ",", ":"}:
            continue
        rest = rest.lstrip(" ,:")
        if not rest:
            return None
        into = _INTO.match(rest)
        if into is not None:
            body = _strip_payload(into.group("body"))
            target = _strip_payload(into.group("target"))
            if body and target:
                return TypeSpan(text=body, has_target=True, target=target)
            return None
        # Drop trailing "in <app>" — surface routing is the planner's job.
        body = _IN_APP.sub("", rest)
        body = _strip_payload(body)
        return TypeSpan(text=body, has_target=False) if body else None
    return None


def extract_ask_span(text: str) -> AskSpan | None:
    """Extract an ask/query assistant span from ``text``.

    Args:
        text: One clause or transcript line.

    Returns:
        An :class:`AskSpan` when an ask verb + assistant token is present.
    """
    collapsed = _collapse(text)
    if not collapsed:
        return None
    folded = collapsed.casefold()
    for prefix in _ASK_PREFIXES:
        token = prefix + " "
        if not folded.startswith(token):
            continue
        rest = collapsed[len(token) :].strip()
        if not rest:
            return None
        parts = rest.split(None, 1)
        assistant = parts[0].casefold().strip(".,!?")
        query = _strip_payload(parts[1]) if len(parts) > 1 else ""
        if not assistant:
            return None
        return AskSpan(assistant=assistant, query=query)
    return None


def extract_search_span(text: str) -> SearchSpan | None:
    """Extract a web-search query span from ``text``.

    Args:
        text: One clause or transcript line.

    Returns:
        A :class:`SearchSpan` when a search prefix matches, else ``None``.
    """
    collapsed = _collapse(text)
    if not collapsed:
        return None
    # Streaming STT often inserts a period after "Search Google".
    if collapsed.casefold().startswith("search google."):
        collapsed = "search google " + collapsed[len("search google.") :].lstrip()
    folded = collapsed.casefold()
    for prefix in _SEARCH_PREFIXES:
        token = prefix + " "
        if folded.startswith(token):
            query = _strip_payload(collapsed[len(token) :])
            return SearchSpan(query=query) if query else None
        if folded == prefix:
            return None
    online = _FIND_ONLINE.match(collapsed)
    if online is not None:
        query = _strip_payload(online.group("body"))
        return SearchSpan(query=query) if query else None
    return None
