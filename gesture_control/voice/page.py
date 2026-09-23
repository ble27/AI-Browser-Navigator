"""Index interactive HTML elements for offline voice page navigation.

Uses only the Python standard library ``html.parser`` — no BeautifulSoup,
lxml, browser automation, or network I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser

from gesture_control.actions import Intent, IntentType

_CLICKABLE_ROLES = frozenset({"button", "link"})


@dataclass(frozen=True, slots=True)
class PageElement:
    """An interactive element discovered in document order.

    Attributes:
        element_id: Stable id ``e1``, ``e2``, ... assigned only to emitted
            elements in document order.
        role: Accessibility role (``button``, ``link``, or ``textbox``).
        name: Accessible name used for speech matching.
    """

    element_id: str
    role: str
    name: str


def index_html(html: str) -> tuple[PageElement, ...]:
    """Index interactive elements from an HTML fragment.

    Emits buttons, links, and labeled inputs in document order. Non-interactive
    tags such as ``<p>`` are ignored. ``<script>`` bodies are skipped entirely
    and never executed.

    Args:
        html: HTML markup to index (fragment or full document).

    Returns:
        A tuple of ``PageElement`` values in document order.
    """
    parser = _PageIndexParser()
    parser.feed(html)
    parser.close()
    return tuple(parser.elements)


def resolve_page_command(transcript: str, elements: tuple[PageElement, ...]) -> Intent | None:
    """Resolve a spoken click command onto a uniquely named page element.

    Accepts case-insensitive transcripts of the form ``click`` + optional
    ``on`` + an accessible name. Only ``button`` and ``link`` roles are
    clickable; textboxes never match.

    Args:
        transcript: Raw voice transcript text to parse.
        elements: Indexed page elements to match against.

    Returns:
        An ``Intent`` with ``IntentType.CLICK_ELEMENT`` and ``target_id`` set
        when exactly one clickable element matches the spoken name; otherwise
        ``None``.
    """
    collapsed = " ".join(transcript.split())
    if not collapsed:
        return None

    tokens = collapsed.split()
    if tokens[0].casefold() != "click":
        return None

    rest = tokens[1:]
    if rest and rest[0].casefold() == "on":
        rest = rest[1:]
    if not rest:
        return None

    spoken_name = " ".join(rest).casefold()
    matches = [
        element
        for element in elements
        if element.role in _CLICKABLE_ROLES and element.name.casefold() == spoken_name
    ]
    # Ambiguous names return None: speech cannot choose which button to click.
    if len(matches) != 1:
        return None
    return Intent(IntentType.CLICK_ELEMENT, target_id=matches[0].element_id)


def _normalize_name(raw: str) -> str:
    """Collapse internal whitespace and strip ends for accessible names.

    Args:
        raw: Raw name text collected from attributes or element content.

    Returns:
        A single-spaced, stripped name, or ``""`` when nothing remains.
    """
    return " ".join(raw.split())


class _PageIndexParser(HTMLParser):
    """HTMLParser that collects button, link, and textbox page elements."""

    def __init__(self) -> None:
        # convert_charrefs=True so &#39; / &amp; become real characters in data.
        super().__init__(convert_charrefs=True)
        self.elements: list[PageElement] = []
        self._next_id = 1
        self._script_depth = 0
        # Stack of open interactive containers: (role, aria_label, text_parts).
        self._stack: list[tuple[str, str | None, list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Handle an opening tag, emitting void inputs immediately.

        Args:
            tag: Lowercased tag name.
            attrs: Attribute name/value pairs from the parser.
        """
        if self._script_depth > 0:
            if tag == "script":
                self._script_depth += 1
            return

        if tag == "script":
            self._script_depth = 1
            return

        attr_map = {name: (value or "") for name, value in attrs}
        aria_label = attr_map.get("aria-label")
        # Prefer aria-label: speech matches the accessible name, not the
        # visible fallback text, when an author-provided label is set.
        labeled = _normalize_name(aria_label) if aria_label is not None else None

        if tag == "input":
            # Void element: emit at the start tag; there is no end-tag text.
            name = labeled or ""
            if name:
                self._emit("textbox", name)
            return

        if tag == "button":
            self._stack.append(("button", labeled, []))
            return

        if tag == "a":
            self._stack.append(("link", labeled, []))
            return

    def handle_endtag(self, tag: str) -> None:
        """Close interactive containers or leave a script skip region.

        Args:
            tag: Lowercased tag name.
        """
        if tag == "script" and self._script_depth > 0:
            self._script_depth -= 1
            return

        if self._script_depth > 0:
            return

        if tag not in {"button", "a"} or not self._stack:
            return

        role, aria_name, text_parts = self._stack.pop()
        expected = "button" if tag == "button" else "link"
        if role != expected:
            # Mismatched close; put it back and ignore this end tag.
            self._stack.append((role, aria_name, text_parts))
            return

        if aria_name is not None:
            name = aria_name
        else:
            name = _normalize_name("".join(text_parts))
        if name:
            self._emit(role, name)

    def handle_data(self, data: str) -> None:
        """Accumulate text for the innermost open button or link.

        Args:
            data: Character data from the parser.
        """
        if self._script_depth > 0 or not self._stack:
            return
        self._stack[-1][2].append(data)

    def _emit(self, role: str, name: str) -> None:
        """Append a numbered ``PageElement`` and advance the id counter.

        Args:
            role: Accessibility role for the element.
            name: Non-empty accessible name.
        """
        element_id = f"e{self._next_id}"
        self._next_id += 1
        self.elements.append(PageElement(element_id=element_id, role=role, name=name))
