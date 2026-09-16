#!/usr/bin/env python3
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import inspect
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor import hermes_deals_runner_smoke_install_broker as broker
from deploy_executor.hermes_deals_runner_smoke_install import (
    APPLY_RECEIPT_SCHEMA,
    INSTALL_TARGET_ALIAS,
    LIVE_GATE_ID,
    OPERATION_ID,
    SOURCE_REPOSITORY,
    SOURCE_SHA,
    ApplyReceipt,
)
from deploy_executor.hermes_deals_runner_smoke_install_runtime import RunnerSmokeInstallRuntimeError

CLIENT_PATH = ROOT / "scripts" / "send-hermes-deals-runner-smoke-install-request.py"
SPEC = importlib.util.spec_from_file_location("runner_smoke_request_client", CLIENT_PATH)
assert SPEC is not None and SPEC.loader is not None
client = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = client
SPEC.loader.exec_module(client)


class FakeRuntime:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[int] = []

    def execute(self, issue_number: int) -> ApplyReceipt:
        self.calls.append(issue_number)
        if self.fail:
            raise RunnerSmokeInstallRuntimeError("fail")
        return ApplyReceipt(
            schema=APPLY_RECEIPT_SCHEMA,
            result="ALREADY_EXACT_NO_MUTATION",
            authorization_issue_number=issue_number,
            operation_id=OPERATION_ID,
            live_gate_id=LIVE_GATE_ID,
            target_alias=INSTALL_TARGET_ALIAS,
            source_repository=SOURCE_REPOSITORY,
            source_sha=SOURCE_SHA,
            rpi5_main_sha="1" * 40,
            mutations_started=False,
            authorization_consumed=False,
        )


class FakeSocket:
    def __init__(self, response: bytes = b"", *, connect_error: OSError | None = None) -> None:
        self.response = response
        self.connect_error = connect_error
        self.connected_path: str | None = None
        self.sent: list[bytes] = []
        self.timeout: float | None = None
        self.shutdown_how: int | None = None
        self.offset = 0

    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): return None
    def settimeout(self, value: float): self.timeout = value
    def connect(self, path: str):
        self.connected_path = path
        if self.connect_error is not None:
            raise self.connect_error
    def sendall(self, raw: bytes): self.sent.append(raw)
    def shutdown(self, how: int): self.shutdown_how = how
    def recv(self, size: int) -> bytes:
        chunk = self.response[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


def request(issue: int = 30) -> bytes:
    return (
        json.dumps(
            {"authorization_issue_number": issue, "schema": broker.REQUEST_SCHEMA},
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"
    ).encode()


def receipt(issue: int = 30) -> bytes:
    value = {
        "schema": broker.FAILURE_SCHEMA,
        "result": "FAIL_CLOSED",
        "authorization_issue_number": issue,
        "safe_stage": "runtime_composition",
        "authorization_reuse_forbidden": False,
        "mutation_state": "NOT_STARTED",
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


class RunnerSmokeInstallBrokerTests(unittest.TestCase):
    def test_request_is_exact_identity_only_frame(self) -> None:
        self.assertEqual(broker.parse_broker_request(request(30)), 30)
        self.assertEqual(set(inspect.signature(broker.execute_broker_request).parameters), {"raw"})
        self.assertEqual(client.build_request_frame(30), request(30))
        self.assertEqual(client.SOCKET_PATH, broker.SOCKET_PATH)
        self.assertEqual(client.REQUEST_MAX_BYTES, broker.REQUEST_MAX_BYTES)

    def test_invalid_requests_fail_closed(self) -> None:
        invalid = [
            b"", b"{}", b"{}\n\n", b'{"schema":"x","authorization_issue_number":30}\n',
            b'{"schema":"rozkalns.hermes-deals.runner-smoke-install-request.v1","authorization_issue_number":0}\n',
            b'{"schema":"rozkalns.hermes-deals.runner-smoke-install-request.v1","authorization_issue_number":30,"command":"id"}\n',
            b'{"schema":"rozkalns.hermes-deals.runner-smoke-install-request.v1","schema":"rozkalns.hermes-deals.runner-smoke-install-request.v1","authorization_issue_number":30}\n',
            b"x" * (broker.REQUEST_MAX_BYTES + 1),
        ]
        for raw in invalid:
            with self.subTest(raw=raw[:40]):
                with self.assertRaises(broker.RunnerSmokeInstallBrokerError):
                    broker.parse_broker_request(raw)

    def test_broker_builds_runtime_internally_and_passes_only_issue_number(self) -> None:
        runtime = FakeRuntime()
        with mock.patch.object(broker, "build_runner_smoke_install_runtime", return_value=runtime):
            value = broker.execute_broker_request(request(30))
        self.assertEqual(runtime.calls, [30])
        self.assertEqual(value["schema"], APPLY_RECEIPT_SCHEMA)
        self.assertEqual(value["authorization_issue_number"], 30)

    def test_runtime_composition_failure_is_pre_mutation_reusable_false(self) -> None:
        with mock.patch.object(
            broker, "build_runner_smoke_install_runtime",
            side_effect=RunnerSmokeInstallRuntimeError("fail"),
        ):
            value = broker.execute_broker_request(request(30))
        self.assertEqual(value["safe_stage"], "runtime_composition")
        self.assertFalse(value["authorization_reuse_forbidden"])
        self.assertEqual(value["mutation_state"], "NOT_STARTED")

    def test_execution_failure_forbids_reuse(self) -> None:
        with mock.patch.object(broker, "build_runner_smoke_install_runtime", return_value=FakeRuntime(fail=True)):
            value = broker.execute_broker_request(request(30))
        self.assertEqual(value["safe_stage"], "install_execution")
        self.assertTrue(value["authorization_reuse_forbidden"])
        self.assertEqual(value["mutation_state"], "UNKNOWN_FAIL_CLOSED")

    def test_unprivileged_client_uses_one_fixed_socket_and_no_retry(self) -> None:
        fake = FakeSocket(receipt())
        with mock.patch.object(client.socket, "socket", return_value=fake) as factory:
            value = client.send_request_once(30)
        factory.assert_called_once_with(socket.AF_UNIX, socket.SOCK_STREAM)
        self.assertEqual(fake.connected_path, broker.SOCKET_PATH)
        self.assertEqual(fake.sent, [request(30)])
        self.assertEqual(fake.shutdown_how, socket.SHUT_WR)
        self.assertIn('"authorization_issue_number":30', value)

        failed = FakeSocket(connect_error=PermissionError("denied"))
        with mock.patch.object(client.socket, "socket", return_value=failed):
            with self.assertRaises(client.RequestOperatorError) as ctx:
                client.send_request_once(30)
        self.assertFalse(ctx.exception.connection_started)
        self.assertEqual(failed.sent, [])

    def test_client_has_no_root_gate_or_generic_authority(self) -> None:
        source = CLIENT_PATH.read_text()
        for prohibited in ("geteuid", "sudo", "subprocess", "Popen", "shell=True", "--socket", "--command"):
            self.assertNotIn(prohibited, source)
        self.assertNotIn("os.", source)

    def test_systemd_source_is_fixed_and_activation_remains_disabled(self) -> None:
        socket_unit = (ROOT / "ops/systemd/rozkalns-hermes-deals-runner-smoke-install.socket").read_text()
        service_unit = (ROOT / "ops/systemd/rozkalns-hermes-deals-runner-smoke-install@.service").read_text()
        self.assertIn(f"ListenStream={broker.SOCKET_PATH}", socket_unit)
        self.assertIn("SocketMode=0600", socket_unit)
        self.assertIn("SocketUser=andris", socket_unit)
        self.assertIn("Accept=yes", socket_unit)
        self.assertIn(f"ExecStart={broker.BROKER_INSTALL_PATH}", service_unit)
        self.assertIn("StandardInput=socket", service_unit)
        self.assertIn("StandardOutput=socket", service_unit)
        self.assertIn("NoNewPrivileges=true", service_unit)
        self.assertNotIn("/bin/sh", service_unit)
        self.assertNotIn("/bin/bash", service_unit)
        ready = broker.source_readiness()
        self.assertEqual(ready["caller_authority"], ("authorization_issue_number",))
        self.assertFalse(ready["generic_sudo_allowed"])
        self.assertTrue(ready["rdc_no_new_privileges_must_remain"])
        self.assertTrue(ready["root_owned_release_layout_required"])
        self.assertFalse(ready["runtime_activation_enabled"])
        self.assertFalse(ready["systemd_socket_installed"])
        self.assertFalse(ready["source_merge_authorizes_live"])


if __name__ == "__main__":
    unittest.main()
