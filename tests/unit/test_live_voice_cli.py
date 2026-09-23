"""CLI contract tests for the continuous hardware-free voice session."""

from __future__ import annotations

from typing import Any

import pytest
from gesture_control import app


def test_voice_arguments_default_to_tiny_english_model() -> None:
    """Live voice should be opt-in and default to the lightweight English model."""
    args = app.build_arg_parser().parse_args([])

    assert args.voice is False
    assert args.voice_model == "tiny.en"


@pytest.mark.parametrize(
    "argv",
    [
        ["--voice", "--command", "reload"],
        ["--voice", "--debug"],
    ],
)
def test_voice_is_mutually_exclusive_with_one_shot_and_camera_modes(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Only one long-running or one-shot operating mode may be selected."""
    with pytest.raises(SystemExit, match="2"):
        app.main(argv)

    assert "not allowed with argument" in capsys.readouterr().err


def test_voice_is_macos_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Live voice should fail argument validation before touching audio off macOS."""
    monkeypatch.setattr(app.sys, "platform", "linux")

    with pytest.raises(SystemExit, match="2"):
        app.main(["--voice"])

    assert "macOS" in capsys.readouterr().err


@pytest.mark.parametrize("model_name", ["tiny.en", "small.en"])
def test_voice_cli_skips_camera_and_passes_selected_model(
    monkeypatch: pytest.MonkeyPatch,
    model_name: str,
) -> None:
    """The voice mode should invoke only the voice runner with its selected model."""
    received_models: list[str] = []

    def fake_run_voice_session(model_name: str = "tiny.en") -> int:
        received_models.append(model_name)
        return 0

    def fail_if_camera_starts(*args: object, **kwargs: object) -> int:
        raise AssertionError("run_debug_overlay must not start for --voice")

    monkeypatch.setattr(app, "run_voice_session", fake_run_voice_session)
    monkeypatch.setattr(app, "run_debug_overlay", fail_if_camera_starts)
    monkeypatch.setattr(app.sys, "platform", "darwin")
    argv = ["--voice"]
    if model_name != "tiny.en":
        argv.extend(["--voice-model", model_name])

    assert app.main(argv) == 0
    assert received_models == [model_name]


def test_safe_pause_hotkey_spans_session_and_interrupt_exits_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The hotkey must be active while the agent runs and close on Ctrl-C."""
    timeline: list[str] = []

    class _Backend:
        """Provide only the safety gate needed by the voice runtime."""

        safe_pause = object()

    class _Hotkey:
        """Record context-manager lifetime without registering a real hotkey."""

        def __init__(self, safe_pause: object, **kwargs: Any) -> None:
            assert safe_pause is _Backend.safe_pause
            del kwargs

        def __enter__(self) -> _Hotkey:
            timeline.append("hotkey-enter")
            return self

        def __exit__(self, *exc_info: object) -> None:
            timeline.append("hotkey-exit")

    class _Agent:
        """Interrupt from inside the session as a user pressing Ctrl-C would."""

        def __init__(
            self,
            recorder: object,
            transcriber: object,
            action_mapper: object,
            *,
            page_resolver: object,
            page_prefetch: object = None,
        ) -> None:
            assert recorder is not None
            assert transcriber is not None
            assert action_mapper is not None
            assert page_resolver is not None
            assert page_prefetch is not None

        def run_forever(self) -> None:
            timeline.append("agent-run")
            raise KeyboardInterrupt

    class _Transcriber:
        """Record model selection without loading faster-whisper."""

        def __init__(self, model_name: str = "tiny.en", **kwargs: Any) -> None:
            timeline.append(f"model:{model_name}")
            del kwargs

    class _Bridge:
        def __enter__(self) -> _Bridge:
            timeline.append("bridge-enter")
            return self

        def __exit__(self, *exc_info: object) -> None:
            timeline.append("bridge-exit")

    class _Resolver:
        def __init__(self, bridge: object) -> None:
            del bridge

        def resolve(self, transcript: str) -> None:
            del transcript

        def warm(self) -> None:
            return None

    monkeypatch.setattr(app, "MacOSInputBackend", lambda page_bridge: _Backend())
    monkeypatch.setattr(app, "SafePauseHotkey", _Hotkey)
    monkeypatch.setattr(app, "ActionMapper", lambda backend: object())
    monkeypatch.setattr("gesture_control.browser.bridge.ChromePageBridge", _Bridge)
    monkeypatch.setattr("gesture_control.voice.audio.MicrophoneUtteranceRecorder", object)
    monkeypatch.setattr("gesture_control.voice.live_page.LivePageCommandResolver", _Resolver)
    monkeypatch.setattr(
        "gesture_control.voice.transcription.FasterWhisperTranscriber", _Transcriber
    )
    monkeypatch.setattr("gesture_control.voice.agent.VoiceAgent", _Agent)

    assert app.run_voice_session(model_name="small.en") == 0
    assert timeline == [
        "bridge-enter",
        "model:small.en",
        "hotkey-enter",
        "agent-run",
        "hotkey-exit",
        "bridge-exit",
    ]
