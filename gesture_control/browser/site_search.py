"""Best-effort on-page search against a live Chrome snapshot.

Used by the macOS backend so ``search for …`` prefers a unique site search
control (textbox or collapsed search button) before falling back to the
omnibox. No speech is evaluated as code; only opaque snapshot ids and literal
query text are sent to the bridge.
"""

from __future__ import annotations

import time
from typing import Protocol

from gesture_control.browser.bridge import BridgeError, PageElement, PageSnapshot

_SEARCH_REVEAL_PAUSE_S = 0.12


class SnapshotPageBridge(Protocol):
    """Page bridge surface required for site search."""

    def snapshot(self, timeout: float | None = None) -> PageSnapshot:
        """Return the active-tab interactive element index."""

    def click(self, target_id: str, timeout: float | None = None) -> None:
        """Activate an indexed element."""

    def type_and_submit(self, target_id: str, text: str, timeout: float | None = None) -> None:
        """Type and submit through an indexed textbox."""


def try_site_search(bridge: SnapshotPageBridge, query: str) -> bool:
    """Search through a unique page search control when one is available.

    Prefers a uniquely named search textbox. If none is visible but exactly one
    search-named button exists (apple.com-style collapsed search), clicks it,
    re-snapshots, and submits through the revealed field.

    Args:
        bridge: Connected Chrome page bridge.
        query: Literal search text. Never evaluated as code.

    Returns:
        ``True`` when the query was submitted on-page; ``False`` when the page
        has no usable unique search control (caller should use omnibox).
    """
    if not query.strip():
        return False
    try:
        snapshot = bridge.snapshot()
    except (BridgeError, RuntimeError, AttributeError):
        return False

    box = _unique_search_textbox(snapshot.elements)
    if box is not None:
        bridge.type_and_submit(box.element_id, query)
        return True

    button = _unique_search_button(snapshot.elements)
    if button is None:
        return False

    bridge.click(button.element_id)
    # Give the page a beat to mount the revealed combobox/input.
    time.sleep(_SEARCH_REVEAL_PAUSE_S)
    try:
        revealed = bridge.snapshot()
    except (BridgeError, RuntimeError, AttributeError):
        return False
    box = _unique_search_textbox(revealed.elements)
    if box is None:
        # Fall back: any newly unique textbox after opening search.
        textboxes = [element for element in revealed.elements if element.role == "textbox"]
        if len(textboxes) != 1:
            return False
        box = textboxes[0]
    bridge.type_and_submit(box.element_id, query)
    return True


def _unique_search_textbox(
    elements: tuple[PageElement, ...] | list[PageElement]
) -> PageElement | None:
    """Return the sole textbox whose accessible name mentions search."""
    matches = [
        element
        for element in elements
        if element.role == "textbox" and "search" in element.name.casefold()
    ]
    return matches[0] if len(matches) == 1 else None


def _unique_search_button(
    elements: tuple[PageElement, ...] | list[PageElement]
) -> PageElement | None:
    """Return the sole button/link whose accessible name mentions search."""
    matches = [
        element
        for element in elements
        if element.role in {"button", "link"} and "search" in element.name.casefold()
    ]
    return matches[0] if len(matches) == 1 else None
