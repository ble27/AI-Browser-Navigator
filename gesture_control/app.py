"""Command-line entrypoint for the gesture control application.

Milestone status: macOS supports opt-in cursor control, deterministic Chrome
commands, and an explicitly started local microphone voice loop.
"""

from __future__ import annotations

import argparse
import sys
import time
from contextlib import ExitStack

import cv2

from gesture_control import __version__
from gesture_control.actions import ActionMapper, Intent, IntentType
from gesture_control.backends.macos import MacOSInputBackend, SafePauseHotkey
from gesture_control.gestures.cursor import (
    CursorMapper,
    CursorPointSource,
    HandPresenceHold,
    PointerGestureRecognizer,
)
from gesture_control.vision.camera import Camera, CameraUnavailableError
from gesture_control.vision.geometry import HandObservation
from gesture_control.vision.hand_landmarker import HandLandmarkerService
from gesture_control.vision.overlay import draw_hand_landmarks
from gesture_control.voice.commands import parse_command

_DEBUG_WINDOW_TITLE = "gesture-control debug (press 'q' to quit)"
_QUIT_KEY = ord("q")
# Palm detection cost grows with the frame area. 320x240 is enough for
# normalized landmarks and keeps the control loop closer to camera rate.
_CONTROL_CAPTURE_WIDTH = 320
_CONTROL_CAPTURE_HEIGHT = 240
# Below the default 0.5 so a brief confidence dip keeps tracking instead of
# falling back to a full-frame search, which is the frame where the cursor
# freezes.
_CONTROL_MIN_PRESENCE_CONFIDENCE = 0.3
_CONTROL_MIN_TRACKING_CONFIDENCE = 0.3
# The debug window is for the operator. Drawing and presenting it on every
# inference frame stalls the pointer behind the hand.
_CONTROL_PREVIEW_INTERVAL_S = 1.0 / 20.0


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the top-level command-line argument parser.

    Returns:
        A configured :class:`argparse.ArgumentParser` for the application.
    """
    parser = argparse.ArgumentParser(
        prog="gesture-control",
        description="Control your computer with hand gestures and voice.",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--debug",
        action="store_true",
        help="Show a debug window with the camera feed and hand landmark overlay.",
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=0,
        help="OS camera device index to open (default: 0, the default webcam).",
    )
    parser.add_argument(
        "--control",
        action="store_true",
        help=(
            "Enable macOS cursor movement and pinch-click input. Requires --debug; "
            "press Ctrl+Option+Command+P at any time to pause or resume input."
        ),
    )
    parser.add_argument(
        "--cursor-point",
        choices=[source.value for source in CursorPointSource],
        default=CursorPointSource.INDEX_TIP.value,
        help=(
            "Landmark set that drives the cursor when --control is on "
            "(default: index_tip). The pointer follows the index fingertip; "
            "use index_mcp or palm if pinch-click tip flex moves the target."
        ),
    )
    parser.add_argument(
        "--edge-margin",
        type=float,
        default=None,
        help=(
            "Normalized camera inset mapped onto the full screen when --control "
            "is on (default: CursorMapper's built-in margin). Raise to need less "
            "arm travel; lower if the pointer overshoots near edges."
        ),
    )
    modes.add_argument(
        "--command",
        type=str,
        default=None,
        help=(
            "Run one deterministic voice-style phrase for Google Chrome, such as "
            '"open cursor webpage", "next tab", or "reload". macOS only; skips '
            "the camera debug overlay."
        ),
    )
    modes.add_argument(
        "--voice",
        action="store_true",
        help=(
            "Continuously listen for local deterministic Chrome commands through "
            "the default microphone. macOS only; press Ctrl+C to stop."
        ),
    )
    modes.add_argument(
        "--dump-page",
        action="store_true",
        help=(
            "Print speakable control names from the active Chrome tab via the "
            "page bridge, then exit. macOS only; useful for WebAssign/apple.com "
            "phrase discovery."
        ),
    )
    parser.add_argument(
        "--voice-model",
        default="tiny.en",
        help=("faster-whisper model id or local directory used by --voice " "(default: tiny.en)."),
    )
    parser.add_argument(
        "--voice-mode",
        choices=("utterance", "streaming"),
        default="utterance",
        help=(
            "Continuous microphone pipeline: batch utterance (default) or "
            "streaming agent (Chrome Web Speech by default)."
        ),
    )
    parser.add_argument(
        "--voice-stt",
        choices=("web_speech", "small_streaming", "medium_streaming", "mlx_turbo"),
        default="web_speech",
        help=(
            "Streaming STT backend: Chrome Web Speech (default), Moonshine "
            "small/medium, or Apple Silicon MLX Whisper large-v3-turbo."
        ),
    )
    parser.add_argument(
        "--voice-redecode",
        action="store_true",
        help=(
            "On each FINAL line (Moonshine only), re-transcribe buffered audio "
            "with MLX Whisper large-v3-turbo."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def run_debug_overlay(
    camera_index: int = 0,
    control: bool = False,
    cursor_point: CursorPointSource = CursorPointSource.INDEX_TIP,
    edge_margin: float | None = None,
) -> int:
    """Run a live debug window showing the camera feed with hand-landmark overlays.

    Opens the requested camera and the MediaPipe HandLandmarker model (which
    triggers a one-time download on first run; see
    :func:`gesture_control.vision.model_download.ensure_hand_landmarker_model`),
    then loops: read a frame, detect hands, draw the overlay, display it.
    Press 'q' in the debug window to exit.

    Args:
        camera_index: OS camera device index to open.
        control: Whether to enable M2 cursor movement and pinch clicking.
        cursor_point: Landmark set used as the cursor anchor under ``--control``.
        edge_margin: Optional override for the camera-to-screen inset.

    Returns:
        A process exit code (``0`` on a clean exit, ``1`` if the camera
        could not be used).
    """
    try:
        with ExitStack() as stack:
            camera = stack.enter_context(
                Camera(
                    device_index=camera_index,
                    width=_CONTROL_CAPTURE_WIDTH if control else None,
                    height=_CONTROL_CAPTURE_HEIGHT if control else None,
                    drop_stale_frames=control,
                    stabilize_exposure=control,
                )
            )
            landmarker = stack.enter_context(
                HandLandmarkerService(
                    num_hands=1 if control else 2,
                    min_presence_confidence=(_CONTROL_MIN_PRESENCE_CONFIDENCE if control else 0.5),
                    min_tracking_confidence=(_CONTROL_MIN_TRACKING_CONFIDENCE if control else 0.5),
                )
            )
            action_mapper: ActionMapper | None = None
            cursor_mapper: CursorMapper | None = None
            pointer_recognizer: PointerGestureRecognizer | None = None
            presence_hold: HandPresenceHold | None = None
            if control:
                backend = MacOSInputBackend()
                screen_width, screen_height = backend.screen_size()
                action_mapper = ActionMapper(backend)
                if edge_margin is None:
                    cursor_mapper = CursorMapper(screen_width, screen_height)
                else:
                    cursor_mapper = CursorMapper(
                        screen_width, screen_height, edge_margin=edge_margin
                    )
                pointer_recognizer = PointerGestureRecognizer(point_source=cursor_point)
                presence_hold = HandPresenceHold()
                stack.enter_context(
                    SafePauseHotkey(
                        backend.safe_pause,
                        on_toggle=lambda paused: print(
                            f"Input {'paused' if paused else 'resumed'} " "(Ctrl+Option+Command+P)."
                        ),
                    )
                )
                print("Input enabled. Press Ctrl+Option+Command+P to pause or resume.")
            print(f"Debug window open ('{_DEBUG_WINDOW_TITLE}'). Press 'q' to quit.")
            preview_interval_s = _CONTROL_PREVIEW_INTERVAL_S if control else 0.0
            next_preview_at_s = 0.0
            while True:
                frame = camera.read_frame()
                hands = landmarker.detect(frame)
                # Move the pointer before any drawing. The overlay is not on
                # the path that has to stay in time with the hand.
                if (
                    action_mapper is not None
                    and cursor_mapper is not None
                    and pointer_recognizer is not None
                    and presence_hold is not None
                ):
                    _dispatch_pointer_intents(
                        hands,
                        pointer_recognizer,
                        cursor_mapper,
                        action_mapper,
                        presence_hold,
                    )
                now_s = time.monotonic()
                if now_s >= next_preview_at_s:
                    draw_hand_landmarks(frame, hands)
                    cv2.imshow(_DEBUG_WINDOW_TITLE, frame)
                    next_preview_at_s = now_s + preview_interval_s
                if cv2.waitKey(1) & 0xFF == _QUIT_KEY:
                    break
    except CameraUnavailableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        cv2.destroyAllWindows()
    return 0


def run_voice_command(command: str) -> int:
    """Parse one deterministic Chrome command and dispatch it through the backend.

    Does not open a camera. On success the macOS backend either opens an https
    URL in Google Chrome or sends a fixed Chrome navigation shortcut.

    Args:
        command: Voice-style phrase such as ``open cursor webpage`` or
            ``next tab``.

    Returns:
        ``0`` when an intent was dispatched, ``1`` when the phrase was not
        recognized (nothing is opened).
    """
    intent = parse_command(command)
    if intent is None:
        print(f"error: unrecognized command: {command!r}", file=sys.stderr)
        return 1
    if intent.kind is IntentType.EDIT_FOCUSED_PAGE_FIELD:
        from gesture_control.browser.bridge import ChromePageBridge

        try:
            with ChromePageBridge() as page_bridge:
                backend = MacOSInputBackend(page_bridge=page_bridge)
                ActionMapper(backend).dispatch(intent)
        except (RuntimeError, OSError, ValueError) as exc:
            print(f"error: cannot edit the active page field: {exc}", file=sys.stderr)
            return 1
        return 0
    backend = MacOSInputBackend()
    ActionMapper(backend).dispatch(intent)
    return 0


def run_voice_session(model_name: str = "tiny.en") -> int:
    """Run continuous local microphone commands for macOS Chrome.

    Optional audio and transcription modules are imported only when this mode
    is explicitly selected, keeping gesture-only startup independent of voice
    packages.

    Args:
        model_name: faster-whisper model id or local model directory.

    Returns:
        ``0`` after a clean Ctrl+C shutdown, or ``1`` when voice setup/runtime
        fails.
    """
    print("Local voice mode uses the default microphone and never uploads audio.")
    print(
        f"Loading faster-whisper model {model_name!r}; " "the first use may download and cache it."
    )
    try:
        from gesture_control.browser.bridge import ChromePageBridge
        from gesture_control.voice.agent import VoiceAgent
        from gesture_control.voice.audio import MicrophoneUtteranceRecorder
        from gesture_control.voice.live_page import LivePageCommandResolver
        from gesture_control.voice.transcription import FasterWhisperTranscriber

        with ChromePageBridge() as page_bridge:
            backend = MacOSInputBackend(page_bridge=page_bridge)
            page_resolver = LivePageCommandResolver(page_bridge)
            agent = VoiceAgent(
                MicrophoneUtteranceRecorder(),
                FasterWhisperTranscriber(model_name=model_name),
                ActionMapper(backend),
                page_resolver=page_resolver.resolve,
                page_prefetch=page_resolver.warm,
            )
            with SafePauseHotkey(
                backend.safe_pause,
                on_toggle=lambda paused: print(
                    f"Input {'paused' if paused else 'resumed'} " "(Ctrl+Option+Command+P)."
                ),
            ):
                print(
                    "Listening for commands. Focus Google Chrome; "
                    "press Ctrl+C to stop. Page click/type requires the Chrome bridge."
                )
                agent.run_forever()
    except KeyboardInterrupt:
        print("\nVoice mode stopped.")
        return 0
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def run_streaming_voice_session(
    model_arch: str = "web_speech",
    *,
    redecode: bool = False,
) -> int:
    """Run the streaming voice agent.

    Args:
        model_arch: ``web_speech`` (Chrome Web Speech), ``small_streaming`` /
            ``medium_streaming`` (Moonshine), or ``mlx_turbo`` (MLX Whisper
            large-v3-turbo).
        redecode: When True with Moonshine, FINAL lines are re-transcribed with
            MLX Whisper ``large-v3-turbo``.

    Returns:
        ``0`` after a clean Ctrl+C shutdown, or ``1`` when setup/runtime fails.
    """
    if model_arch == "web_speech":
        print(
            "Streaming STT is Chrome Web Speech. Audio is sent to Google. "
            "The agent stays on this machine."
        )
    else:
        print("Streaming voice mode uses the default microphone and never uploads audio.")
    if model_arch == "mlx_turbo":
        print("STT backend: MLX Whisper large-v3-turbo (silence-endpointed).")
    elif redecode and model_arch != "web_speech":
        print("FINAL redecode enabled (MLX Whisper large-v3-turbo).")
    try:
        from gesture_control.backends.macos import frontmost_app_name
        from gesture_control.browser.bridge import ChromePageBridge
        from gesture_control.voice.executor import QueuedStepExecutor
        from gesture_control.voice.live_page import LivePageCommandResolver
        from gesture_control.voice.pill_wiring import (
            default_pill_dir,
            mirror_output,
            mirror_reports,
        )
        from gesture_control.voice.planner import DeterministicClausePlanner
        from gesture_control.voice.redecode import MlxWhisperFinalRedecoder
        from gesture_control.voice.segmenter import DeterministicClauseSegmenter
        from gesture_control.voice.status_hub import StatusHub
        from gesture_control.voice.stream_contracts import StepReport
        from gesture_control.voice.streaming_agent import StreamingVoiceAgent

        hub = StatusHub()
        with ChromePageBridge() as page_bridge:
            backend = MacOSInputBackend(page_bridge=page_bridge)
            page_resolver = LivePageCommandResolver(page_bridge)
            page_resolver.warm()
            mapper = ActionMapper(backend)

            def report(step_report: StepReport) -> None:
                print(f"[{step_report.outcome.value}] {step_report.detail}")

            class _FocusPort:
                def frontmost_app(self) -> str | None:
                    return frontmost_app_name()

            executor = QueuedStepExecutor(
                mapper=mapper,
                page=page_resolver,
                focus=_FocusPort(),
                safe_pause=backend.safe_pause,
                report=mirror_reports(hub, report),
            )
            if model_arch == "web_speech":
                from gesture_control.voice.web_speech import WebSpeechStreamingTranscriber

                pill_dir = default_pill_dir()
                if pill_dir is None:
                    print(
                        "Pill UI is not built (run `npm install && npm run build` in ui/); "
                        "using the plain control page."
                    )
                transcriber: object = WebSpeechStreamingTranscriber(
                    open_browser=True,
                    hub=hub,
                    static_dir=pill_dir,
                )
            elif model_arch == "mlx_turbo":
                from gesture_control.voice.mlx_stt import MlxWhisperStreamingTranscriber

                transcriber = MlxWhisperStreamingTranscriber()
            else:
                from gesture_control.voice.moonshine_stt import (
                    MoonshineStreamingTranscriber,
                )

                redecoder = MlxWhisperFinalRedecoder() if redecode else None
                transcriber = MoonshineStreamingTranscriber(
                    model_arch=model_arch,
                    redecoder=redecoder,
                )
            agent = StreamingVoiceAgent(
                transcriber,  # type: ignore[arg-type]
                DeterministicClauseSegmenter(),
                DeterministicClausePlanner(preferences=hub.preferences),
                executor,
                output=mirror_output(hub),
                preferences=hub.preferences,
            )
            with SafePauseHotkey(
                backend.safe_pause,
                on_toggle=lambda paused: print(
                    f"Input {'paused' if paused else 'resumed'} " "(Ctrl+Option+Command+P)."
                ),
            ):
                print("Streaming voice listening. Speak continuously; " "press Ctrl+C to stop.")
                agent.start()
                control_url = getattr(transcriber, "control_url", None)
                if isinstance(control_url, str):
                    print(f"Voice control page: {control_url}")
                    print(
                        "Allow the microphone in that Chrome window, click "
                        "Start microphone, and leave the window open."
                    )
                try:
                    while True:
                        time.sleep(0.25)
                except KeyboardInterrupt:
                    agent.stop()
                    executor.close()
                    hub.close()
    except KeyboardInterrupt:
        print("\nStreaming voice mode stopped.")
        return 0
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def run_dump_page() -> int:
    """Print the active Chrome tab's indexed controls for phrase discovery.

    Returns:
        ``0`` when a snapshot was printed, or ``1`` when the bridge is
        unavailable.
    """
    try:
        from gesture_control.browser.bridge import BridgeError, ChromePageBridge
    except ImportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    try:
        with ChromePageBridge(timeout=5.0) as bridge:
            snapshot = bridge.snapshot()
    except (BridgeError, RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "Install/reload the unpacked extension and native host "
            "(see docs/CHROME_PAGE_BRIDGE.md), focus an HTTPS tab, then retry.",
            file=sys.stderr,
        )
        return 1
    print(f"URL: {snapshot.url}")
    print(f"Title: {snapshot.title}")
    if snapshot.seo.site_name:
        print(f"Site: {snapshot.seo.site_name}")
    if snapshot.seo.og_title:
        print(f"OG title: {snapshot.seo.og_title}")
    if snapshot.seo.description:
        print(f"Description: {snapshot.seo.description}")
    if snapshot.seo.keywords:
        print(f"Keywords: {', '.join(snapshot.seo.keywords)}")
    if snapshot.seo.canonical_url:
        print(f"Canonical: {snapshot.seo.canonical_url}")
    if not snapshot.elements:
        print("No indexed interactive controls on this page.")
        return 0
    print(f"{len(snapshot.elements)} speakable controls:")
    for element in snapshot.elements:
        print(f"  [{element.role}] {element.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the gesture control application.

    Command, continuous voice, and camera-debug modes are mutually exclusive.

    Args:
        argv: Command-line arguments, excluding the program name. Defaults to
            ``sys.argv[1:]`` when ``None``.

    Returns:
        A process exit code (``0`` on success).
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.control and not args.debug:
        parser.error("--control requires --debug.")
    if args.control and sys.platform != "darwin":
        parser.error("--control is currently supported on macOS only.")
    if args.command is not None and sys.platform != "darwin":
        parser.error("--command is currently supported on macOS only.")
    if args.voice and sys.platform != "darwin":
        parser.error("--voice is currently supported on macOS only.")
    if args.dump_page and sys.platform != "darwin":
        parser.error("--dump-page is currently supported on macOS only.")
    if args.command is not None:
        return run_voice_command(args.command)
    if args.dump_page:
        return run_dump_page()
    if args.voice:
        if args.voice_mode == "streaming":
            return run_streaming_voice_session(
                model_arch=args.voice_stt,
                redecode=args.voice_redecode,
            )
        return run_voice_session(model_name=args.voice_model)
    if args.debug:
        return run_debug_overlay(
            camera_index=args.camera_index,
            control=args.control,
            cursor_point=CursorPointSource(args.cursor_point),
            edge_margin=args.edge_margin,
        )

    print(f"gesture-control {__version__} -- see README.md to get started.")
    return 0


def _dispatch_pointer_intents(
    hands: list[HandObservation],
    pointer_recognizer: PointerGestureRecognizer,
    cursor_mapper: CursorMapper,
    action_mapper: ActionMapper,
    presence_hold: HandPresenceHold,
    timestamp_s: float | None = None,
) -> None:
    """Map the tracked hand into M2 cursor intents.

    Args:
        hands: Hand observations from the current camera frame.
        pointer_recognizer: Stateful pinch recognizer.
        cursor_mapper: Stateful cursor smoothing mapper.
        action_mapper: Shared intent dispatch boundary.
        presence_hold: Bridges single-frame detection drops.
        timestamp_s: Sample time in seconds. Defaults to a monotonic clock.
    """
    now_s = time.monotonic() if timestamp_s is None else timestamp_s
    selected_hand = presence_hold.select(hands, now_s)
    if selected_hand is None:
        pointer_recognizer.reset()
        return
    pointer = pointer_recognizer.recognize(selected_hand)
    # Freeze during pinch approach and the held pinch so closing fingertips
    # (and residual MCP flex) cannot walk the click target away.
    if not pointer.freeze_cursor:
        x, y = cursor_mapper.map(pointer.x, pointer.y, now_s)
        action_mapper.dispatch(Intent(IntentType.MOVE_CURSOR, x=x, y=y))
    if pointer.pinch_started:
        action_mapper.dispatch(Intent(IntentType.CLICK_LEFT))


if __name__ == "__main__":
    raise SystemExit(main())
