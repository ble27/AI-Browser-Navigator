"""Chrome Web Speech bridge into the streaming voice agent.

The recognizer runs in a localhost Chrome window (audio goes to Google). This
module only forwards interim and final text into ``TranscriptEvent``s. Intent
parsing and input injection stay in the local agent.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from gesture_control.voice.stream_contracts import TranscriptEvent, TranscriptEventKind

_MAX_BODY_BYTES = 8_192
_CONTROL_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Gesture Control — voice</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; max-width: 36rem; }
    button { font-size: 1.1rem; padding: 0.6rem 1rem; }
    #status { margin-top: 1rem; }
    #heard { margin-top: 1rem; font-size: 1.4rem; }
  </style>
</head>
<body>
  <h1>Voice control</h1>
  <p>Keep this window open. Speech is recognized by Chrome and sent to the
  local agent. Commands act on your other Chrome window.</p>
  <button id="toggle" type="button">Start microphone</button>
  <p id="status">Stopped</p>
  <p id="heard"></p>
  <script>
    const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
    const statusEl = document.getElementById("status");
    const heardEl = document.getElementById("heard");
    const toggle = document.getElementById("toggle");
    let listening = false;
    let recognition = null;

    function setStatus(text) { statusEl.textContent = text; }

    async function post(kind, text) {
      const trimmed = text.trim();
      if (!trimmed) return;
      heardEl.textContent = trimmed;
      await fetch("/transcript", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({kind: kind, text: trimmed}),
      });
    }

    function ensureRecognition() {
      if (!Rec) {
        setStatus("This browser has no Web Speech API. Use Google Chrome.");
        return null;
      }
      if (recognition) return recognition;
      const session = new Rec();
      session.continuous = true;
      session.interimResults = true;
      session.lang = "en-US";
      session.onresult = (event) => {
        let finalText = "";
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const text = event.results[i][0].transcript;
          if (event.results[i].isFinal) finalText += text;
          else interim += text;
        }
        if (finalText.trim()) post("final", finalText);
        else if (interim.trim()) post("partial", interim);
      };
      session.onerror = (event) => {
        if (event.error === "not-allowed") setStatus("Microphone blocked.");
        else if (event.error !== "no-speech" && event.error !== "aborted") {
          setStatus("Recognition error: " + event.error);
        }
      };
      session.onend = () => {
        if (!listening) return;
        setStatus("Listening");
        try { session.start(); } catch (err) { /* already running */ }
      };
      recognition = session;
      return session;
    }

    toggle.addEventListener("click", () => {
      const session = ensureRecognition();
      if (!session) return;
      if (listening) {
        listening = false;
        session.stop();
        toggle.textContent = "Start microphone";
        setStatus("Stopped");
        return;
      }
      listening = true;
      toggle.textContent = "Stop microphone";
      setStatus("Listening");
      try { session.start(); } catch (err) { setStatus(String(err)); }
    });
  </script>
</body>
</html>
"""


def chrome_web_speech_profile_dir() -> Path:
    """Return the dedicated Chrome profile used only for the control window."""
    return Path.home() / ".gesture-control" / "web-speech-chrome"


def open_chrome_control_window(url: str) -> None:
    """Open ``url`` in a separate Chrome app window so it is not a controlled tab.

    Args:
        url: Localhost control page URL.

    Raises:
        RuntimeError: If the Chrome launch command fails.
    """
    profile = chrome_web_speech_profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.Popen(
            [
                "open",
                "-na",
                "Google Chrome",
                "--args",
                f"--user-data-dir={profile}",
                f"--app={url}",
            ]
        )
    except OSError as exc:
        raise RuntimeError(
            f"Could not open Google Chrome for Web Speech. Open {url} in Chrome."
        ) from exc


class WebSpeechStreamingTranscriber:
    """Serve a localhost control page and emit transcript events from POSTs.

    ``start`` binds ``127.0.0.1`` only. The page uses ``SpeechRecognition``;
    this class never captures the microphone itself.
    """

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        open_browser: bool = False,
        browser_opener: Callable[[str], None] | None = None,
    ) -> None:
        """Create a transcriber that can later bind a localhost control page.

        Args:
            host: Bind address. Must be loopback.
            port: TCP port, or ``0`` to let the OS choose one.
            open_browser: When True, ``start`` opens the control page in Chrome.
            browser_opener: Launch hook for the control URL. Defaults to a
                separate Chrome app window.

        Raises:
            ValueError: If ``host`` is not a loopback address.
        """
        if host not in {"127.0.0.1", "localhost"}:
            raise ValueError("Web Speech bridge binds to loopback only.")
        self._host = host
        self._port = port
        self._open_browser = open_browser
        self._browser_opener = browser_opener or open_chrome_control_window
        self._sink: Callable[[TranscriptEvent], None] | None = None
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._line_id = 0
        self._last_key: tuple[str, str, int] | None = None

    @property
    def control_url(self) -> str:
        """Base URL of the control page, available after ``start``."""
        if self._httpd is None:
            raise RuntimeError("Web Speech bridge is not running.")
        host, port = self._httpd.server_address[:2]
        if isinstance(host, bytes):
            host = host.decode("ascii")
        return f"http://{host}:{port}/"

    def start(self, sink: Callable[[TranscriptEvent], None]) -> None:
        """Bind the control page and begin accepting transcript posts.

        Args:
            sink: Callback invoked for each accepted transcript event.
        """
        self._sink = sink
        handler = _handler_for(self)
        self._httpd = ThreadingHTTPServer((self._host, self._port), handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="web-speech-bridge",
            daemon=True,
        )
        self._thread.start()
        if self._open_browser:
            self._browser_opener(self.control_url)

    def stop(self) -> None:
        """Stop the control server. Safe to call more than once."""
        httpd = self._httpd
        thread = self._thread
        self._httpd = None
        self._thread = None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if thread is not None:
            thread.join(timeout=2.0)
        self._sink = None

    def submit(self, payload: object) -> TranscriptEvent | None:
        """Accept one recognition payload and emit a transcript event.

        Args:
            payload: JSON object with ``kind`` (``partial`` or ``final``) and
                ``text``.

        Returns:
            The emitted event, or ``None`` when the payload is ignored.
        """
        event = self._event_from_payload(payload)
        if event is None:
            return None
        sink = self._sink
        if sink is None:
            return None
        sink(event)
        return event

    def _event_from_payload(self, payload: object) -> TranscriptEvent | None:
        if not isinstance(payload, dict):
            return None
        kind_raw = payload.get("kind")
        text_raw = payload.get("text")
        if not isinstance(kind_raw, str) or not isinstance(text_raw, str):
            return None
        text = " ".join(text_raw.split())
        if not text:
            return None
        try:
            kind = TranscriptEventKind(kind_raw)
        except ValueError:
            return None
        with self._lock:
            line_id = self._line_id
            key = (kind.value, text, line_id)
            if key == self._last_key:
                return None
            self._last_key = key
            if kind is TranscriptEventKind.FINAL:
                self._line_id += 1
                self._last_key = None
        return TranscriptEvent(kind, text, line_id, time.monotonic())


def _handler_for(owner: WebSpeechStreamingTranscriber) -> type[BaseHTTPRequestHandler]:
    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path not in {"/", "/index.html"}:
                self.send_error(404)
                return
            body = _CONTROL_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path != "/transcript":
                self.send_error(404)
                return
            length_raw = self.headers.get("Content-Length", "0")
            try:
                length = int(length_raw)
            except ValueError:
                self.send_error(400)
                return
            if length < 0 or length > _MAX_BODY_BYTES:
                self.send_error(413)
                return
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.send_error(400)
                return
            owner.submit(payload)
            self.send_response(204)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    return _Handler
