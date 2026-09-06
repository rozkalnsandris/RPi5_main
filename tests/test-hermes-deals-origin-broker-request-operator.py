#!/usr/bin/env python3
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.hermes_deals_origin_dispatch_request import SCHEMA as SERVER_REQUEST_SCHEMA
from deploy_executor.hermes_deals_origin_privileged_broker import (
    BROKER_REQUEST_MAX_BYTES,
    BROKER_SOCKET_PATH,
    parse_broker_transport_request,
)
from deploy_executor.hermes_deals_origin_broker_composition import BROKER_DISPATCH_RECEIPT_SCHEMA

OPERATOR = ROOT / "scripts" / "send-hermes-deals-origin-broker-request.py"
SPEC = importlib.util.spec_from_file_location("hermes_origin_request_operator", OPERATOR)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeSocket:
    def __init__(self, response: bytes = b"", *, connect_error: OSError | None = None) -> None:
        self.response = response
        self.connect_error = connect_error
        self.timeout: float | None = None
        self.connected_path: str | None = None
        self.connect_calls = 0
        self.sent: list[bytes] = []
        self.shutdown_how: int | None = None
        self.closed = False
        self._offset = 0

    def __enter__(self) -> "FakeSocket":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.closed = True

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def connect(self, path: str) -> None:
        self.connect_calls += 1
        self.connected_path = path
        if self.connect_error is not None:
            raise self.connect_error

    def sendall(self, raw: bytes) -> None:
        self.sent.append(raw)

    def shutdown(self, how: int) -> None:
        self.shutdown_how = how

    def recv(self, size: int) -> bytes:
        if self._offset >= len(self.response):
            return b""
        chunk = self.response[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


def receipt_bytes(issue_number: int = 11, *, schema: str = BROKER_DISPATCH_RECEIPT_SCHEMA) -> bytes:
    return (
        json.dumps(
            {
                "schema": schema,
                "result": "FAIL_CLOSED",
                "authorization_issue_number": issue_number,
                "safe_stage": "canonical_prepare",
                "replay_consume_attempted": False,
                "durable_replay_consumed": False,
                "authorization_reuse_forbidden": False,
                "helper_execution_attempted": False,
                "production_mutation_started": False,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


class HermesOriginBrokerRequestOperatorTests(unittest.TestCase):
    def test_source_fixed_transport_contract_matches_server(self) -> None:
        self.assertEqual(MODULE.REQUEST_SCHEMA, SERVER_REQUEST_SCHEMA)
        self.assertEqual(MODULE.RECEIPT_SCHEMA, BROKER_DISPATCH_RECEIPT_SCHEMA)
        self.assertEqual(MODULE.SOCKET_PATH, BROKER_SOCKET_PATH)
        self.assertEqual(MODULE.REQUEST_MAX_BYTES, BROKER_REQUEST_MAX_BYTES)

    def test_generated_frame_is_exactly_one_server_accepted_frame(self) -> None:
        frame = MODULE.build_request_frame(11)
        parsed = parse_broker_transport_request(frame)
        self.assertEqual(parsed.authorization_issue_number, 11)
        self.assertEqual(frame.count(b"\n"), 1)
        self.assertTrue(frame.endswith(b"\n"))
        self.assertNotIn(b"\r", frame)
        self.assertNotIn(b"\x00", frame)
        self.assertLessEqual(len(frame), BROKER_REQUEST_MAX_BYTES)
        self.assertEqual(
            frame,
            b'{"authorization_issue_number":11,"schema":"rozkalns.hermes-deals.origin-dispatch-request.v1"}\n',
        )

    def test_frame_rejects_invalid_issue_numbers(self) -> None:
        for value in (True, 0, -1, MODULE.MAX_ISSUE_NUMBER + 1):
            with self.subTest(value=value):
                with self.assertRaises(MODULE.RequestOperatorError):
                    MODULE.build_request_frame(value)

    def test_cli_issue_number_is_canonical_decimal_only(self) -> None:
        for text in ("0", "00", "+11", "011", "-1", "1.0", "abc"):
            with self.subTest(text=text):
                with self.assertRaises(MODULE.argparse.ArgumentTypeError):
                    MODULE._issue_number(text)
        self.assertEqual(MODULE._issue_number("11"), 11)

    def test_send_once_uses_fixed_socket_and_exact_frame(self) -> None:
        fake = FakeSocket(receipt_bytes())
        with mock.patch.object(MODULE.socket, "socket", return_value=fake) as factory:
            receipt = MODULE.send_request_once(11)
        factory.assert_called_once_with(socket.AF_UNIX, socket.SOCK_STREAM)
        self.assertEqual(fake.timeout, MODULE.SOCKET_TIMEOUT_SECONDS)
        self.assertEqual(fake.connected_path, BROKER_SOCKET_PATH)
        self.assertEqual(fake.connect_calls, 1)
        self.assertEqual(fake.sent, [MODULE.build_request_frame(11)])
        self.assertEqual(fake.shutdown_how, socket.SHUT_WR)
        self.assertTrue(fake.closed)
        self.assertIn('"authorization_issue_number":11', receipt)

    def test_connect_failure_is_one_attempt_and_pre_connection(self) -> None:
        fake = FakeSocket(connect_error=PermissionError("denied"))
        with mock.patch.object(MODULE.socket, "socket", return_value=fake):
            with self.assertRaises(MODULE.RequestOperatorError) as ctx:
                MODULE.send_request_once(11)
        self.assertFalse(ctx.exception.connection_started)
        self.assertEqual(fake.connect_calls, 1)
        self.assertEqual(fake.sent, [])

    def test_invalid_receipt_is_post_connection_fail_closed(self) -> None:
        fake = FakeSocket(receipt_bytes(issue_number=12))
        with mock.patch.object(MODULE.socket, "socket", return_value=fake):
            with self.assertRaises(MODULE.RequestOperatorError) as ctx:
                MODULE.send_request_once(11)
        self.assertTrue(ctx.exception.connection_started)
        self.assertEqual(fake.connect_calls, 1)
        self.assertEqual(len(fake.sent), 1)

    def test_oversized_receipt_is_bounded_after_one_connection(self) -> None:
        fake = FakeSocket(b"x" * (MODULE.RECEIPT_MAX_BYTES + 1))
        with mock.patch.object(MODULE.socket, "socket", return_value=fake):
            with self.assertRaises(MODULE.RequestOperatorError) as ctx:
                MODULE.send_request_once(11)
        self.assertTrue(ctx.exception.connection_started)
        self.assertEqual(fake.connect_calls, 1)
        self.assertEqual(len(fake.sent), 1)

    def test_root_gate_happens_before_socket_creation(self) -> None:
        stderr = io.StringIO()
        with (
            mock.patch.object(MODULE.os, "geteuid", return_value=1000),
            mock.patch.object(MODULE.socket, "socket") as factory,
            redirect_stderr(stderr),
        ):
            rc = MODULE.main(["11"])
        self.assertEqual(rc, 77)
        factory.assert_not_called()
        self.assertIn("root_required", stderr.getvalue())

    def test_extra_cli_authority_is_rejected(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as ctx:
                MODULE.main(["11", "--socket", "/tmp/other.sock"])
        self.assertEqual(ctx.exception.code, 2)

    def test_successful_main_prints_only_validated_receipt(self) -> None:
        fake = FakeSocket(receipt_bytes())
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(MODULE.os, "geteuid", return_value=0),
            mock.patch.object(MODULE.socket, "socket", return_value=fake),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            rc = MODULE.main(["11"])
        self.assertEqual(rc, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue().count("\n"), 1)
        self.assertIn('"result":"FAIL_CLOSED"', stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
