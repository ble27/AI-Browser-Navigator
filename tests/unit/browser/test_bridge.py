from __future__ import annotations

import socket
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from gesture_control.backends.base import FocusedPageFieldAction
from gesture_control.browser.bridge import (
    BridgeDisconnectedError,
    BridgeError,
    BridgeTimeoutError,
    ChromePageBridge,
    PageElement,
    PageSnapshot,
)
from gesture_control.browser.native_protocol import read_message, write_message


@pytest.fixture
def socket_dir() -> Iterator[Path]:
    """Provide a short path below macOS's Unix-socket path limit."""
    with tempfile.TemporaryDirectory(prefix="gcb-", dir="/tmp") as directory:
        yield Path(directory)


def _run_fake_relay(
    socket_path: Path,
    responses: list[dict[str, object]],
    requests: list[dict[str, object]],
    errors: list[BaseException],
) -> None:
    try:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.connect(str(socket_path))
        reader = connection.makefile("rb", buffering=0)
        writer = connection.makefile("wb", buffering=0)
        with connection, reader, writer:
            for response in responses:
                request = read_message(reader)
                assert request is not None
                requests.append(request)
                write_message(
                    writer,
                    {
                        "request_id": request["request_id"],
                        **response,
                    },
                )
    except BaseException as exc:
        errors.append(exc)


def test_bridge_issues_all_fixed_operations(socket_dir: Path) -> None:
    socket_path = socket_dir / "private" / "bridge.sock"
    requests: list[dict[str, object]] = []
    errors: list[BaseException] = []
    responses: list[dict[str, object]] = [
        {
            "ok": True,
            "result": {
                "url": "https://example.test/",
                "title": "Fixture",
                "elements": [{"id": "nonce:1", "role": "textbox", "name": "Email"}],
            },
        },
        {"ok": True, "result": {}},
        {"ok": True, "result": {}},
        {"ok": True, "result": {}},
        {"ok": True, "result": {}},
        {"ok": True, "result": {}},
    ]

    with ChromePageBridge(socket_path=socket_path, timeout=1.0) as bridge:
        relay = threading.Thread(
            target=_run_fake_relay,
            args=(socket_path, responses, requests, errors),
        )
        relay.start()
        assert bridge.snapshot() == PageSnapshot(
            url="https://example.test/",
            title="Fixture",
            elements=(PageElement(element_id="nonce:1", role="textbox", name="Email"),),
        )
        bridge.click("nonce:1")
        bridge.focus("nonce:1")
        bridge.type_text("nonce:1", "hello")
        bridge.type_and_submit("nonce:1", "send")
        bridge.edit_focused_field(FocusedPageFieldAction.DELETE_WORD)
        relay.join(timeout=1.0)

    assert not errors
    assert [request["operation"] for request in requests] == [
        "snapshot",
        "click",
        "focus",
        "type",
        "submit",
        "edit_focused_field",
    ]
    assert requests[3]["text"] == "hello"
    assert requests[4]["text"] == "send"
    assert requests[5]["action"] == "delete_word"
    assert not socket_path.exists()
    assert (socket_path.parent.stat().st_mode & 0o777) == 0o700


def test_bridge_surfaces_extension_error(socket_dir: Path) -> None:
    socket_path = socket_dir / "bridge.sock"
    requests: list[dict[str, object]] = []
    errors: list[BaseException] = []

    with ChromePageBridge(socket_path=socket_path, timeout=1.0) as bridge:
        relay = threading.Thread(
            target=_run_fake_relay,
            args=(
                socket_path,
                [{"ok": False, "error": "Target is no longer available"}],
                requests,
                errors,
            ),
        )
        relay.start()
        with pytest.raises(BridgeError, match="no longer available"):
            bridge.click("old-id")
        relay.join(timeout=1.0)

    assert not errors


def test_bridge_reports_actionable_disconnected_error(socket_dir: Path) -> None:
    with ChromePageBridge(socket_path=socket_dir / "bridge.sock", timeout=0.02) as bridge:
        with pytest.raises(BridgeDisconnectedError, match="extension.*native host"):
            bridge.snapshot()


def test_bridge_times_out_when_relay_does_not_respond(socket_dir: Path) -> None:
    socket_path = socket_dir / "bridge.sock"
    connected = threading.Event()

    def silent_relay() -> None:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.connect(str(socket_path))
        connected.set()
        with connection:
            read_message(connection.makefile("rb", buffering=0))
            threading.Event().wait(0.2)

    with ChromePageBridge(socket_path=socket_path, timeout=0.02) as bridge:
        relay = threading.Thread(target=silent_relay)
        relay.start()
        assert connected.wait(1.0)
        with pytest.raises(BridgeTimeoutError, match="did not respond"):
            bridge.snapshot()
        relay.join(timeout=1.0)


def test_bridge_removes_owned_stale_socket(socket_dir: Path) -> None:
    socket_path = socket_dir / "bridge.sock"
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(socket_path))
    stale.close()

    with ChromePageBridge(socket_path=socket_path):
        assert socket_path.exists()


def test_bridge_refuses_to_replace_regular_file(socket_dir: Path) -> None:
    socket_path = socket_dir / "bridge.sock"
    socket_path.write_text("keep me", encoding="utf-8")
    bridge = ChromePageBridge(socket_path=socket_path)

    with pytest.raises(BridgeError, match="unsafe socket path"):
        bridge.start()

    assert socket_path.read_text(encoding="utf-8") == "keep me"
