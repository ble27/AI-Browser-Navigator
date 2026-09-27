"""Chrome Native Messaging host relay for the local Unix socket."""

from __future__ import annotations

import argparse
import re
import socket
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import BinaryIO, cast

from gesture_control.browser.bridge import default_socket_path
from gesture_control.browser.native_protocol import (
    ProtocolError,
    read_message,
    validate_request,
    validate_response,
    write_message,
)

# The extension normally starts at Chrome launch, while ``--voice`` or
# ``--dump-page`` can start much later. Keep its one local process available
# long enough for the app socket to appear without relying on an MV3 worker
# timer surviving while idle.
_SOCKET_CONNECT_TIMEOUT_S = 300.0
_SOCKET_CONNECT_RETRY_S = 0.1
_EXTENSION_ORIGIN_PATTERN = re.compile(r"chrome-extension://[a-p]{32}/")


def _parse_extension_origin(value: str) -> str:
    """Validate Chrome's Native Messaging caller-origin argument.

    Args:
        value: Origin passed by Chrome when it launches the native host.

    Returns:
        The validated extension origin.

    Raises:
        argparse.ArgumentTypeError: If the value is not a Chrome extension origin.
    """
    if _EXTENSION_ORIGIN_PATTERN.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("expected a chrome-extension:// origin")
    return value


def connect_to_app_socket(socket_path: Path) -> socket.socket:
    """Connect to an app bridge socket, tolerating startup ordering.

    Chrome can start its Native Messaging host before the Python app creates
    its socket. Keep the host alive briefly so Chrome does not discard its
    native port during that normal race.

    Args:
        socket_path: User-private Unix socket owned by ``ChromePageBridge``.

    Returns:
        Connected Unix-domain socket.

    Raises:
        OSError: If the socket remains unavailable for the bounded timeout.
    """
    deadline = time.monotonic() + _SOCKET_CONNECT_TIMEOUT_S
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            connection.connect(str(socket_path))
            return connection
        except OSError as exc:
            connection.close()
            last_error = exc
            time.sleep(_SOCKET_CONNECT_RETRY_S)
    assert last_error is not None
    raise last_error


def relay_messages(
    connection: socket.socket,
    chrome_input: BinaryIO,
    chrome_output: BinaryIO,
) -> None:
    """Relay validated framed messages between Chrome and the app socket.

    App requests flow from the socket to Chrome stdout. Extension responses
    flow from Chrome stdin back to the socket. No network listener is opened.

    Args:
        connection: Connected Unix-domain socket owned by the app.
        chrome_input: Native Messaging input stream from Chrome.
        chrome_output: Native Messaging output stream to Chrome.

    Raises:
        OSError: If either transport fails.
        ProtocolError: If either peer sends a malformed protocol message.
    """
    socket_input = cast(BinaryIO, connection.makefile("rb", buffering=0))
    socket_output = cast(BinaryIO, connection.makefile("wb", buffering=0))

    def forward_responses() -> None:
        try:
            while True:
                response = read_message(chrome_input)
                if response is None:
                    return
                write_message(socket_output, validate_response(response))
        finally:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    response_thread = threading.Thread(
        target=forward_responses,
        name="chrome-native-responses",
        daemon=True,
    )
    response_thread.start()
    try:
        while True:
            request = read_message(socket_input)
            if request is None:
                return
            write_message(chrome_output, validate_request(request))
    finally:
        try:
            connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        socket_input.close()
        socket_output.close()


def build_parser() -> argparse.ArgumentParser:
    """Build the native host command-line parser.

    Returns:
        Parser accepting Chrome's caller origin and an optional local socket path.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    # Chrome appends the calling extension's origin to the native host command.
    # Without this positional argument, argparse exits before the relay starts.
    parser.add_argument("origin", nargs="?", type=_parse_extension_origin)
    parser.add_argument(
        "--socket",
        type=Path,
        default=default_socket_path(),
        help="app-owned Unix socket path",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Connect to the app socket and relay Native Messaging traffic.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Process exit status.
    """
    args = build_parser().parse_args(argv)
    connection: socket.socket | None = None
    try:
        connection = connect_to_app_socket(args.socket)
        relay_messages(connection, sys.stdin.buffer, sys.stdout.buffer)
    except (OSError, ProtocolError) as exc:
        print(f"Chrome page bridge native host: {exc}", file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
