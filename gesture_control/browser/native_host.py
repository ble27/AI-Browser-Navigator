"""Chrome Native Messaging host relay for the local Unix socket."""

from __future__ import annotations

import argparse
import socket
import sys
import threading
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
        Parser accepting an optional local socket path.
    """
    parser = argparse.ArgumentParser(description=__doc__)
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
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        connection.connect(str(args.socket))
        relay_messages(connection, sys.stdin.buffer, sys.stdout.buffer)
    except (OSError, ProtocolError) as exc:
        print(f"Chrome page bridge native host: {exc}", file=sys.stderr)
        return 1
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
