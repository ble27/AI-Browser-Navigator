"""Map committed clauses to executable streaming voice steps."""

from __future__ import annotations

import inspect
from urllib.parse import urlparse

from gesture_control.actions import Intent, IntentType
from gesture_control.backends.base import LaunchableApp, PressableKey
from gesture_control.voice.commands import parse_command
from gesture_control.voice.desktop import (
    parse_app_command,
    parse_ask_command,
    parse_control_command,
    parse_key_command,
    parse_type_command,
)
from gesture_control.voice.stream_contracts import (
    CancelStep,
    Clause,
    PageStep,
    Readiness,
    ResolvedStep,
    Step,
    Surface,
)


def _host_from_url(url: str) -> str:
    host = urlparse(url).hostname
    if host is None:
        return ""
    return host.removeprefix("www.")


class DeterministicClausePlanner:
    """Expand one committed clause into ordered execution steps."""

    def __init__(self, initial_surface: Surface = Surface.BROWSER) -> None:
        """Create a planner with a starting surface assumption."""
        self._surface = initial_surface
        self._active_line_id: int | None = None
        self._line_host: str | None = None
        self._line_app: LaunchableApp | None = None

    @property
    def surface(self) -> Surface:
        """Return the planner's current browser vs. app surface."""
        return self._surface

    def plan(self, clause: Clause) -> list[Step]:
        """Expand one committed clause into zero or more steps."""
        self._sync_line(clause.line_id)
        if parse_control_command(clause.text):
            return [CancelStep(source=clause)]

        key_intent = parse_key_command(clause.text)
        if key_intent is not None:
            return [ResolvedStep(source=clause, intent=key_intent, ready=self._readiness())]

        app_intent = parse_app_command(clause.text)
        if app_intent is not None:
            ready = self._readiness()
            self._record_open_app(app_intent.app)
            return [
                ResolvedStep(source=clause, intent=app_intent, ready=ready),
            ]

        ask = parse_ask_command(clause.text)
        if ask is not None:
            open_intent = Intent(IntentType.OPEN_URL, url=ask.url)
            type_intent = Intent(IntentType.TYPE_FOCUSED, text=ask.query)
            enter_intent = Intent(IntentType.PRESS_KEY, key=PressableKey.ENTER)
            ready = Readiness(host=ask.host)
            open_ready = self._readiness()
            self._record_open_url(ask.url)
            return [
                ResolvedStep(source=clause, intent=open_intent, ready=open_ready),
                ResolvedStep(source=clause, intent=type_intent, ready=ready),
                ResolvedStep(source=clause, intent=enter_intent, ready=ready),
            ]

        command_intent = parse_command(clause.text)
        if command_intent is not None:
            ready = self._readiness()
            if command_intent.kind is IntentType.OPEN_URL and command_intent.url:
                self._record_open_url(command_intent.url)
            elif command_intent.kind is IntentType.SEARCH_WEB:
                self._surface = Surface.BROWSER
            return [
                ResolvedStep(source=clause, intent=command_intent, ready=ready),
            ]

        type_request = parse_type_command(clause.text)
        if type_request is not None:
            if type_request.has_target:
                return [
                    PageStep(
                        source=clause,
                        phrase=clause.text,
                        ready=self._readiness(),
                    ),
                ]
            if self._surface is Surface.APP:
                intent = Intent(IntentType.TYPE_FOCUSED, text=type_request.text)
                return [
                    ResolvedStep(source=clause, intent=intent, ready=self._readiness()),
                ]
            fallback = Intent(IntentType.TYPE_FOCUSED, text=type_request.text)
            return [
                PageStep(
                    source=clause,
                    phrase=clause.text,
                    fallback=fallback,
                    ready=self._readiness(),
                ),
            ]

        return [
            PageStep(
                source=clause,
                phrase=clause.text,
                ready=self._readiness(),
            ),
        ]

    def _sync_line(self, line_id: int) -> None:
        if self._active_line_id != line_id:
            self._active_line_id = line_id
            self._line_host = None
            self._line_app = None

    def _readiness(self) -> Readiness | None:
        if self._line_host is not None:
            return Readiness(host=self._line_host)
        if self._line_app is not None:
            return Readiness(app=self._line_app)
        return None

    def _record_open_url(self, url: str) -> None:
        self._surface = Surface.BROWSER
        self._line_host = _host_from_url(url)
        self._line_app = None

    def _record_open_app(self, app: LaunchableApp | None) -> None:
        if app is LaunchableApp.CHROME:
            self._surface = Surface.BROWSER
            self._line_host = None
            self._line_app = None
        else:
            self._surface = Surface.APP
            self._line_app = app
            self._line_host = None


DeterministicClausePlanner.__signature__ = inspect.Signature(
    [
        inspect.Parameter("self", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        inspect.Parameter(
            "initial_surface",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=Surface.BROWSER,
        ),
    ],
)
