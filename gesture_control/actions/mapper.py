"""Translate modality-neutral intents into gated input-backend calls."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from gesture_control.backends.base import InputBackend


class IntentType(StrEnum):
    """Actions currently understood by the M2 Action Mapper."""

    MOVE_CURSOR = "move_cursor"
    CLICK_LEFT = "click_left"
    OPEN_URL = "open_url"
    CLICK_ELEMENT = "click_element"
    TYPE_TEXT = "type_text"


@dataclass(frozen=True, slots=True)
class Intent:
    """A modality-neutral user action.

    Attributes:
        kind: The action requested by a gesture or voice command.
        x: Target cursor horizontal coordinate, required for ``MOVE_CURSOR``.
        y: Target cursor vertical coordinate, required for ``MOVE_CURSOR``.
        url: HTTPS URL to open, required for ``OPEN_URL``.
        target_id: Indexed page element id (``e1``, ``e2``, ...), required for
            ``CLICK_ELEMENT`` and ``TYPE_TEXT``.
        text: Literal text to type into a field, required for ``TYPE_TEXT``.
    """

    kind: IntentType
    x: int | None = None
    y: int | None = None
    url: str | None = None
    target_id: str | None = None
    text: str | None = None


class ActionMapper:
    """Dispatch intents through the sole synthetic-input boundary."""

    def __init__(self, backend: InputBackend) -> None:
        """Create an action mapper for one OS input backend.

        Args:
            backend: The platform adapter that performs gated input injection.
        """
        self._backend = backend

    def dispatch(self, intent: Intent) -> None:
        """Execute an intent via the configured backend.

        Args:
            intent: The gesture or voice action to perform.

        Raises:
            ValueError: If a cursor movement intent omits a coordinate, an
                ``OPEN_URL`` intent omits ``url``, a ``CLICK_ELEMENT`` intent
                omits ``target_id``, or a ``TYPE_TEXT`` intent omits
                ``target_id`` or ``text``.
        """
        if intent.kind is IntentType.MOVE_CURSOR:
            if intent.x is None or intent.y is None:
                raise ValueError("MOVE_CURSOR intents require both x and y coordinates.")
            self._backend.move_to(intent.x, intent.y)
        elif intent.kind is IntentType.CLICK_LEFT:
            self._backend.click_left()
        elif intent.kind is IntentType.OPEN_URL:
            if intent.url is None:
                raise ValueError("OPEN_URL intents require a url.")
            self._backend.open_url(intent.url)
        elif intent.kind is IntentType.CLICK_ELEMENT:
            if not intent.target_id:
                raise ValueError("CLICK_ELEMENT intents require a target_id.")
            self._backend.click_element(intent.target_id)
        elif intent.kind is IntentType.TYPE_TEXT:
            if not intent.target_id or intent.text is None:
                raise ValueError("TYPE_TEXT intents require a target_id and text.")
            self._backend.type_text(intent.target_id, intent.text)
