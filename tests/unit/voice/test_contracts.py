"""Pin frozen streaming voice contracts (Phase 1 source of truth)."""

from __future__ import annotations

import importlib
import inspect
from dataclasses import fields

import pytest
from gesture_control.actions.mapper import Intent, IntentType
from gesture_control.backends.base import LaunchableApp, PressableKey
from gesture_control.voice import asr_repair
from gesture_control.voice.stream_contracts import (
    DEFAULT_READY_WAIT_S,
    MAX_TYPED_CHARS,
    READY_POLL_INTERVAL_S,
    STABLE_PARTIALS_TO_COMMIT,
    AskRequest,
    CancelStep,
    Clause,
    PageStep,
    Readiness,
    ResolvedStep,
    StepOutcome,
    StepReport,
    Surface,
    TranscriptEvent,
    TypeRequest,
)


def test_transcript_event_fields() -> None:
    names = {field.name for field in fields(TranscriptEvent)}
    assert names == {"kind", "text", "line_id", "at_s"}


def test_clause_fields() -> None:
    names = {field.name for field in fields(Clause)}
    assert names == {"text", "line_id", "index", "final"}


def test_readiness_defaults() -> None:
    ready = Readiness()
    assert ready.host is None
    assert ready.app is None
    assert ready.max_wait_s == DEFAULT_READY_WAIT_S


def test_streaming_timing_constants() -> None:
    assert STABLE_PARTIALS_TO_COMMIT == 2
    assert DEFAULT_READY_WAIT_S == 6.0
    assert READY_POLL_INTERVAL_S == 0.25
    assert MAX_TYPED_CHARS == 500


def test_step_outcome_values() -> None:
    assert {member.value for member in StepOutcome} == {
        "done",
        "skipped_paused",
        "failed",
        "cancelled",
    }


def test_surface_values() -> None:
    assert Surface.BROWSER.value == "browser"
    assert Surface.APP.value == "app"


def test_desktop_request_types() -> None:
    type_fields = {field.name for field in fields(TypeRequest)}
    ask_fields = {field.name for field in fields(AskRequest)}
    assert type_fields == {"text", "has_target"}
    assert ask_fields == {"url", "host", "query"}


def test_intent_type_desktop_values() -> None:
    assert IntentType.OPEN_APP.value == "open_app"
    assert IntentType.TYPE_FOCUSED.value == "type_focused"
    assert IntentType.PRESS_KEY.value == "press_key"


def test_intent_has_app_and_key_fields() -> None:
    names = {field.name for field in fields(Intent)}
    assert "app" in names
    assert "key" in names


def test_launchable_app_members() -> None:
    assert LaunchableApp.NOTES.value == "Notes"
    assert LaunchableApp.CHROME.value == "Google Chrome"
    assert LaunchableApp.CURSOR.value == "Cursor"
    assert len(LaunchableApp) == 20


def test_pressable_key_members() -> None:
    assert PressableKey.ENTER.value == "enter"
    assert PressableKey.NEW_ITEM.value == "cmd+n"
    assert len(PressableKey) == 6


def test_repair_command_text_signature() -> None:
    sig = inspect.signature(asr_repair.repair_command_text)
    assert list(sig.parameters) == ["text"]
    assert sig.return_annotation in (str, "str")


def test_input_backend_desktop_method_signatures() -> None:
    from gesture_control.backends.base import InputBackend

    assert "open_app" in InputBackend.__dict__
    assert "type_focused" in InputBackend.__dict__
    assert "press_key" in InputBackend.__dict__
    open_sig = inspect.signature(InputBackend.open_app)
    assert list(open_sig.parameters) == ["self", "app"]
    type_sig = inspect.signature(InputBackend.type_focused)
    assert list(type_sig.parameters) == ["self", "text"]
    key_sig = inspect.signature(InputBackend.press_key)
    assert list(key_sig.parameters) == ["self", "key"]


def test_desktop_parser_signatures() -> None:
    desktop = importlib.import_module("gesture_control.voice.desktop")
    for name in (
        "parse_control_command",
        "parse_key_command",
        "parse_app_command",
        "parse_type_command",
        "parse_ask_command",
    ):
        func = getattr(desktop, name)
        assert callable(func)


def test_moonshine_transcriber_constructor() -> None:
    module = importlib.import_module("gesture_control.voice.moonshine_stt")
    cls = module.MoonshineStreamingTranscriber
    sig = inspect.signature(cls)
    params = list(sig.parameters)
    assert params == ["self", "model_arch", "update_interval_s"]
    assert sig.parameters["model_arch"].default == "small_streaming"
    assert sig.parameters["update_interval_s"].default == 0.3


def test_clause_segmenter_constructor() -> None:
    module = importlib.import_module("gesture_control.voice.segmenter")
    sig = inspect.signature(module.DeterministicClauseSegmenter)
    assert list(sig.parameters) == ["self"]


def test_clause_planner_constructor() -> None:
    module = importlib.import_module("gesture_control.voice.planner")
    sig = inspect.signature(module.DeterministicClausePlanner)
    params = list(sig.parameters)
    assert params == ["self", "initial_surface"]
    assert sig.parameters["initial_surface"].default is Surface.BROWSER


def test_queued_step_executor_constructor() -> None:
    module = importlib.import_module("gesture_control.voice.executor")
    cls = module.QueuedStepExecutor
    sig = inspect.signature(cls)
    param_names = list(sig.parameters)
    assert param_names == [
        "self",
        "mapper",
        "page",
        "focus",
        "safe_pause",
        "report",
        "sleep",
        "clock",
    ]


def test_streaming_voice_agent_constructor() -> None:
    module = importlib.import_module("gesture_control.voice.streaming_agent")
    sig = inspect.signature(module.StreamingVoiceAgent)
    assert list(sig.parameters) == [
        "self",
        "transcriber",
        "segmenter",
        "planner",
        "executor",
        "output",
    ]


def test_step_dataclass_field_types_use_intent() -> None:
    assert ResolvedStep.__annotations__["intent"] == "Intent"
    assert "Readiness" in PageStep.__annotations__["ready"]
    assert CancelStep.__annotations__["source"] == "Clause"
    assert StepReport.__annotations__["step"] == "Step"
