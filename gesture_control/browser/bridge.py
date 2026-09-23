"""Synchronous app-side server for the local Chrome page bridge."""

from __future__ import annotations

import errno
import os
import socket
import stat
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Self, cast

from gesture_control.browser.native_protocol import (
    Operation,
    ProtocolError,
    read_message,
    validate_request,
    validate_response,
    write_message,
)

DEFAULT_TIMEOUT_SECONDS = 5.0


class BridgeError(RuntimeError):
    """Base error for Chrome page bridge failures."""


class BridgeDisconnectedError(BridgeError):
    """Raised when the extension/native host is not connected."""


class BridgeTimeoutError(BridgeError):
    """Raised when connecting to or receiving from Chrome times out."""


@dataclass(frozen=True, slots=True)
class PageElement:
    """An interactive element exposed by the active page.

    Attributes:
        element_id: Opaque stable-in-page identifier.
        role: One of button, link, textbox, or checkbox.
        name: Accessible-ish name presented for command matching.
    """

    element_id: str
    role: str
    name: str


@dataclass(frozen=True, slots=True)
class PageSnapshot:
    """A point-in-time index of the active HTTPS page.

    Attributes:
        url: Active page URL.
        title: Active page title.
        elements: Interactive elements in document order.
    """

    url: str
    title: str
    elements: tuple[PageElement, ...]


def default_socket_path() -> Path:
    """Return the user-private default Unix socket path.

    Returns:
        A path below the current user's application-support directory.
    """
    configured = os.environ.get("AI_GESTURES_PAGE_BRIDGE_SOCKET")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / "Library" / "Application Support" / "AI Gestures Tool" / "page_bridge.sock"


class ChromePageBridge:
    """Own a Unix socket and synchronously issue fixed page operations."""

    def __init__(
        self, socket_path: Path | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS
    ) -> None:
        """Initialize a stopped bridge server.

        Args:
            socket_path: Override for the user-private Unix socket.
            timeout: Default connect/response timeout in seconds.

        Raises:
            ValueError: If ``timeout`` is not positive.
        """
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.socket_path = socket_path or default_socket_path()
        self.timeout = timeout
        self._listener: socket.socket | None = None
        self._connection: socket.socket | None = None
        self._reader: BinaryIO | None = None
        self._writer: BinaryIO | None = None
        self._accept_thread: threading.Thread | None = None
        self._connected = threading.Event()
        self._closed = threading.Event()
        self._request_lock = threading.Lock()
        self._state_lock = threading.Lock()

    def start(self) -> None:
        """Create the private socket and begin accepting the native relay.

        Raises:
            BridgeError: If the path is unsafe, already active, or cannot bind.
        """
        if self._listener is not None:
            return
        self._prepare_socket_directory()
        self._remove_stale_socket()
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(str(self.socket_path))
            os.chmod(self.socket_path, 0o600)
            listener.listen(1)
            listener.settimeout(0.25)
        except OSError as exc:
            listener.close()
            raise BridgeError(f"Cannot create Chrome page bridge socket: {exc}") from exc
        self._closed.clear()
        self._listener = listener
        self._accept_thread = threading.Thread(
            target=self._accept_connections,
            name="chrome-page-bridge",
            daemon=True,
        )
        self._accept_thread.start()

    def close(self) -> None:
        """Stop the server, close its relay, and remove its socket file."""
        self._closed.set()
        self._connected.clear()
        listener = self._listener
        self._listener = None
        if listener is not None:
            listener.close()
        self._drop_connection()
        thread = self._accept_thread
        self._accept_thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        try:
            socket_stat = self.socket_path.lstat()
            if stat.S_ISSOCK(socket_stat.st_mode) and socket_stat.st_uid == os.getuid():
                self.socket_path.unlink()
        except FileNotFoundError:
            pass

    def __enter__(self) -> Self:
        """Start and return this bridge for context-manager use."""
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close this bridge when leaving a context manager."""
        self.close()

    def snapshot(self, timeout: float | None = None) -> PageSnapshot:
        """Index named interactive elements on the active HTTPS tab.

        Args:
            timeout: Per-call timeout override.

        Returns:
            Validated active-page metadata and elements.
        """
        result = self._request(Operation.SNAPSHOT, timeout=timeout)
        return _parse_snapshot(result)

    def click(self, target_id: str, timeout: float | None = None) -> None:
        """Click an element from the latest page snapshot.

        Args:
            target_id: Opaque element identifier.
            timeout: Per-call timeout override.
        """
        self._request(Operation.CLICK, target_id=target_id, timeout=timeout)

    def focus(self, target_id: str, timeout: float | None = None) -> None:
        """Focus an element from the latest page snapshot.

        Args:
            target_id: Opaque element identifier.
            timeout: Per-call timeout override.
        """
        self._request(Operation.FOCUS, target_id=target_id, timeout=timeout)

    def type_text(self, target_id: str, text: str, timeout: float | None = None) -> None:
        """Replace a textbox value and dispatch input/change events.

        Args:
            target_id: Opaque textbox identifier.
            text: Text to place in the target.
            timeout: Per-call timeout override.
        """
        self._request(Operation.TYPE, target_id=target_id, text=text, timeout=timeout)

    def type_and_submit(self, target_id: str, text: str, timeout: float | None = None) -> None:
        """Replace a textbox value and submit its containing form.

        Args:
            target_id: Opaque textbox identifier.
            text: Text to place in the target.
            timeout: Per-call timeout override.
        """
        self._request(Operation.SUBMIT, target_id=target_id, text=text, timeout=timeout)

    def _request(
        self,
        operation: Operation,
        *,
        target_id: str | None = None,
        text: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, object]:
        """Send one request and return its successful result object."""
        wait_seconds = self.timeout if timeout is None else timeout
        if wait_seconds <= 0:
            raise ValueError("timeout must be positive")
        request_id = uuid.uuid4().hex
        request: dict[str, object] = {
            "request_id": request_id,
            "operation": operation.value,
        }
        if target_id is not None:
            request["target_id"] = target_id
        if text is not None:
            request["text"] = text
        try:
            validated_request = validate_request(request)
        except ProtocolError as exc:
            raise BridgeError(f"Invalid Chrome page bridge request: {exc}") from exc

        with self._request_lock:
            if not self._connected.wait(wait_seconds):
                raise BridgeDisconnectedError(
                    "Chrome page bridge is disconnected. Start Chrome with the unpacked "
                    "extension and install its native host."
                )
            connection, reader, writer = self._current_streams()
            connection.settimeout(wait_seconds)
            try:
                write_message(writer, validated_request)
                raw_response = read_message(reader)
                if raw_response is None:
                    raise BridgeDisconnectedError("Chrome native host disconnected")
                response = validate_response(raw_response)
            except TimeoutError as exc:
                self._drop_connection()
                raise BridgeTimeoutError(
                    f"Chrome page bridge did not respond within {wait_seconds:g} seconds"
                ) from exc
            except (OSError, ProtocolError) as exc:
                self._drop_connection()
                raise BridgeDisconnectedError(
                    f"Chrome page bridge connection failed: {exc}"
                ) from exc
            if response["request_id"] != request_id:
                self._drop_connection()
                raise BridgeDisconnectedError("Chrome page bridge returned a mismatched request ID")
            if not response["ok"]:
                raise BridgeError(str(response["error"]))
            result = response["result"]
            assert isinstance(result, dict)
            return result

    def _prepare_socket_directory(self) -> None:
        """Create and restrict the socket parent directory."""
        parent = self.socket_path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent_stat = parent.stat()
        if parent_stat.st_uid != os.getuid():
            raise BridgeError(f"Socket directory is not owned by this user: {parent}")
        os.chmod(parent, 0o700)

    def _remove_stale_socket(self) -> None:
        """Remove only an owned, inactive Unix socket at the configured path."""
        try:
            socket_stat = self.socket_path.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(socket_stat.st_mode) or socket_stat.st_uid != os.getuid():
            raise BridgeError(f"Refusing to replace unsafe socket path: {self.socket_path}")
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            probe.settimeout(0.2)
            probe.connect(str(self.socket_path))
        except OSError as exc:
            if exc.errno not in {errno.ECONNREFUSED, errno.ENOENT}:
                raise BridgeError(f"Cannot verify existing bridge socket: {exc}") from exc
        else:
            raise BridgeError(f"Chrome page bridge socket is already active: {self.socket_path}")
        finally:
            probe.close()
        self.socket_path.unlink(missing_ok=True)

    def _accept_connections(self) -> None:
        """Accept relay connections until the bridge closes."""
        while not self._closed.is_set():
            listener = self._listener
            if listener is None:
                return
            try:
                connection, _ = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            reader = cast(BinaryIO, connection.makefile("rb", buffering=0))
            writer = cast(BinaryIO, connection.makefile("wb", buffering=0))
            with self._state_lock:
                old_connection = self._connection
                old_reader = self._reader
                old_writer = self._writer
                self._connection = connection
                self._reader = reader
                self._writer = writer
                self._connected.set()
            _close_streams(old_connection, old_reader, old_writer)

    def _current_streams(self) -> tuple[socket.socket, BinaryIO, BinaryIO]:
        """Return the current connected relay streams."""
        with self._state_lock:
            if self._connection is None or self._reader is None or self._writer is None:
                self._connected.clear()
                raise BridgeDisconnectedError("Chrome page bridge relay is not connected")
            return self._connection, self._reader, self._writer

    def _drop_connection(self) -> None:
        """Atomically detach and close the current relay connection."""
        with self._state_lock:
            connection = self._connection
            reader = self._reader
            writer = self._writer
            self._connection = None
            self._reader = None
            self._writer = None
            self._connected.clear()
        _close_streams(connection, reader, writer)


def _close_streams(
    connection: socket.socket | None, reader: BinaryIO | None, writer: BinaryIO | None
) -> None:
    """Close one socket and its file wrappers without surfacing teardown errors."""
    for stream in (reader, writer):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
    if connection is not None:
        try:
            connection.close()
        except OSError:
            pass


def _parse_snapshot(result: dict[str, object]) -> PageSnapshot:
    """Validate a snapshot result from the extension."""
    if set(result) != {"url", "title", "elements"}:
        raise BridgeError("Chrome returned an invalid snapshot")
    url = result["url"]
    title = result["title"]
    raw_elements = result["elements"]
    if not isinstance(url, str) or not url.startswith("https://") or not isinstance(title, str):
        raise BridgeError("Chrome returned invalid page metadata")
    if not isinstance(raw_elements, list):
        raise BridgeError("Chrome returned invalid page elements")
    elements: list[PageElement] = []
    for raw_element in raw_elements:
        if not isinstance(raw_element, dict) or set(raw_element) != {"id", "role", "name"}:
            raise BridgeError("Chrome returned an invalid page element")
        element_id = raw_element["id"]
        role = raw_element["role"]
        name = raw_element["name"]
        if (
            not isinstance(element_id, str)
            or not element_id
            or role not in {"button", "link", "textbox", "checkbox"}
            or not isinstance(name, str)
            or not name
        ):
            raise BridgeError("Chrome returned an invalid page element")
        assert isinstance(role, str)
        elements.append(PageElement(element_id=element_id, role=role, name=name))
    return PageSnapshot(url=url, title=title, elements=tuple(elements))
