from __future__ import annotations

import io
import json
import struct

import pytest
from gesture_control.browser.native_protocol import (
    MAX_MESSAGE_BYTES,
    ProtocolError,
    encode_message,
    read_message,
    validate_request,
    validate_response,
    write_message,
)


def test_message_round_trip_uses_little_endian_framing() -> None:
    message = {"request_id": "r1", "operation": "snapshot"}

    framed = encode_message(message)

    assert struct.unpack("<I", framed[:4]) == (len(framed) - 4,)
    assert read_message(io.BytesIO(framed)) == message


def test_write_message_flushes_stream() -> None:
    class FlushTrackingStream(io.BytesIO):
        flushed = False

        def flush(self) -> None:
            self.flushed = True
            super().flush()

    stream = FlushTrackingStream()

    write_message(stream, {"ok": True})

    assert stream.flushed


@pytest.mark.parametrize(
    "message",
    [
        {},
        {"request_id": "r1", "operation": "evaluate", "script": "alert(1)"},
        {"request_id": "r1", "operation": "click"},
        {"request_id": "r1", "operation": "snapshot", "extra": True},
        {"request_id": "r1", "operation": "type", "target_id": "e1"},
        {
            "request_id": "r1",
            "operation": "type",
            "target_id": "e1",
            "text": "x" * 10_001,
        },
    ],
)
def test_validate_request_rejects_malformed_or_unbounded_values(
    message: dict[str, object],
) -> None:
    with pytest.raises(ProtocolError):
        validate_request(message)


def test_validate_request_accepts_only_fixed_operation_payloads() -> None:
    assert validate_request(
        {"request_id": "r1", "operation": "submit", "target_id": "opaque", "text": ""}
    ) == {
        "request_id": "r1",
        "operation": "submit",
        "target_id": "opaque",
        "text": "",
    }


@pytest.mark.parametrize(
    "response",
    [
        {"request_id": "r1", "ok": "yes", "result": {}},
        {"request_id": "r1", "ok": True},
        {"request_id": "r1", "ok": False, "error": ""},
        {"request_id": "r1", "ok": True, "result": {}, "extra": 1},
    ],
)
def test_validate_response_rejects_malformed_values(response: dict[str, object]) -> None:
    with pytest.raises(ProtocolError):
        validate_response(response)


def test_read_message_returns_none_only_for_clean_eof() -> None:
    assert read_message(io.BytesIO()) is None

    with pytest.raises(ProtocolError, match="Unexpected EOF"):
        read_message(io.BytesIO(b"\x05\x00"))

    with pytest.raises(ProtocolError, match="Unexpected EOF"):
        read_message(io.BytesIO(struct.pack("<I", 5) + b"{}"))


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"not json",
        b"[]",
        b'{"number":NaN}',
        b"\xff",
    ],
)
def test_read_message_rejects_malformed_json_payloads(payload: bytes) -> None:
    framed = struct.pack("<I", len(payload)) + payload

    with pytest.raises(ProtocolError):
        read_message(io.BytesIO(framed))


def test_read_message_rejects_oversized_length_before_reading_payload() -> None:
    framed = struct.pack("<I", MAX_MESSAGE_BYTES + 1)

    with pytest.raises(ProtocolError, match="length"):
        read_message(io.BytesIO(framed))


def test_encode_message_rejects_oversized_payload() -> None:
    with pytest.raises(ProtocolError, match="exceeds"):
        encode_message({"value": "x" * MAX_MESSAGE_BYTES})


def test_framed_payload_is_compact_utf8_json() -> None:
    framed = encode_message({"name": "café"})
    payload = framed[4:]

    assert json.loads(payload) == {"name": "café"}
    assert b"caf\xc3\xa9" in payload
