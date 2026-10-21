"""Thread-safe status fan-out between the voice agent and the pill UI.

The agent, executor, and HTTP bridge run on different threads. They publish
small JSON-safe event dicts here; the bridge streams them to the browser UI
over Server-Sent Events. The hub also owns the user-facing on/off switch.
"""

from __future__ import annotations

import queue
import threading
from collections import deque
from typing import Any

from gesture_control.voice.stream_contracts import (
    PageStep,
    ResolvedStep,
    Step,
    StepReport,
)

Event = dict[str, Any]

# Slow or stalled browser tabs must never block the voice pipeline, so each
# subscriber gets a bounded queue and loses its oldest events when it lags.
_SUBSCRIBER_BUFFER = 256
_HISTORY = 20


class Subscription:
    """One consumer's bounded event queue."""

    def __init__(self) -> None:
        """Create an empty subscription."""
        self._queue: queue.Queue[Event | None] = queue.Queue(maxsize=_SUBSCRIBER_BUFFER)

    def push(self, event: Event | None) -> None:
        """Enqueue ``event``, dropping the oldest entry when the queue is full.

        Args:
            event: Event to deliver, or ``None`` to wake the consumer for shutdown.
        """
        while True:
            try:
                self._queue.put_nowait(event)
                return
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    continue

    def get(self, timeout_s: float) -> Event | None:
        """Wait for the next event.

        Args:
            timeout_s: Maximum seconds to wait.

        Returns:
            The next event, or ``None`` on timeout or hub shutdown.
        """
        try:
            return self._queue.get(timeout=timeout_s)
        except queue.Empty:
            return None


class StatusHub:
    """Publish/subscribe hub plus the pill's enabled flag."""

    def __init__(self, *, enabled: bool = True) -> None:
        """Create a hub.

        Args:
            enabled: Initial state of the user-facing on/off switch.
        """
        self._lock = threading.Lock()
        self._enabled = enabled
        self._closed = False
        self._subscribers: list[Subscription] = []
        self._history: deque[Event] = deque(maxlen=_HISTORY)

    @property
    def enabled(self) -> bool:
        """Whether the user currently wants the voice agent to act."""
        with self._lock:
            return self._enabled

    @property
    def closed(self) -> bool:
        """Whether :meth:`close` has been called."""
        with self._lock:
            return self._closed

    def set_enabled(self, enabled: bool) -> None:
        """Flip the on/off switch and tell every subscriber.

        Args:
            enabled: New desired state.
        """
        with self._lock:
            changed = self._enabled != enabled
            self._enabled = enabled
        if changed:
            self.publish({"type": "enabled", "enabled": enabled})

    def publish(self, event: Event) -> None:
        """Broadcast ``event`` to all subscribers and remember it.

        Args:
            event: JSON-serializable event dict with a ``type`` key.
        """
        with self._lock:
            if self._closed:
                return
            self._history.append(event)
            targets = list(self._subscribers)
        for target in targets:
            target.push(event)

    def snapshot(self) -> Event:
        """Return the current state for a freshly loaded UI.

        Returns:
            Dict with ``enabled`` and the most recent ``events``.
        """
        with self._lock:
            return {"enabled": self._enabled, "events": list(self._history)}

    def subscribe(self) -> Subscription:
        """Register a new consumer.

        Returns:
            A subscription that receives every later event.
        """
        subscription = Subscription()
        with self._lock:
            if self._closed:
                subscription.push(None)
            else:
                self._subscribers.append(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        """Remove a consumer. Safe to call twice.

        Args:
            subscription: Subscription returned by :meth:`subscribe`.
        """
        with self._lock:
            if subscription in self._subscribers:
                self._subscribers.remove(subscription)

    def close(self) -> None:
        """Stop publishing and wake every consumer so their streams end."""
        with self._lock:
            self._closed = True
            targets = list(self._subscribers)
            self._subscribers.clear()
        for target in targets:
            target.push(None)


def describe_step(step: Step) -> str:
    """Return a short human label for a step.

    Args:
        step: Planned step.

    Returns:
        Text such as ``click orders`` or ``scroll``.
    """
    if isinstance(step, PageStep):
        return step.phrase
    if isinstance(step, ResolvedStep):
        return str(step.intent.kind.value).replace("_", " ")
    return "cancel"


def report_event(report: StepReport) -> Event:
    """Convert an executor report into a UI event.

    Args:
        report: Outcome from the step executor.

    Returns:
        A ``step`` event dict.
    """
    return {
        "type": "step",
        "outcome": report.outcome.value,
        "label": describe_step(report.step),
        "detail": report.detail,
    }
