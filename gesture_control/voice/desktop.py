"""Desktop voice parsers for apps, keys, typing, and assistant macros."""

from __future__ import annotations

from gesture_control.actions import Intent, IntentType
from gesture_control.backends.base import LaunchableApp, PressableKey
from gesture_control.voice.browser import parse_browser_command
from gesture_control.voice.spans import extract_ask_span, extract_type_span
from gesture_control.voice.stream_contracts import AskRequest, TypeRequest

_CONTROL_PHRASES = frozenset({"cancel", "stop", "never mind"})

_KEY_PHRASES: dict[str, PressableKey] = {
    "press enter": PressableKey.ENTER,
    "hit enter": PressableKey.ENTER,
    "press tab": PressableKey.TAB,
    "hit tab": PressableKey.TAB,
    "press escape": PressableKey.ESCAPE,
    "hit escape": PressableKey.ESCAPE,
    "press backspace": PressableKey.BACKSPACE,
    "delete that": PressableKey.BACKSPACE,
    "new note": PressableKey.NEW_ITEM,
    "new document": PressableKey.NEW_ITEM,
    "select all": PressableKey.SELECT_ALL,
}

_APP_ALIASES: dict[str, LaunchableApp] = {
    "notes": LaunchableApp.NOTES,
    "textedit": LaunchableApp.TEXTEDIT,
    "calendar": LaunchableApp.CALENDAR,
    "reminders": LaunchableApp.REMINDERS,
    "mail": LaunchableApp.MAIL,
    "messages": LaunchableApp.MESSAGES,
    "safari": LaunchableApp.SAFARI,
    "chrome": LaunchableApp.CHROME,
    "finder": LaunchableApp.FINDER,
    "terminal": LaunchableApp.TERMINAL,
    "settings": LaunchableApp.SETTINGS,
    "system settings": LaunchableApp.SETTINGS,
    "music": LaunchableApp.MUSIC,
    "maps": LaunchableApp.MAPS,
    "photos": LaunchableApp.PHOTOS,
    "slack": LaunchableApp.SLACK,
    "spotify": LaunchableApp.SPOTIFY,
    "visual studio code": LaunchableApp.VSCODE,
    "vscode": LaunchableApp.VSCODE,
    "cursor": LaunchableApp.CURSOR,
    "discord": LaunchableApp.DISCORD,
    "zoom": LaunchableApp.ZOOM,
}

_ASSISTANTS: dict[str, tuple[str, str]] = {
    "claude": ("https://claude.ai/new", "claude.ai"),
    "chatgpt": ("https://chatgpt.com", "chatgpt.com"),
    "openai": ("https://chatgpt.com", "chatgpt.com"),
    "perplexity": ("https://www.perplexity.ai", "perplexity.ai"),
    "gemini": ("https://gemini.google.com/app", "gemini.google.com"),
}

_APP_PREFIXES = ("open ", "opened ", "launch ")


def parse_control_command(text: str) -> bool:
    """Return whether ``text`` is a streaming cancel phrase."""
    collapsed = " ".join(text.split()).casefold().strip(".,!?")
    return collapsed in _CONTROL_PHRASES


def parse_key_command(text: str) -> Intent | None:
    """Parse a desktop key phrase into ``PRESS_KEY``."""
    collapsed = " ".join(text.split()).casefold().strip(".,!?")
    key = _KEY_PHRASES.get(collapsed)
    if key is None:
        return None
    return Intent(IntentType.PRESS_KEY, key=key)


def parse_app_command(text: str) -> Intent | None:
    """Parse ``open`` / ``launch`` app phrases when the phrase names an app."""
    collapsed = " ".join(text.split())
    folded = collapsed.casefold()
    for prefix in _APP_PREFIXES:
        if not folded.startswith(prefix):
            continue
        remainder = collapsed[len(prefix) :].strip()
        if remainder.casefold().startswith("the "):
            remainder = remainder[4:].strip()
        tokens = remainder.rstrip(".,!?").split()
        if not tokens:
            return None
        if tokens[-1].casefold() == "app":
            tokens = tokens[:-1]
        if not tokens:
            return None
        alias = " ".join(tokens).casefold()
        app = _APP_ALIASES.get(alias)
        if app is None:
            return None
        # Prefer the present-tense form so browser-site checks stay consistent.
        present = "open " + " ".join(tokens)
        if " app" not in folded and parse_browser_command(present) is not None:
            return None
        return Intent(IntentType.OPEN_APP, app=app)
    return None


def parse_type_command(text: str) -> TypeRequest | None:
    """Parse type/write phrases into literal typing requests."""
    span = extract_type_span(text)
    if span is None:
        return None
    return TypeRequest(text=span.text, has_target=span.has_target)


def parse_ask_command(text: str) -> AskRequest | None:
    """Parse assistant ask/query macros.

    Bare ``ask claude`` (no query) still opens the assistant; the planner skips
    type/enter when ``query`` is empty.
    """
    span = extract_ask_span(text)
    if span is None:
        return None
    target = _ASSISTANTS.get(span.assistant)
    if target is None:
        return None
    url, host = target
    return AskRequest(url=url, host=host, query=span.query)
