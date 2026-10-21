"""Chrome Web Speech bridge into the streaming voice agent.

The recognizer runs in a localhost Chrome window (audio goes to Google). This
module only forwards interim and final text into ``TranscriptEvent``s. Intent
parsing and input injection stay in the local agent.
"""

from __future__ import annotations

import json
import mimetypes
import subprocess
import threading
import time
from collections.abc import Callable
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from gesture_control.voice.status_hub import StatusHub
from gesture_control.voice.stream_contracts import TranscriptEvent, TranscriptEventKind

_MAX_BODY_BYTES = 8_192
# How often an idle SSE stream checks for shutdown, and how many of those
# checks pass between keep-alive comments (keeps proxies and tabs from timing out).
_SSE_POLL_S = 0.5
_SSE_KEEPALIVE_POLLS = 30
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
                # Small window sized for the pill; the page itself is transparent.
                "--window-size=420,110",
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
        hub: StatusHub | None = None,
        static_dir: Path | None = None,
    ) -> None:
        """Create a transcriber that can later bind a localhost control page.

        Args:
            host: Bind address. Must be loopback.
            port: TCP port, or ``0`` to let the OS choose one.
            open_browser: When True, ``start`` opens the control page in Chrome.
            browser_opener: Launch hook for the control URL. Defaults to a
                separate Chrome app window.
            hub: Optional status hub. When given, the server exposes the
                ``/api`` endpoints and drops transcripts while the hub is
                switched off.
            static_dir: Optional directory of a built pill UI to serve at ``/``.
                The inline control page is used when it is missing.

        Raises:
            ValueError: If ``host`` is not a loopback address.
        """
        if host not in {"127.0.0.1", "localhost"}:
            raise ValueError("Web Speech bridge binds to loopback only.")
        self._host = host
        self._port = port
        self._open_browser = open_browser
        self._browser_opener = browser_opener or open_chrome_control_window
        self._hub = hub
        self._static_dir = static_dir
        self._stopping = threading.Event()
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
        self._stopping.clear()
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
        self._stopping.set()
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
        hub = self._hub
        if hub is not None:
            if not hub.enabled:
                return None
            hub.publish({"type": "transcript", "kind": event.kind.value, "text": event.text})
        sink(event)
        return event

    @property
    def port(self) -> int:
        """TCP port the bridge is bound to, available after ``start``."""
        if self._httpd is None:
            raise RuntimeError("Web Speech bridge is not running.")
        return int(self._httpd.server_address[1])

    @property
    def hub(self) -> StatusHub | None:
        """Status hub backing the ``/api`` endpoints, if any."""
        return self._hub

    @property
    def stopping(self) -> threading.Event:
        """Set while the server is shutting down so streams can end."""
        return self._stopping

    @property
    def static_dir(self) -> Path | None:
        """Directory of the built pill UI, if configured."""
        return self._static_dir

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


def _origin_allowed(headers: Message, port: int) -> bool:
    """Accept only requests that really came from this loopback origin.

    Any web page can fire requests at ``127.0.0.1``. Rejecting foreign
    ``Origin`` headers stops a hostile site from injecting voice commands, and
    checking ``Host`` stops DNS-rebinding variants of the same attack.

    Args:
        headers: Request headers.
        port: Port the bridge is bound to.

    Returns:
        True when the request may proceed.
    """
    allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
    host = headers.get("Host")
    if host is not None and host.casefold() not in allowed:
        return False
    origin = headers.get("Origin")
    if origin is None:
        return True
    return origin.casefold() in {f"http://{value}" for value in allowed}


def _read_static(root: Path, request_path: str) -> tuple[bytes, str] | None:
    """Read a built UI file without letting the path escape ``root``.

    Args:
        root: Built UI directory.
        request_path: URL path from the request.

    Returns:
        ``(body, content_type)`` or ``None`` when absent or outside ``root``.
    """
    relative = unquote(request_path).lstrip("/") or "index.html"
    try:
        base = root.resolve()
        target = (base / relative).resolve()
    except (OSError, ValueError):
        return None
    if not target.is_relative_to(base) or not target.is_file():
        return None
    content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return target.read_bytes(), content_type


def _handler_for(owner: WebSpeechStreamingTranscriber) -> type[BaseHTTPRequestHandler]:
    class _Handler(BaseHTTPRequestHandler):
        def _allowed(self) -> bool:
            if _origin_allowed(self.headers, owner.port):
                return True
            self.send_error(403)
            return False

        def _send_json(self, status: int, payload: object) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_body(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _stream_events(self, hub: StatusHub) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            subscription = hub.subscribe()
            polls = 0
            try:
                first = {"type": "state", **hub.snapshot()}
                self.wfile.write(f"data: {json.dumps(first)}\n\n".encode())
                self.wfile.flush()
                while not owner.stopping.is_set():
                    event = subscription.get(_SSE_POLL_S)
                    if event is None:
                        if hub.closed:
                            return
                        polls += 1
                        if polls % _SSE_KEEPALIVE_POLLS == 0:
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                        continue
                    self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                return
            finally:
                hub.unsubscribe(subscription)

        def do_GET(self) -> None:  # noqa: N802
            if not self._allowed():
                return
            path = self.path.split("?", 1)[0]
            hub = owner.hub
            if path.startswith("/api/"):
                if hub is None:
                    self.send_error(404)
                elif path == "/api/state":
                    self._send_json(200, hub.snapshot())
                elif path == "/api/events":
                    self._stream_events(hub)
                else:
                    self.send_error(404)
                return
            static_dir = owner.static_dir
            if static_dir is not None:
                asset = _read_static(static_dir, path)
                if asset is not None:
                    self._send_body(*asset)
                    return
            if path not in {"/", "/index.html"}:
                self.send_error(404)
                return
            self._send_body(_CONTROL_PAGE.encode("utf-8"), "text/html; charset=utf-8")

        def _read_json_body(self) -> object | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_error(400)
                return None
            if length < 0 or length > _MAX_BODY_BYTES:
                self.send_error(413)
                return None
            raw = self.rfile.read(length)
            try:
                payload: object = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.send_error(400)
                return None
            return payload

        def do_POST(self) -> None:  # noqa: N802
            if not self._allowed():
                return
            path = self.path.split("?", 1)[0]
            if path not in {"/transcript", "/api/enabled"}:
                self.send_error(404)
                return
            hub = owner.hub
            if path == "/api/enabled" and hub is None:
                self.send_error(404)
                return
            payload = self._read_json_body()
            if payload is None:
                return
            if path == "/api/enabled":
                assert hub is not None
                value = payload.get("enabled") if isinstance(payload, dict) else None
                if not isinstance(value, bool):
                    self.send_error(400)
                    return
                hub.set_enabled(value)
                self._send_json(200, {"enabled": hub.enabled})
                return
            owner.submit(payload)
            self.send_response(204)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    return _Handler
