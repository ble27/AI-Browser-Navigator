"""Glue between the streaming voice session and the pill UI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from gesture_control.voice.status_hub import StatusHub, report_event
from gesture_control.voice.stream_contracts import StepReport

# <repo>/gesture_control/voice/pill_wiring.py -> <repo>/ui/dist
_DEFAULT_DIST = Path(__file__).resolve().parents[2] / "ui" / "dist"


def default_pill_dir(dist: Path = _DEFAULT_DIST) -> Path | None:
    """Locate the built pill UI.

    Args:
        dist: Directory expected to hold the Vite build.

    Returns:
        ``dist`` when it contains ``index.html``, else ``None`` (the session
        then falls back to the plain control page).
    """
    return dist if (dist / "index.html").is_file() else None


def mirror_output(hub: StatusHub, sink: Callable[[str], None] = print) -> Callable[[str], None]:
    """Wrap an output sink so each line is also published to the UI.

    Args:
        hub: Status hub to publish to.
        sink: Original destination for agent lines.

    Returns:
        A function suitable for ``StreamingVoiceAgent(output=...)``.
    """

    def emit(line: str) -> None:
        sink(line)
        hub.publish({"type": "log", "line": line})

    return emit


def mirror_reports(
    hub: StatusHub,
    sink: Callable[[StepReport], None],
) -> Callable[[StepReport], None]:
    """Wrap an executor report sink so each outcome is also published to the UI.

    Args:
        hub: Status hub to publish to.
        sink: Original handler (for example console printing).

    Returns:
        A function suitable for ``QueuedStepExecutor(report=...)``.
    """

    def emit(report: StepReport) -> None:
        sink(report)
        hub.publish(report_event(report))

    return emit
