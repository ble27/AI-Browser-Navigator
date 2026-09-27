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
from gesture_control.voice.spans import extract_type_span, is_generic_input_target
from gesture_control.voice.stream_contracts import (
    CancelStep,
    Clause,
    PageStep,
    Readiness,
    ResolvedStep,
    Step,
    Surface,
)

_BROWSER_WIDE_INTENTS = frozenset(
    {
        IntentType.SEARCH_WEB,
        IntentType.SCROLL,
        IntentType.NEXT_TAB,
        IntentType.PREVIOUS_TAB,
        IntentType.NEW_TAB,
        IntentType.CLOSE_TAB,
        IntentType.GO_BACK,
        IntentType.GO_FORWARD,
        IntentType.RELOAD_PAGE,
        IntentType.REOPEN_TAB,
    }
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
        # Session-level fallback so "open amazon" then a later "click orders"
        # still waits on the amazon host (multi-utterance flows).
        self._session_host: str | None = None
        self._session_app: LaunchableApp | None = None

    @property
    def surface(self) -> Surface:
        """Return the planner's current browser vs. app surface."""
        return self._surface

    @property
    def recent_host(self) -> str | None:
        """Most recent browser host from this session (line or prior)."""
        return self._line_host or self._session_host

    @property
    def recent_app(self) -> LaunchableApp | None:
        """Most recent app focus target from this session (line or prior)."""
        return self._line_app or self._session_app

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
            # An open action must never wait on the destination it creates.
            ready = None
            self._record_open_app(app_intent.app)
            return [
                ResolvedStep(source=clause, intent=app_intent, ready=ready),
            ]

        ask = parse_ask_command(clause.text)
        if ask is not None:
            open_intent = Intent(IntentType.OPEN_URL, url=ask.url)
            open_ready = None
            self._record_open_url(ask.url)
            steps: list[Step] = [
                ResolvedStep(source=clause, intent=open_intent, ready=open_ready),
            ]
            if ask.query:
                ready = Readiness(host=ask.host)
                steps.append(
                    ResolvedStep(
                        source=clause,
                        intent=Intent(IntentType.TYPE_FOCUSED, text=ask.query),
                        ready=ready,
                    ),
                )
                steps.append(
                    ResolvedStep(
                        source=clause,
                        intent=Intent(IntentType.PRESS_KEY, key=PressableKey.ENTER),
                        ready=ready,
                    ),
                )
            return steps

        command_intent = parse_command(clause.text)
        if command_intent is not None:
            if command_intent.kind is IntentType.OPEN_URL and command_intent.url:
                ready = None
                self._record_open_url(command_intent.url)
            elif command_intent.kind in _BROWSER_WIDE_INTENTS:
                self._surface = Surface.BROWSER
                # Browser-wide controls must not depend on the current host.
                ready = None
            else:
                ready = self._readiness()
            return [
                ResolvedStep(source=clause, intent=command_intent, ready=ready),
            ]

        type_request = parse_type_command(clause.text)
        if type_request is not None:
            focused = Intent(IntentType.TYPE_FOCUSED, text=type_request.text)
            span = extract_type_span(clause.text)
            generic_input = (
                type_request.has_target
                and span is not None
                and span.target is not None
                and is_generic_input_target(span.target)
            )
            if type_request.has_target and not generic_input:
                return [
                    PageStep(
                        source=clause,
                        phrase=clause.text,
                        ready=self._readiness(),
                    ),
                ]
            if self._surface is Surface.APP and not generic_input:
                return [
                    ResolvedStep(source=clause, intent=focused, ready=self._readiness()),
                ]
            # Browser typing must not wait on the last opened host. A missing
            # page URL was cancelling "type … into input" before any keystrokes.
            return [
                PageStep(
                    source=clause,
                    phrase=clause.text,
                    fallback=focused,
                    ready=None,
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

    def _readiness(self, *, allow_session: bool = True) -> Readiness | None:
        if self._line_host is not None:
            return Readiness(host=self._line_host)
        if self._line_app is not None:
            return Readiness(app=self._line_app)
        if not allow_session:
            return None
        if self._session_host is not None:
            return Readiness(host=self._session_host)
        if self._session_app is not None:
            return Readiness(app=self._session_app)
        return None

    def _record_open_url(self, url: str) -> None:
        self._surface = Surface.BROWSER
        self._line_host = _host_from_url(url)
        self._line_app = None
        self._session_host = self._line_host
        self._session_app = None

    def _record_open_app(self, app: LaunchableApp | None) -> None:
        if app is LaunchableApp.CHROME:
            self._surface = Surface.BROWSER
            self._line_host = None
            self._line_app = None
            self._session_app = None
        else:
            self._surface = Surface.APP
            self._line_app = app
            self._line_host = None
            self._session_app = app
            self._session_host = None


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
