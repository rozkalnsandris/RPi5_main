#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from typing import Any, Sequence

REQUEST_SCHEMA = "rozkalns.hermes-deals.origin-dispatch-request.v1"
RECEIPT_SCHEMA = "rozkalns.hermes-deals.origin-broker-dispatch-receipt.v1"
SOCKET_PATH = "/run/rozkalns-hermes-deals-origin-broker/request.sock"
REQUEST_MAX_BYTES = 256
RECEIPT_MAX_BYTES = 8192
SOCKET_TIMEOUT_SECONDS = 65.0
MAX_ISSUE_NUMBER = 2_147_483_647


class RequestOperatorError(RuntimeError):
    def __init__(self, message: str, *, connection_started: bool = False) -> None:
        super().__init__(message)
        self.connection_started = connection_started


def _issue_number(text: str) -> int:
    if not text.isascii() or not text.isdigit() or text.startswith("0"):
        raise argparse.ArgumentTypeError("authorization_issue_number must be canonical decimal")
    value = int(text)
    if not 1 <= value <= MAX_ISSUE_NUMBER:
        raise argparse.ArgumentTypeError("authorization_issue_number is outside the supported range")
    return value


def build_request_frame(authorization_issue_number: int) -> bytes:
    if type(authorization_issue_number) is not int or not (
        1 <= authorization_issue_number <= MAX_ISSUE_NUMBER
    ):
        raise RequestOperatorError("authorization_issue_number is invalid")
    payload = {
        "schema": REQUEST_SCHEMA,
        "authorization_issue_number": authorization_issue_number,
    }
    frame = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    if len(frame) > REQUEST_MAX_BYTES:
        raise RequestOperatorError("broker request exceeds the source-fixed byte limit")
    if not frame.endswith(b"\n") or frame.count(b"\n") != 1:
        raise RequestOperatorError("broker request framing invariant failed")
    if b"\r" in frame or b"\x00" in frame:
        raise RequestOperatorError("broker request contains forbidden framing bytes")
    return frame


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RequestOperatorError("broker receipt contains duplicate JSON fields", connection_started=True)
        result[key] = value
    return result


def _validate_receipt(raw: bytes, authorization_issue_number: int) -> str:
    if not raw or len(raw) > RECEIPT_MAX_BYTES:
        raise RequestOperatorError("broker receipt size is invalid", connection_started=True)
    if b"\x00" in raw or b"\r" in raw:
        raise RequestOperatorError("broker receipt contains forbidden framing", connection_started=True)
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise RequestOperatorError("broker receipt is not one newline-terminated frame", connection_started=True)
    try:
        decoded = raw[:-1].decode("utf-8", "strict")
        value = json.loads(decoded, object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RequestOperatorError("broker receipt is not strict UTF-8 JSON", connection_started=True) from exc
    if type(value) is not dict:
        raise RequestOperatorError("broker receipt must be a JSON object", connection_started=True)
    if value.get("schema") != RECEIPT_SCHEMA:
        raise RequestOperatorError("broker receipt schema mismatch", connection_started=True)
    if value.get("authorization_issue_number") != authorization_issue_number:
        raise RequestOperatorError("broker receipt authorization identity mismatch", connection_started=True)
    if type(value.get("result")) is not str:
        raise RequestOperatorError("broker receipt result is missing", connection_started=True)
    return decoded


def send_request_once(authorization_issue_number: int) -> str:
    frame = build_request_frame(authorization_issue_number)
    connected = False
    chunks: list[bytes] = []
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(SOCKET_TIMEOUT_SECONDS)
            client.connect(SOCKET_PATH)
            connected = True
            client.sendall(frame)
            client.shutdown(socket.SHUT_WR)
            remaining = RECEIPT_MAX_BYTES + 1
            while remaining > 0:
                chunk = client.recv(min(4096, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
    except OSError as exc:
        raise RequestOperatorError(
            "broker socket request failed",
            connection_started=connected,
        ) from exc
    raw = b"".join(chunks)
    if len(raw) > RECEIPT_MAX_BYTES:
        raise RequestOperatorError("broker receipt exceeds the source-fixed byte limit", connection_started=True)
    return _validate_receipt(raw, authorization_issue_number)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send exactly one identity-only request to the Hermes origin broker."
    )
    parser.add_argument("authorization_issue_number", type=_issue_number)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if os.geteuid() != 0:
        print(
            "HERMES_ORIGIN_REQUEST_OPERATOR=REJECTED reason=root_required",
            file=sys.stderr,
        )
        return 77
    try:
        receipt = send_request_once(args.authorization_issue_number)
    except RequestOperatorError as exc:
        started = "true" if exc.connection_started else "false"
        retry_forbidden = started
        print(
            "HERMES_ORIGIN_REQUEST_OPERATOR=FAIL_CLOSED "
            f"connection_started={started} retry_forbidden={retry_forbidden} "
            "reason=request_failed",
            file=sys.stderr,
        )
        return 71
    print(receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
