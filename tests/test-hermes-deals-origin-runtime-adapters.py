from __future__ import annotations

from contextlib import ExitStack
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import inspect
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor import hermes_deals_origin_runtime_adapters as runtime  # noqa: E402
from deploy_executor.protocol import (  # noqa: E402
    AUTHORIZATION_REPOSITORY,
    AUTHORIZATION_REPOSITORY_ID,
    AcceptedAuthorization,
)
from deploy_executor.state import StateStore  # noqa: E402
from deploy_executor.transport import InstallationToken  # noqa: E402

SOURCE_SHA = subprocess.check_output(
    ("git", "rev-parse", "HEAD"), cwd=ROOT, text=True
).strip()
REQUEST_ID = "123e4567-e89b-42d3-a456-426614174000"


def _accepted(**updates: object) -> AcceptedAuthorization:
    value = AcceptedAuthorization(
        repository_id=AUTHORIZATION_REPOSITORY_ID,
        repository_full_name=AUTHORIZATION_REPOSITORY,
        issue_id=5017,
        issue_number=17,
        request_id=REQUEST_ID,
        created_at=datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc),
        target_alias="hermes-deals-origin-path-audit",
        canonical_payload_json="{}",
        canonical_payload_sha256="1" * 64,
        raw_body_sha256="2" * 64,
        performed_via_github_app_id=None,
        performed_via_github_app_slug=None,
    )
    return replace(value, **updates)


def _git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


class DurableReplayAuthorityTests(unittest.TestCase):
    def test_availability_is_read_only_then_consume_is_one_shot(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.sqlite3"
            with StateStore(db, bootstrap=True):
                pass
            os.chmod(db, 0o600)
            before = hashlib.sha256(db.read_bytes()).hexdigest()
            accepted = _accepted()
            with (
                patch.object(runtime, "STATE_DB_PATH", db),
                patch.object(runtime, "ROOT_UID", os.geteuid()),
                patch.object(runtime, "ROOT_GID", os.getegid()),
            ):
                authority = runtime.ConcreteDurableHermesOriginReplayAuthority()
                self.assertTrue(authority.is_available(accepted))
                self.assertTrue(authority.is_available(accepted))
                self.assertEqual(before, hashlib.sha256(db.read_bytes()).hexdigest())
                receipt = authority.consume(REQUEST_ID)
                self.assertEqual(receipt.state, "CONSUMED")
                self.assertEqual(receipt.availability_checks, 2)
                self.assertTrue(receipt.durable_replay_consumed)
                self.assertTrue(receipt.replay_mutation_started)
                self.assertFalse(receipt.production_mutation_started)
                self.assertFalse(authority.is_available(accepted))
                with self.assertRaises(runtime.HermesOriginRuntimeAdapterError):
                    authority.consume(REQUEST_ID)
            conn = sqlite3.connect(db)
            try:
                row = conn.execute(
                    "SELECT state FROM requests WHERE request_id = ?", (REQUEST_ID,)
                ).fetchone()
            finally:
                conn.close()
            self.assertEqual(row, ("CONSUMED",))

    def test_consume_requires_double_identical_canonical_availability(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.sqlite3"
            with StateStore(db, bootstrap=True):
                pass
            os.chmod(db, 0o600)
            with (
                patch.object(runtime, "STATE_DB_PATH", db),
                patch.object(runtime, "ROOT_UID", os.geteuid()),
                patch.object(runtime, "ROOT_GID", os.getegid()),
            ):
                authority = runtime.ConcreteDurableHermesOriginReplayAuthority()
                self.assertTrue(authority.is_available(_accepted()))
                with self.assertRaises(runtime.HermesOriginRuntimeAdapterError):
                    authority.consume(REQUEST_ID)
                authority = runtime.ConcreteDurableHermesOriginReplayAuthority()
                self.assertTrue(authority.is_available(_accepted()))
                with self.assertRaises(runtime.HermesOriginRuntimeAdapterError):
                    authority.is_available(_accepted(issue_id=5018))


class LocalHostObservationProviderTests(unittest.TestCase):
    def test_fixed_provider_emits_sanitized_observation_without_credential_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            registration = base / "registration.json"
            helper = base / "helper"
            probe = base / "probe.py"
            broker = base / "broker"
            socket_unit = base / "broker.socket"
            service_unit = base / "broker.service"
            credential = base / "source.pem"
            evidence = base / "evidence"
            machine = evidence / "rpi5"
            sock_path = base / "request.sock"
            evidence.mkdir(mode=0o700)
            machine.mkdir(mode=0o700)

            helper_raw = b"reviewed helper\n"
            probe_raw = b"reviewed probe\n"
            broker_raw = b"reviewed broker\n"
            socket_raw = b"reviewed socket unit\n"
            service_raw = b"reviewed service unit\n"
            helper.write_bytes(helper_raw)
            probe.write_bytes(probe_raw)
            broker.write_bytes(broker_raw)
            socket_unit.write_bytes(socket_raw)
            service_unit.write_bytes(service_raw)
            credential.write_bytes(b"PRIVATE-CONTENT-MUST-NOT-BE-READ")
            for path in (helper, probe, broker):
                path.chmod(0o755)
            for path in (socket_unit, service_unit):
                path.chmod(0o644)
            credential.chmod(0o600)

            helper_sha = hashlib.sha256(helper_raw).hexdigest()
            probe_sha = hashlib.sha256(probe_raw).hexdigest()
            registration.write_text(
                json.dumps(
                    {
                        "schema": "rozkalns.hermes-deals.origin-path-rpi5-pull-registration.v1",
                        "capability": "origin-path-audit",
                        "registered_source_sha": runtime.REVIEWED_HERMES_SOURCE_SHA,
                        "helper_sha256": helper_sha,
                        "probe_sha256": probe_sha,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            registration.chmod(0o600)

            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                server.bind(str(sock_path))
                os.chmod(sock_path, 0o660)
                original_read = runtime._read_bounded

                def guarded_read(path: Path, *, max_bytes: int) -> bytes:
                    self.assertNotEqual(path, credential)
                    return original_read(path, max_bytes=max_bytes)

                patches = {
                    "ROOT_UID": os.geteuid(),
                    "ROOT_GID": os.getegid(),
                    "REGISTRATION_PATH": str(registration),
                    "INSTALLED_HELPER_PATH": str(helper),
                    "PROBE_PATH": str(probe),
                    "BROKER_INSTALL_PATH": str(broker),
                    "BROKER_SOCKET_UNIT_PATH": socket_unit,
                    "BROKER_SERVICE_UNIT_PATH": service_unit,
                    "SOURCE_CREDENTIAL_PATH": str(credential),
                    "EVIDENCE_ROOT": evidence,
                    "MACHINE_ROOT": machine,
                    "SOCKET_PATH": sock_path,
                    "HELPER_SHA256": helper_sha,
                    "PROBE_SHA256": probe_sha,
                    "PULL_HELPER_SOURCE_BLOB": _git_blob(helper_raw),
                    "PROBE_SOURCE_BLOB": _git_blob(probe_raw),
                    "BROKER_ENTRYPOINT_GIT_BLOB": _git_blob(broker_raw),
                    "BROKER_SOCKET_UNIT_GIT_BLOB": _git_blob(socket_raw),
                    "BROKER_SERVICE_UNIT_GIT_BLOB": _git_blob(service_raw),
                    "_group_gid": lambda _name: os.getegid(),
                    "_read_bounded": guarded_read,
                }
                with ExitStack() as stack:
                    for name, value in patches.items():
                        stack.enter_context(patch.object(runtime, name, value))
                    value = json.loads(
                        runtime.ConcreteLocalHermesOriginHostObservationProvider()
                        .read()
                        .decode("utf-8")
                    )
            finally:
                server.close()
            self.assertEqual(value["registered_source_sha"], runtime.REVIEWED_HERMES_SOURCE_SHA)
            self.assertFalse(value["credential_content_read"])
            self.assertFalse(value["protected_values_included"])
            self.assertFalse(value["filesystem_mutation"])
            self.assertFalse(value["systemd_interaction"])
            self.assertFalse(value["authority_expanded"])
            self.assertFalse(value["production_mutation_started"])
            self.assertEqual(
                tuple(inspect.signature(runtime.ConcreteLocalHermesOriginHostObservationProvider.read).parameters),
                ("self",),
            )


class SourceAppScopeProverTests(unittest.TestCase):
    def test_scope_proof_never_exposes_short_lived_token(self):
        class FakeProvider:
            repository = runtime.HERMES_DEALS_SOURCE_REPOSITORY
            repository_id = runtime.HERMES_DEALS_SOURCE_REPOSITORY_ID

            def get_installation_token(self):
                return InstallationToken("secret-token-value-that-must-not-escape")

        with patch.object(runtime, "build_hermes_deals_source_token_provider", return_value=FakeProvider()):
            proof = runtime.ConcreteHermesDealsSourceAppScopeProver().prove()
        self.assertEqual(proof.repository, runtime.HERMES_DEALS_SOURCE_REPOSITORY)
        self.assertTrue(proof.credential_content_read)
        self.assertTrue(proof.github_api_request)
        self.assertTrue(proof.installation_token_minted)
        self.assertFalse(proof.installation_token_exposed)
        self.assertNotIn("token", proof.__dict__)
        self.assertFalse(proof.credential_mutation)
        self.assertFalse(proof.filesystem_mutation)
        self.assertFalse(proof.production_mutation_started)

    def test_default_cli_is_nonprotected_and_does_not_prove(self):
        result = subprocess.run(
            (
                sys.executable,
                str(ROOT / "scripts/prove-hermes-deals-origin-source-app-scope.py"),
                SOURCE_SHA,
            ),
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value["result"], "HERMES_SOURCE_APP_SCOPE_PROOF_PROTECTED_READY")
        self.assertFalse(value["credential_content_read"])
        self.assertFalse(value["github_api_request"])
        self.assertFalse(value["installation_token_minted"])
        self.assertFalse(value["installation_token_exposed"])

    def test_source_app_scope_cli_uses_root_safe_exact_source_validation(self):
        source = (
            ROOT / "scripts/prove-hermes-deals-origin-source-app-scope.py"
        ).read_text(encoding="utf-8")
        self.assertIn("f'safe.directory={ROOT}'", source)
        self.assertIn("_git('rev-parse', 'HEAD')", source)
        self.assertIn(
            "_git('show', f'{expected_sha}:scripts/prove-hermes-deals-origin-source-app-scope.py')",
            source,
        )
        self.assertIn("_git('status', '--porcelain')", source)

    def test_source_readiness_remains_nonlive(self):
        readiness = runtime.source_readiness()
        self.assertTrue(readiness["source_app_scope_prover_implemented"])
        self.assertTrue(readiness["durable_replay_adapter_implemented"])
        self.assertTrue(readiness["host_observation_provider_implemented"])
        for key in (
            "source_app_scope_runtime_proven",
            "durable_replay_runtime_proven",
            "host_observation_runtime_proven",
            "broker_entrypoint_wired",
            "privileged_dispatch_enabled",
            "genuine_hermes_audit_authorized",
            "production_mutation_started",
        ):
            self.assertFalse(readiness[key], key)


class ContractAndSourceBoundaryTests(unittest.TestCase):
    def test_machine_contract_binds_exact_source_blobs_and_stays_nonlive(self):
        contract = json.loads(
            (ROOT / "ops/deploy/hermes-deals-origin-runtime-adapters.json").read_text(
                encoding="utf-8"
            )
        )
        bindings = (
            (contract["runtime_module"]["path"], contract["runtime_module"]["source_blob"]),
            (
                contract["runtime_adapter_preflight"]["path"],
                contract["runtime_adapter_preflight"]["source_blob"],
            ),
            (
                contract["source_app_scope_proof"]["operator"],
                contract["source_app_scope_proof"]["operator_source_blob"],
            ),
        )
        for path, expected in bindings:
            observed = subprocess.check_output(
                ("git", "hash-object", path), cwd=ROOT, text=True
            ).strip()
            self.assertEqual(observed, expected, path)
        self.assertEqual(
            contract["required_previous_result"],
            "HERMES_ORIGIN_RUNTIME_PREFLIGHT_PARTIAL_READY",
        )
        self.assertTrue(contract["source_app_scope_proof"]["requires_separate_live_owner_authorization"])
        self.assertFalse(contract["source_app_scope_proof"]["installation_token_exposed"])
        for key in (
            "runtime_adapters_runtime_proven",
            "source_app_installation_scope_proven",
            "broker_entrypoint_wired",
            "privileged_dispatch_enabled",
            "genuine_hermes_audit_authorized",
            "runner_retirement_eligible",
            "production_mutation_started",
        ):
            self.assertFalse(contract["source_gate_flags"][key], key)

    def test_runtime_preflight_has_no_protected_or_mutation_surface(self):
        source = (
            ROOT / "scripts/preflight-hermes-deals-origin-runtime-adapters.py"
        ).read_text(encoding="utf-8")
        self.assertIn('f"safe.directory={ROOT}"', source)
        self.assertIn('_git("rev-parse", "HEAD")', source)
        self.assertIn('_git("show", f"{expected_sha}:scripts/preflight-hermes-deals-origin-runtime-adapters.py")', source)
        self.assertIn('_git("status", "--porcelain")', source)
        for token in (
            "--apply",
            "ConcreteHermesDealsSourceAppScopeProver",
            "get_installation_token",
            "StateStore(",
            ".consume(",
            "systemctl",
            "socket.connect",
            "subprocess.Popen",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_docs_mark_current_gate_and_keep_broker_disabled(self):
        master = (ROOT / "docs/AUTOMATION_MASTER_PLAN.md").read_text(encoding="utf-8")
        current = master.rindex(
            "## Current supersession — Hermes PARTIAL_READY runtime-adapter trust-boundary source gate"
        )
        text = master[current:]
        self.assertIn(
            "PHASE4_CURRENT_WORK_ITEM=HERMES_ORIGIN_RUNTIME_ADAPTER_TRUST_BOUNDARY_SOURCE",
            text,
        )
        self.assertIn("BROKER_ENTRYPOINT_WIRED=false", text)
        self.assertIn("PRIVILEGED_DISPATCH_ENABLED=false", text)
        self.assertIn("GENUINE_HERMES_AUDIT_AUTHORIZED=false", text)
        self.assertIn("PRODUCTION_MUTATION_STARTED=false", text)


if __name__ == "__main__":
    unittest.main()
