#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_operator_v10_successor_preflight as preflight

SOCKET_PATH = "/run/rozkalns-weather-operator-v10-successor-preflight/request.sock"
SOCKET_TIMEOUT_SECONDS = 5.0


def request() -> dict[str, object]:
    payload = (json.dumps(
        {"schema": preflight.REQUEST_SCHEMA, "operation": preflight.OPERATION},
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n").encode("utf-8")
    if len(payload) > preflight.REQUEST_MAX_BYTES:
        raise RuntimeError("fixed preflight request exceeds protocol bound")
    response = bytearray()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(SOCKET_TIMEOUT_SECONDS)
        client.connect(SOCKET_PATH)
        client.sendall(payload)
        client.shutdown(socket.SHUT_WR)
        while len(response) <= preflight.RECEIPT_MAX_BYTES:
            chunk = client.recv(min(4096, preflight.RECEIPT_MAX_BYTES + 1 - len(response)))
            if not chunk:
                break
            response.extend(chunk)
    if not response or len(response) > preflight.RECEIPT_MAX_BYTES:
        raise RuntimeError("preflight response size is invalid")
    try:
        value = json.loads(bytes(response).decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("preflight response is malformed") from exc
    return preflight.validate_receipt(value)


def main() -> int:
    if len(sys.argv) != 1:
        return 64
    try:
        receipt = request()
    except (OSError, RuntimeError, preflight.WeatherV10SuccessorPreflightError):
        receipt = preflight.failure_receipt()
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0 if receipt.get("result") == "PASS" else 78


if __name__ == "__main__":
    raise SystemExit(main())
