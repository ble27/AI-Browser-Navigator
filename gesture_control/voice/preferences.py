"""User preferences for scroll size, dictation timing, and pill display."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from gesture_control.voice.policy import FREE_TEXT_SILENCE_S, TYPE_COMMAND_SILENCE_S
from gesture_control.voice.scroll import DEFAULT_SCROLL_PAGES, LARGE_SCROLL_PAGES

SCROLL_CHOICES = {"small": 1, "medium": DEFAULT_SCROLL_PAGES, "large": LARGE_SCROLL_PAGES}
TYPING_CHOICES = {"fast": TYPE_COMMAND_SILENCE_S, "steady": FREE_TEXT_SILENCE_S}
TEXT_SIZES = frozenset({"default", "large"})


@dataclass(frozen=True, slots=True)
class VoicePreferences:
    """Pill settings the streaming session reads while it plans commands.

    Attributes:
        scroll: Plain scroll distance: ``small``, ``medium``, or ``large``.
        typing: Dictation commit speed: ``fast`` or ``steady``.
        text_size: Pill text size: ``default`` or ``large``.
        high_contrast: When True, the pill avoids gray status text.
    """

    scroll: str = "medium"
    typing: str = "fast"
    text_size: str = "default"
    high_contrast: bool = False

    def scroll_pages(self) -> int:
        """Return the page count a plain scroll command should use."""
        return SCROLL_CHOICES[self.scroll]

    def type_silence_s(self) -> float:
        """Return how long dictation waits after the words stop changing."""
        return TYPING_CHOICES[self.typing]

    def to_dict(self) -> dict[str, object]:
        """Return the JSON shape the pill reads and writes."""
        return {
            "scroll": self.scroll,
            "typing": self.typing,
            "textSize": self.text_size,
            "highContrast": self.high_contrast,
        }


def merge_preferences(
    current: VoicePreferences,
    payload: object,
) -> VoicePreferences | None:
    """Apply a partial settings object onto ``current``.

    Args:
        current: Settings already in effect.
        payload: JSON object. Missing keys keep their current value.

    Returns:
        The merged settings, or ``None`` when a provided value is not allowed.
    """
    if not isinstance(payload, Mapping):
        return None
    values: dict[str, Any] = current.to_dict()
    for key, value in payload.items():
        if key not in values:
            return None
        values[key] = value
    scroll = values["scroll"]
    typing = values["typing"]
    text_size = values["textSize"]
    contrast = values["highContrast"]
    if scroll not in SCROLL_CHOICES or typing not in TYPING_CHOICES:
        return None
    if text_size not in TEXT_SIZES or not isinstance(contrast, bool):
        return None
    return VoicePreferences(
        scroll=str(scroll),
        typing=str(typing),
        text_size=str(text_size),
        high_contrast=contrast,
    )
