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


@dataclass(frozen=True, slots=True)
class Intent:
    """A modality-neutral user action.

    Attributes:
        kind: The action requested by a gesture or voice command.
        x: Target cursor horizontal coordinate, required for ``MOVE_CURSOR``.
        y: Target cursor vertical coordinate, required for ``MOVE_CURSOR``.
        url: HTTPS URL to open, required for ``OPEN_URL``.
    """

    kind: IntentType
    x: int | None = None
    y: int | None = None
    url: str | None = None


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
            ValueError: If a cursor movement intent omits a coordinate, or an
                ``OPEN_URL`` intent omits ``url``.
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
