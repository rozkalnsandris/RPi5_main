#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import socket
import sys
from typing import Any, Sequence

REQUEST_SCHEMA = "rozkalns.hermes-deals.runner-smoke-install-request.v1"
APPLY_RECEIPT_SCHEMA = "rozkalns.hermes-deals.runner-smoke-install-apply-receipt.v1"
FAILURE_SCHEMA = "rozkalns.hermes-deals.runner-smoke-install-runtime-failure.v1"
SOCKET_PATH = "/run/rozkalns-hermes-deals-runner-smoke-install/request.sock"
REQUEST_MAX_BYTES = 192
RECEIPT_MAX_BYTES = 4096
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
    if type(authorization_issue_number) is not int or not 1 <= authorization_issue_number <= MAX_ISSUE_NUMBER:
        raise RequestOperatorError("authorization_issue_number is invalid")
    frame = (
        json.dumps(
            {"schema": REQUEST_SCHEMA, "authorization_issue_number": authorization_issue_number},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    if len(frame) > REQUEST_MAX_BYTES or frame.count(b"\n") != 1 or not frame.endswith(b"\n"):
        raise RequestOperatorError("request framing invariant failed")
    return frame


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RequestOperatorError("broker receipt contains duplicate fields", connection_started=True)
        result[key] = value
    return result


def _validate_receipt(raw: bytes, issue_number: int) -> str:
    if not raw or len(raw) > RECEIPT_MAX_BYTES or not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise RequestOperatorError("broker receipt framing is invalid", connection_started=True)
    if b"\x00" in raw or b"\r" in raw:
        raise RequestOperatorError("broker receipt contains forbidden framing", connection_started=True)
    try:
        value = json.loads(raw[:-1].decode("utf-8", "strict"), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RequestOperatorError("broker receipt is not strict JSON", connection_started=True) from exc
    if type(value) is not dict:
        raise RequestOperatorError("broker receipt must be an object", connection_started=True)
    if value.get("schema") not in {APPLY_RECEIPT_SCHEMA, FAILURE_SCHEMA}:
        raise RequestOperatorError("broker receipt schema mismatch", connection_started=True)
    if value.get("authorization_issue_number") != issue_number:
        raise RequestOperatorError("broker receipt authorization identity mismatch", connection_started=True)
    if type(value.get("result")) is not str:
        raise RequestOperatorError("broker receipt result is missing", connection_started=True)
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def send_request_once(issue_number: int) -> str:
    frame = build_request_frame(issue_number)
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
        raise RequestOperatorError("broker socket request failed", connection_started=connected) from exc
    raw = b"".join(chunks)
    if len(raw) > RECEIPT_MAX_BYTES:
        raise RequestOperatorError("broker receipt exceeds byte limit", connection_started=True)
    return _validate_receipt(raw, issue_number)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send one identity-only runner-smoke install request.")
    parser.add_argument("authorization_issue_number", type=_issue_number)
    args = parser.parse_args(argv)
    try:
        receipt = send_request_once(args.authorization_issue_number)
    except RequestOperatorError as exc:
        started = "true" if exc.connection_started else "false"
        retry_forbidden = "true" if exc.connection_started else "false"
        print(
            "RUNNER_SMOKE_INSTALL_REQUEST=FAIL_CLOSED "
            f"connection_started={started} retry_forbidden={retry_forbidden}",
            file=sys.stderr,
        )
        return 71
    print(receipt)
    return 71 if '"result":"FAIL_CLOSED"' in receipt else 0


if __name__ == "__main__":
    raise SystemExit(main())
