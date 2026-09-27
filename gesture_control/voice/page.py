"""Index interactive HTML elements for offline voice page navigation.

Uses only the Python standard library ``html.parser`` — no BeautifulSoup,
lxml, browser automation, or network I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

from gesture_control.actions import Intent, IntentType
from gesture_control.voice.spans import is_generic_input_target

_CLICKABLE_ROLES = frozenset({"button", "link", "checkbox"})
_TYPEABLE_ROLES = frozenset({"textbox"})
# Everyday mouse-replacement verbs humans say instead of "click".
_CLICK_VERBS = frozenset(
    {
        "click",
        "press",
        "tap",
        "choose",
        "activate",
        "hit",
        "pick",
        "push",
        "open",
    }
)
_FOCUS_VERBS = frozenset({"focus", "select", "highlight"})
_FIELD_SUFFIXES = frozenset({"box", "field", "textbox", "button", "link"})
_SUBMIT_NAME_TOKENS = frozenset({"submit", "submit answer", "submit answers", "check answer"})
_ANSWER_FIELD_TOKENS = frozenset({"answer", "answers", "response", "responses"})
_CLICK_PREFIX_SKIP = frozenset({"on", "the", "a", "an"})
# Match chrome_extension content_script humanizeIdentifier: only split a→A.
_CAMEL_BOUNDARY = re.compile(r"([a-z])([A-Z])")
# Keep speakable names bounded even when pages dump huge data-label values.
_MAX_ELEMENT_NAME_CHARS = 500
_ORDINALS = {
    "first": 1,
    "1st": 1,
    "second": 2,
    "2nd": 2,
    "third": 3,
    "3rd": 3,
    "fourth": 4,
    "4th": 4,
    "fifth": 5,
    "5th": 5,
    "sixth": 6,
    "6th": 6,
    "seventh": 7,
    "7th": 7,
    "eighth": 8,
    "8th": 8,
    "ninth": 9,
    "9th": 9,
    "tenth": 10,
    "10th": 10,
}


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
    """Resolve a spoken page command onto a uniquely named element.

    Supports ``click`` [``on``] ``<name>`` for buttons/links, and
    ``type <text> into <field>`` for textboxes. Matching is case-insensitive
    on element names; typed text casing is preserved.

    Args:
        transcript: Raw voice transcript text to parse.
        elements: Indexed page elements to match against.

    Returns:
        A ``CLICK_ELEMENT`` or ``TYPE_TEXT`` intent when exactly one eligible
        element matches; otherwise ``None``.
    """
    collapsed = " ".join(transcript.split())
    if not collapsed:
        return None

    tokens = collapsed.split()
    folded = [token.casefold().strip(".,!?") for token in tokens]
    verb = folded[0]

    homework = _resolve_homework(folded, tokens, elements)
    if homework is not None:
        return homework

    # Multi-word mouse phrases: "mouse click on …", "left click …".
    if folded[:2] == ["mouse", "click"] or folded[:2] == ["left", "click"]:
        return _resolve_click(tokens[2:], elements)
    if verb in _CLICK_VERBS:
        return _resolve_click(tokens[1:], elements)
    if verb in _FOCUS_VERBS:
        return _resolve_focus(tokens[1:], elements)
    if verb == "type":
        return _resolve_type(tokens[1:], elements)
    if verb == "enter":
        return _resolve_enter(tokens[1:], elements)
    if verb in {"fill", "put", "write"}:
        return _resolve_fill(tokens[1:], elements)
    if verb in {"search", "lookup"} or (verb == "look" and len(tokens) > 1):
        return _resolve_search(tokens, elements)
    return None


def _resolve_homework(
    folded: list[str],
    tokens: list[str],
    elements: tuple[PageElement, ...],
) -> Intent | None:
    """Resolve WebAssign-style answer/submit phrases.

    Args:
        folded: Casefolded speech tokens.
        tokens: Original tokens (preserves answer text casing).
        elements: Indexed page elements.

    Returns:
        A page intent when the homework grammar matches, else ``None``.
    """
    if not folded:
        return None

    if folded[0] == "submit" or folded[:2] == ["check", "answer"]:
        return _resolve_submit_action(folded, elements)

    # "the answer is 42" / "answer is 42" / "answer with 42"
    start = 1 if folded[:1] == ["the"] else 0
    if start < len(folded) and folded[start] in {"answer", "answers", "response"}:
        rest = folded[start + 1 :]
        original_rest = tokens[start + 1 :]
        if rest and rest[0] in {"is", "with", "as"}:
            text = " ".join(original_rest[1:]).strip()
            if text:
                return _answer_text_intent(text, elements, ordinal=None)
            # "answer is" / "answer with" without a value is incomplete.
            return None
        # Bare "answer 42" types into the unique answer field when possible.
        if rest:
            text = " ".join(original_rest).strip()
            if text:
                return _answer_text_intent(text, elements, ordinal=None)

    return None


def _resolve_submit_action(folded: list[str], elements: tuple[PageElement, ...]) -> Intent | None:
    """Resolve ``submit`` / ``submit answer`` onto a unique submit control."""
    spoken = " ".join(folded)
    if spoken in {"submit", "submit answer", "submit answers", "check answer"}:
        matches = _submit_buttons(elements)
        if len(matches) == 1:
            return Intent(IntentType.CLICK_ELEMENT, target_id=matches[0].element_id)
        # Fall through to normal click matching for "submit something else".
    if folded[0] == "submit" and len(folded) > 1:
        return _resolve_click(list(folded[1:]), elements)
    return None


def _submit_buttons(elements: tuple[PageElement, ...]) -> list[PageElement]:
    """Return clickable controls whose names look like submit actions."""
    matches: list[PageElement] = []
    for element in elements:
        if element.role not in _CLICKABLE_ROLES:
            continue
        name = _normalize_spoken_name(element.name)
        if name in _SUBMIT_NAME_TOKENS or name.startswith("submit"):
            matches.append(element)
    return matches


def _answer_text_intent(
    text: str,
    elements: tuple[PageElement, ...],
    *,
    ordinal: int | None,
) -> Intent | None:
    """Type into the unique answer field, or the only textbox on the page."""
    answer_fields = [
        element
        for element in elements
        if element.role in _TYPEABLE_ROLES and _is_answer_field(element.name)
    ]
    if not answer_fields:
        textboxes = [element for element in elements if element.role in _TYPEABLE_ROLES]
        if len(textboxes) == 1:
            answer_fields = textboxes
        else:
            return None
    chosen = _pick_by_ordinal(answer_fields, ordinal)
    if chosen is None:
        return None
    return Intent(IntentType.TYPE_TEXT, target_id=chosen.element_id, text=text)


def _pick_by_ordinal(matches: list[PageElement], ordinal: int | None) -> PageElement | None:
    """Pick one match by 1-based ordinal, or the sole match when unspecified."""
    if ordinal is None:
        return matches[0] if len(matches) == 1 else None
    if 1 <= ordinal <= len(matches):
        return matches[ordinal - 1]
    return None


def _resolve_click(rest: list[str], elements: tuple[PageElement, ...]) -> Intent | None:
    """Resolve ``click`` [``on``] ``<name>`` against clickable elements.

    Args:
        rest: Tokens after the leading ``click`` verb.
        elements: Indexed page elements to match against.

    Returns:
        A ``CLICK_ELEMENT`` intent for a unique button/link match, else
        ``None``.
    """
    while rest and rest[0].casefold().strip(".,!?") in _CLICK_PREFIX_SKIP:
        rest = rest[1:]
    if not rest:
        return None

    spoken_name = " ".join(rest).casefold()
    matches = _matching_elements(spoken_name, elements, _CLICKABLE_ROLES)
    if len(matches) == 0:
        # Saying "click the search box" means focus that textbox, not submit it.
        textboxes = _matching_elements(spoken_name, elements, _TYPEABLE_ROLES)
        if len(textboxes) == 1:
            return Intent(IntentType.FOCUS_ELEMENT, target_id=textboxes[0].element_id)
    # Ambiguous names return None: speech cannot choose which button to click.
    if len(matches) != 1:
        return None
    return Intent(IntentType.CLICK_ELEMENT, target_id=matches[0].element_id)


def _resolve_type(rest: list[str], elements: tuple[PageElement, ...]) -> Intent | None:
    """Resolve ``type <text> into <field>`` against textbox elements.

    Args:
        rest: Tokens after the leading ``type`` verb.
        elements: Indexed page elements to match against.

    Returns:
        A ``TYPE_TEXT`` intent for a unique textbox match, else ``None``.
    """
    into_indices = [i for i, token in enumerate(rest) if token.casefold() == "into"]
    if not into_indices:
        return None

    # Use the last "into" so typed text may itself contain the word "into".
    into_idx = into_indices[-1]
    typed_tokens = rest[:into_idx]
    field_tokens = rest[into_idx + 1 :]
    typed_text = " ".join(typed_tokens)
    field_name = " ".join(field_tokens)
    if not typed_text or not field_name:
        return None

    field_folded = field_name.casefold()
    if is_generic_input_target(field_folded):
        textboxes = [element for element in elements if element.role in _TYPEABLE_ROLES]
        if len(textboxes) == 1:
            return Intent(
                IntentType.TYPE_TEXT,
                target_id=textboxes[0].element_id,
                text=typed_text,
            )
        return None
    matches = _matching_elements(field_folded, elements, _TYPEABLE_ROLES)
    # Ambiguous names return None: speech cannot choose which field to type into.
    if len(matches) != 1:
        return None
    return Intent(
        IntentType.TYPE_TEXT,
        target_id=matches[0].element_id,
        text=typed_text,
    )


def _resolve_focus(rest: list[str], elements: tuple[PageElement, ...]) -> Intent | None:
    """Resolve focus/select phrases onto one textbox."""
    while rest and rest[0].casefold() in {"on", "the"}:
        rest = rest[1:]
    if not rest:
        return None
    matches = _matching_elements(" ".join(rest), elements, _TYPEABLE_ROLES)
    if len(matches) != 1:
        return None
    return Intent(IntentType.FOCUS_ELEMENT, target_id=matches[0].element_id)


def _resolve_enter(rest: list[str], elements: tuple[PageElement, ...]) -> Intent | None:
    """Resolve ``enter <text> in/into <field>``."""
    return _resolve_text_separator(rest, elements, separators={"in", "into"})


def _resolve_fill(rest: list[str], elements: tuple[PageElement, ...]) -> Intent | None:
    """Resolve ``fill/put <field> with <text>``."""
    separator_indices = [i for i, token in enumerate(rest) if token.casefold() == "with"]
    if not separator_indices:
        return None
    separator = separator_indices[-1]
    field_name = " ".join(rest[:separator])
    text = " ".join(rest[separator + 1 :])
    return _text_intent_for_field(field_name, text, elements, submit=False)


def _resolve_text_separator(
    rest: list[str],
    elements: tuple[PageElement, ...],
    separators: set[str],
) -> Intent | None:
    """Resolve text before a separator and a field name after it."""
    indices = [i for i, token in enumerate(rest) if token.casefold() in separators]
    if not indices:
        return None
    separator = indices[-1]
    return _text_intent_for_field(
        " ".join(rest[separator + 1 :]),
        " ".join(rest[:separator]),
        elements,
        submit=False,
    )


def _resolve_search(tokens: list[str], elements: tuple[PageElement, ...]) -> Intent | None:
    """Resolve a search phrase through the active page's unique search box."""
    folded = [token.casefold().strip(".,!?") for token in tokens]
    if folded[:2] == ["look", "up"]:
        query_tokens = tokens[2:]
    elif folded[0] == "lookup":
        query_tokens = tokens[1:]
    elif folded[0] == "search":
        query_tokens = tokens[2:] if len(folded) > 1 and folded[1] == "for" else tokens[1:]
    else:
        return None
    query = " ".join(query_tokens).strip()
    if not query:
        return None
    search_boxes = tuple(
        element
        for element in elements
        if element.role in _TYPEABLE_ROLES and "search" in _normalize_name(element.name).casefold()
    )
    if len(search_boxes) != 1:
        return None
    return Intent(IntentType.SUBMIT_TEXT, target_id=search_boxes[0].element_id, text=query)


def _text_intent_for_field(
    field_name: str,
    text: str,
    elements: tuple[PageElement, ...],
    *,
    submit: bool,
) -> Intent | None:
    """Build a type/submit intent for one uniquely matched field."""
    if not field_name.strip() or not text.strip():
        return None
    if is_generic_input_target(field_name):
        textboxes = [element for element in elements if element.role in _TYPEABLE_ROLES]
        if len(textboxes) != 1:
            return None
        kind = IntentType.SUBMIT_TEXT if submit else IntentType.TYPE_TEXT
        return Intent(kind, target_id=textboxes[0].element_id, text=text.strip())
    matches = _matching_elements(field_name, elements, _TYPEABLE_ROLES)
    if len(matches) != 1:
        return None
    kind = IntentType.SUBMIT_TEXT if submit else IntentType.TYPE_TEXT
    return Intent(kind, target_id=matches[0].element_id, text=text.strip())


def _matching_elements(
    spoken_name: str,
    elements: tuple[PageElement, ...],
    roles: frozenset[str],
) -> list[PageElement]:
    """Return exact, numbered, or unique partial accessible-name matches."""
    base, ordinal = _split_ordinal(spoken_name)
    if not base:
        return []
    eligible = [element for element in elements if element.role in roles]
    exact = [element for element in eligible if _normalize_spoken_name(element.name) == base]
    pool = exact
    if not pool:
        partial = [element for element in eligible if base in _normalize_spoken_name(element.name)]
        pool = partial
    if ordinal is not None:
        chosen = _pick_by_ordinal(pool, ordinal)
        return [chosen] if chosen is not None else []
    return pool if len(pool) == 1 else []


def _is_answer_field(name: str) -> bool:
    """Return True when an accessible name looks like a homework answer box."""
    tokens = set(_normalize_spoken_name(name).split())
    return bool(tokens & _ANSWER_FIELD_TOKENS)


def _split_ordinal(spoken_name: str) -> tuple[str, int | None]:
    """Split ``second answer`` / ``answer 2`` into a base name and ordinal."""
    tokens = _normalize_spoken_name(spoken_name).split()
    if not tokens:
        return "", None
    if tokens[0] in _ORDINALS:
        return " ".join(tokens[1:]), _ORDINALS[tokens[0]]
    if tokens[-1].isdigit():
        return " ".join(tokens[:-1]), int(tokens[-1])
    if tokens[-1] in _ORDINALS:
        return " ".join(tokens[:-1]), _ORDINALS[tokens[-1]]
    return " ".join(tokens), None


def _normalize_spoken_name(raw: str) -> str:
    """Normalize speech and remove optional control-role suffixes."""
    tokens = _normalize_name(raw).casefold().strip(".,!?").split()
    while tokens and tokens[0] in {"on", "the"}:
        tokens = tokens[1:]
    if tokens and tokens[-1] in _FIELD_SUFFIXES:
        tokens = tokens[:-1]
    return " ".join(tokens)


def _normalize_name(raw: str) -> str:
    """Collapse internal whitespace and strip ends for accessible names.

    Args:
        raw: Raw name text collected from attributes or element content.

    Returns:
        A single-spaced, stripped name, or ``""`` when nothing remains.
    """
    return " ".join(raw.split())


def _seo_attr_name(attr_map: dict[str, str]) -> str:
    """Return a speakable name from common SEO / analytics attributes."""
    for key in ("data-label", "data-name", "data-seo", "data-analytics-name", "itemprop"):
        value = attr_map.get(key)
        if not value:
            continue
        humanized = value.replace("_", " ").replace("-", " ")
        # Match the extension: split camelCase only at a→A, keep acronyms intact.
        spaced = _CAMEL_BOUNDARY.sub(r"\1 \2", humanized)
        name = _normalize_name(spaced)
        if name:
            return name[:_MAX_ELEMENT_NAME_CHARS]
    return ""


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

        if tag == "img" and self._stack:
            # Icon-only buttons/links often expose speakable text only via alt.
            alt = _normalize_name(attr_map.get("alt", ""))
            if alt:
                self._stack[-1][2].append(alt)
            return

        if tag == "input":
            input_type = (attr_map.get("type") or "text").casefold()
            if input_type in {"button", "submit", "reset", "image"}:
                name = (
                    labeled
                    or _normalize_name(attr_map.get("value", ""))
                    or _normalize_name(attr_map.get("alt", ""))
                    or _seo_attr_name(attr_map)
                    or _normalize_name(attr_map.get("name", ""))
                )
                if name:
                    self._emit("button", name)
                return
            if input_type in {"hidden", "radio", "file"}:
                return
            if input_type == "checkbox":
                name = (
                    labeled
                    or _seo_attr_name(attr_map)
                    or _normalize_name(attr_map.get("name", ""))
                    or _normalize_name(attr_map.get("id", ""))
                )
                if name:
                    self._emit("checkbox", name)
                return
            # Void text-like input: emit at the start tag; there is no end-tag text.
            name = (
                labeled
                or _normalize_name(attr_map.get("placeholder", ""))
                or _seo_attr_name(attr_map)
                or _normalize_name(attr_map.get("name", "").replace("_", " "))
                or _normalize_name(attr_map.get("id", "").replace("_", " ").replace("-", " "))
            )
            if name:
                self._emit("textbox", name)
            return

        if tag == "textarea":
            name = (
                labeled
                or _normalize_name(attr_map.get("placeholder", ""))
                or _seo_attr_name(attr_map)
                or _normalize_name(attr_map.get("name", "").replace("_", " "))
                or _normalize_name(attr_map.get("id", "").replace("_", " ").replace("-", " "))
            )
            # Textarea may have body text; name comes from attributes only.
            if name:
                self._emit("textbox", name)
            return

        if tag == "button":
            self._stack.append(("button", labeled or _seo_attr_name(attr_map) or None, []))
            return

        if tag == "a":
            self._stack.append(("link", labeled or _seo_attr_name(attr_map) or None, []))
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
        trimmed = name[:_MAX_ELEMENT_NAME_CHARS]
        element_id = f"e{self._next_id}"
        self._next_id += 1
        self.elements.append(PageElement(element_id=element_id, role=role, name=trimmed))
