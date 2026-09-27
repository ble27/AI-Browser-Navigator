"""Strict messages and framing for the Chrome Native Messaging bridge."""

from __future__ import annotations

import json
import struct
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, BinaryIO

from gesture_control.backends.base import FocusedPageFieldAction

MAX_MESSAGE_BYTES = 1_048_576
MAX_REQUEST_ID_LENGTH = 128
MAX_TARGET_ID_LENGTH = 200
MAX_TEXT_LENGTH = 10_000
MAX_ERROR_LENGTH = 1_000


class ProtocolError(ValueError):
    """Raised when a bridge message is malformed or outside protocol bounds."""


class Operation(StrEnum):
    """Operations implemented by the page bridge extension."""

    SNAPSHOT = "snapshot"
    CLICK = "click"
    FOCUS = "focus"
    TYPE = "type"
    SUBMIT = "submit"
    EDIT_FOCUSED_FIELD = "edit_focused_field"


def validate_request(message: object) -> dict[str, object]:
    """Validate and normalize an app-to-extension request.

    Args:
        message: Decoded JSON value.

    Returns:
        A new request dictionary containing only protocol fields.

    Raises:
        ProtocolError: If the request has wrong, missing, or extra fields.
    """
    request = _plain_object(message, "Request")
    request_id = _bounded_string(request.get("request_id"), "request_id", MAX_REQUEST_ID_LENGTH)
    raw_operation = request.get("operation")
    if not isinstance(raw_operation, str):
        raise ProtocolError("operation is unsupported")
    try:
        operation = Operation(raw_operation)
    except ValueError as exc:
        raise ProtocolError("operation is unsupported") from exc

    expected = {"request_id", "operation"}
    normalized: dict[str, object] = {"request_id": request_id, "operation": operation.value}
    if operation is Operation.EDIT_FOCUSED_FIELD:
        expected.add("action")
        raw_action = request.get("action")
        if not isinstance(raw_action, str):
            raise ProtocolError("action is unsupported")
        try:
            action = FocusedPageFieldAction(raw_action)
        except ValueError as exc:
            raise ProtocolError("action is unsupported") from exc
        normalized["action"] = action.value
    elif operation is not Operation.SNAPSHOT:
        expected.add("target_id")
        normalized["target_id"] = _bounded_string(
            request.get("target_id"), "target_id", MAX_TARGET_ID_LENGTH
        )
    if operation in {Operation.TYPE, Operation.SUBMIT}:
        expected.add("text")
        normalized["text"] = _bounded_string(
            request.get("text"), "text", MAX_TEXT_LENGTH, allow_empty=True
        )
    _reject_extra_fields(request, expected, "Request")
    return normalized


def validate_response(message: object) -> dict[str, object]:
    """Validate and normalize an extension-to-app response.

    Args:
        message: Decoded JSON value.

    Returns:
        A new response dictionary containing only protocol fields.

    Raises:
        ProtocolError: If the response has wrong, missing, or extra fields.
    """
    response = _plain_object(message, "Response")
    request_id = _bounded_string(response.get("request_id"), "request_id", MAX_REQUEST_ID_LENGTH)
    ok = response.get("ok")
    if not isinstance(ok, bool):
        raise ProtocolError("ok must be a boolean")
    if ok:
        _reject_extra_fields(response, {"request_id", "ok", "result"}, "Response")
        result = _plain_object(response.get("result"), "result")
        return {"request_id": request_id, "ok": True, "result": result}
    _reject_extra_fields(response, {"request_id", "ok", "error"}, "Response")
    error = _bounded_string(response.get("error"), "error", MAX_ERROR_LENGTH)
    return {"request_id": request_id, "ok": False, "error": error}


def encode_message(message: Mapping[str, object]) -> bytes:
    """Encode one JSON object with a little-endian native-message header.

    Args:
        message: JSON-compatible mapping to encode.

    Returns:
        Four-byte length prefix followed by compact UTF-8 JSON.

    Raises:
        ProtocolError: If JSON encoding fails or the payload exceeds the bound.
    """
    try:
        payload = json.dumps(
            dict(message),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError("Message is not valid JSON data") from exc
    if not payload or len(payload) > MAX_MESSAGE_BYTES:
        raise ProtocolError(f"Message exceeds the {MAX_MESSAGE_BYTES}-byte limit")
    return struct.pack("<I", len(payload)) + payload


def read_message(stream: BinaryIO) -> dict[str, Any] | None:
    """Read and decode one framed JSON object.

    A clean EOF before a new header returns ``None``. EOF after any header or
    payload byte is malformed and raises instead.

    Args:
        stream: Binary stream implementing ``read``.

    Returns:
        A decoded JSON object, or ``None`` at clean EOF.

    Raises:
        ProtocolError: If framing, UTF-8, JSON, or the root value is invalid.
    """
    header = _read_exact(stream, 4, allow_clean_eof=True)
    if header is None:
        return None
    (length,) = struct.unpack("<I", header)
    if length == 0 or length > MAX_MESSAGE_BYTES:
        raise ProtocolError(f"Invalid native-message length: {length}")
    payload = _read_exact(stream, length, allow_clean_eof=False)
    assert payload is not None
    try:
        decoded = json.loads(
            payload.decode("utf-8"),
            parse_constant=lambda value: (_raise_invalid_constant(value)),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("Message payload is not valid UTF-8 JSON") from exc
    return _plain_object(decoded, "Message")


def write_message(stream: BinaryIO, message: Mapping[str, object]) -> None:
    """Write and flush one framed JSON object.

    Args:
        stream: Binary stream implementing ``write`` and ``flush``.
        message: JSON-compatible mapping to encode.
    """
    stream.write(encode_message(message))
    stream.flush()


def _read_exact(stream: BinaryIO, size: int, *, allow_clean_eof: bool) -> bytes | None:
    """Read exactly ``size`` bytes, accounting for short stream reads."""
    chunks = bytearray()
    while len(chunks) < size:
        chunk = stream.read(size - len(chunks))
        if not chunk:
            if allow_clean_eof and not chunks:
                return None
            raise ProtocolError("Unexpected EOF inside native message")
        chunks.extend(chunk)
    return bytes(chunks)


def _plain_object(value: object, field: str) -> dict[str, Any]:
    """Require a JSON object with string keys."""
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ProtocolError(f"{field} must be an object")
    return value


def _bounded_string(value: object, field: str, limit: int, *, allow_empty: bool = False) -> str:
    """Require a string within the field's protocol bound."""
    if not isinstance(value, str) or (not value and not allow_empty) or len(value) > limit:
        qualifier = "a bounded string" if allow_empty else "a non-empty bounded string"
        raise ProtocolError(f"{field} must be {qualifier}")
    return value


def _reject_extra_fields(
    message: Mapping[str, object], expected: set[str], message_name: str
) -> None:
    """Reject fields outside the fixed protocol schema."""
    extras = set(message) - expected
    missing = expected - set(message)
    if missing:
        raise ProtocolError(f"{message_name} is missing fields: {', '.join(sorted(missing))}")
    if extras:
        raise ProtocolError(f"{message_name} contains unsupported fields")


def _raise_invalid_constant(value: str) -> Any:
    """Reject non-standard JSON constants such as NaN and Infinity."""
    raise ProtocolError(f"Invalid JSON constant: {value}")
