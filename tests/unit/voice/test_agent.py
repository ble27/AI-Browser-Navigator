"""Tests for the hardware-free voice command runtime."""

from __future__ import annotations

import numpy as np
import pytest
from gesture_control.actions import ActionMapper
from gesture_control.backends.base import BrowserAction, InputBackend
from gesture_control.voice.agent import VoiceAgent
from numpy.typing import NDArray


class _Recorder:
    def __init__(self) -> None:
        self.audio = np.zeros(1600, dtype=np.float32)

    def record_utterance(self) -> NDArray[np.float32]:
        return self.audio


class _Transcriber:
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript
        self.calls: list[tuple[NDArray[np.float32], int]] = []

    def transcribe(self, audio: NDArray[np.float32], sample_rate: int = 16_000) -> str:
        self.calls.append((audio, sample_rate))
        return self.transcript


class _Backend(InputBackend):
    def __init__(self) -> None:
        super().__init__()
        self.browser_actions: list[BrowserAction] = []

    def screen_size(self) -> tuple[int, int]:
        return 100, 100

    def move_to(self, x: int, y: int) -> None:
        del x, y

    def click_left(self) -> None:
        return None

    def open_url(self, url: str) -> None:
        del url

    def navigate_browser(self, action: BrowserAction) -> None:
        self.browser_actions.append(action)

    def search_web(self, text: str) -> None:
        del text

    def scroll(self, amount: int) -> None:
        del amount

    def click_element(self, target_id: str) -> None:
        del target_id

    def type_text(self, target_id: str, text: str) -> None:
        del target_id, text


def test_voice_agent_dispatches_recognized_transcript() -> None:
    recorder = _Recorder()
    transcriber = _Transcriber("next tab")
    backend = _Backend()
    output: list[str] = []
    agent = VoiceAgent(recorder, transcriber, ActionMapper(backend), output.append)

    assert agent.run_once() is True
    assert transcriber.calls == [(recorder.audio, 16_000)]
    assert backend.browser_actions == [BrowserAction.NEXT_TAB]
    assert output == ["Heard: next tab", "Recognized: next_tab"]


def test_voice_agent_does_not_dispatch_unknown_transcript() -> None:
    backend = _Backend()
    output: list[str] = []
    agent = VoiceAgent(
        _Recorder(),
        _Transcriber("unknown words"),
        ActionMapper(backend),
        output.append,
    )

    assert agent.run_once() is False
    assert backend.browser_actions == []
    assert output[-1] == "Unrecognized command."


def test_voice_agent_ignores_empty_transcript() -> None:
    backend = _Backend()
    output: list[str] = []
    agent = VoiceAgent(
        _Recorder(),
        _Transcriber("   "),
        ActionMapper(backend),
        output.append,
    )

    assert agent.run_once() is False
    assert backend.browser_actions == []
    assert output == []


def test_voice_loop_handles_multiple_utterances_before_interrupt() -> None:
    class _SequenceRecorder:
        def __init__(self) -> None:
            self.calls = 0

        def record_utterance(self) -> NDArray[np.float32]:
            if self.calls == 2:
                raise KeyboardInterrupt
            self.calls += 1
            return np.zeros(1600, dtype=np.float32)

    class _SequenceTranscriber:
        def __init__(self) -> None:
            self._transcripts = iter(("new tab", "reload"))

        def transcribe(self, audio: NDArray[np.float32], sample_rate: int = 16_000) -> str:
            del audio, sample_rate
            return next(self._transcripts)

    recorder = _SequenceRecorder()
    backend = _Backend()
    agent = VoiceAgent(
        recorder,
        _SequenceTranscriber(),
        ActionMapper(backend),
        lambda _message: None,
    )

    with pytest.raises(KeyboardInterrupt):
        agent.run_forever()

    assert recorder.calls == 2
    assert backend.browser_actions == [BrowserAction.NEW_TAB, BrowserAction.RELOAD_PAGE]
