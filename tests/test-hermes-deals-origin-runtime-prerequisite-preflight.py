from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/preflight-hermes-deals-origin-runtime-prerequisites.py"
spec = importlib.util.spec_from_file_location("hermes_runtime_preflight", SCRIPT)
assert spec is not None and spec.loader is not None
preflight = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = preflight
spec.loader.exec_module(preflight)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


class HermesRuntimePrerequisitePreflightTests(unittest.TestCase):
    def test_credential_check_is_metadata_only_and_no_source_token_provider_is_used(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("P9SourceInstallationTokenProvider", source)
        self.assertNotIn("build_app_jwt", source)
        self.assertNotIn("https_json_request", source)
        with mock.patch.object(preflight, "_require_file_metadata") as metadata, mock.patch.object(
            preflight, "_require_directory_metadata"
        ) as directory, mock.patch.object(preflight, "_read_descriptor_safe") as read:
            preflight._credential_metadata()
        directory.assert_called_once_with(preflight.CREDENTIAL.parent, mode=0o700)
        metadata.assert_called_once_with(preflight.CREDENTIAL, mode=0o600)
        read.assert_not_called()

    def test_partial_ready_receipt_keeps_unproven_authority_false(self) -> None:
        raw = preflight._receipt(
            result="HERMES_ORIGIN_RUNTIME_PREFLIGHT_PARTIAL_READY",
            source_sha="a" * 40,
            registration_source_sha="b" * 40,
            state={
                "credential_metadata_proven": True,
                "durable_replay_store_proven": True,
                "local_host_identities_proven": True,
                "systemd_query_performed": True,
            },
        )
        value = json.loads(raw)
        self.assertTrue(value["credential_metadata_proven"])
        self.assertTrue(value["durable_replay_store_proven"])
        self.assertTrue(value["local_host_identities_proven"])
        self.assertFalse(value["credential_content_read"])
        self.assertFalse(value["github_api_request"])
        self.assertFalse(value["source_app_installation_scope_proven"])
        self.assertFalse(value["durable_replay_adapter_runtime_proven"])
        self.assertFalse(value["host_observation_adapter_runtime_proven"])
        self.assertFalse(value["broker_entrypoint_wired"])
        self.assertFalse(value["privileged_dispatch_enabled"])
        self.assertFalse(value["helper_executed"])
        self.assertFalse(value["filesystem_mutation"])
        self.assertFalse(value["systemd_mutation"])
        self.assertFalse(value["production_mutation_started"])

    def test_registration_helper_and_probe_are_exact_and_sanitized(self) -> None:
        old_uid, old_gid = preflight.ROOT_UID, preflight.ROOT_GID
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                helper = root / "helper.py"
                probe = root / "probe.py"
                registration = root / "registration.json"
                evidence = root / "evidence"
                helper_raw = b"#!/usr/bin/python3\nprint('helper')\n"
                probe_raw = b"#!/usr/bin/python3\nprint('probe')\n"
                helper.write_bytes(helper_raw)
                probe.write_bytes(probe_raw)
                os.chmod(helper, 0o755)
                os.chmod(probe, 0o755)
                evidence.mkdir()
                os.chmod(evidence, 0o700)
                machine_root = evidence / "rpi5"
                machine_root.mkdir()
                os.chmod(machine_root, 0o700)
                source_sha = "c" * 40
                registration.write_text(
                    json.dumps(
                        {
                            "schema": preflight.REGISTRATION_SCHEMA,
                            "capability": preflight.CAPABILITY,
                            "registered_source_sha": source_sha,
                            "helper_sha256": hashlib.sha256(helper_raw).hexdigest(),
                            "probe_sha256": hashlib.sha256(probe_raw).hexdigest(),
                        }
                    ),
                    encoding="utf-8",
                )
                os.chmod(registration, 0o600)
                preflight.ROOT_UID = os.getuid()
                preflight.ROOT_GID = os.getgid()
                with mock.patch.object(preflight, "REGISTRATION", registration), mock.patch.object(
                    preflight, "HELPER", helper
                ), mock.patch.object(preflight, "PROBE", probe), mock.patch.object(
                    preflight, "EVIDENCE_ROOT", evidence
                ), mock.patch.object(preflight, "MACHINE_ROOT", machine_root), mock.patch.object(preflight, "HELPER_GIT_BLOB", git_blob(helper_raw)), mock.patch.object(
                    preflight, "PROBE_GIT_BLOB", git_blob(probe_raw)
                ):
                    self.assertEqual(preflight._registration_and_helper(), source_sha)
        finally:
            preflight.ROOT_UID, preflight.ROOT_GID = old_uid, old_gid

    def test_registration_extra_field_fails_closed(self) -> None:
        old_uid, old_gid = preflight.ROOT_UID, preflight.ROOT_GID
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                registration = root / "registration.json"
                registration.write_text(
                    json.dumps(
                        {
                            "schema": preflight.REGISTRATION_SCHEMA,
                            "capability": preflight.CAPABILITY,
                            "registered_source_sha": "d" * 40,
                            "helper_sha256": "0" * 64,
                            "probe_sha256": "1" * 64,
                            "unexpected": "forbidden",
                        }
                    ),
                    encoding="utf-8",
                )
                os.chmod(registration, 0o600)
                preflight.ROOT_UID = os.getuid()
                preflight.ROOT_GID = os.getgid()
                with mock.patch.object(preflight, "REGISTRATION", registration):
                    with self.assertRaises(preflight.RuntimePreflightError):
                        preflight._registration_and_helper()
        finally:
            preflight.ROOT_UID, preflight.ROOT_GID = old_uid, old_gid

    def _make_state_db(self, path: Path) -> None:
        db = sqlite3.connect(path)
        db.execute(
            """
            CREATE TABLE requests (
                repository_id INTEGER NOT NULL,
                issue_id INTEGER NOT NULL,
                request_id TEXT NOT NULL,
                canonical_payload_sha256 TEXT NOT NULL,
                raw_body_sha256 TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                consumed_at TEXT,
                PRIMARY KEY (repository_id, issue_id),
                UNIQUE (request_id)
            )
            """
        )
        db.execute("PRAGMA application_id = 1381647448")
        db.execute("PRAGMA user_version = 1")
        db.commit()
        db.close()
        os.chmod(path, 0o600)

    def test_state_db_verification_is_immutable_and_read_only(self) -> None:
        old_uid, old_gid = preflight.ROOT_UID, preflight.ROOT_GID
        try:
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "state.sqlite3"
                self._make_state_db(path)
                before = path.stat()
                preflight.ROOT_UID = os.getuid()
                preflight.ROOT_GID = os.getgid()
                with mock.patch.object(preflight, "STATE_DB", path):
                    preflight._verify_state_db()
                after = path.stat()
                self.assertEqual((before.st_size, before.st_mtime_ns), (after.st_size, after.st_mtime_ns))
                self.assertFalse(Path(str(path) + "-wal").exists())
                self.assertFalse(Path(str(path) + "-shm").exists())
        finally:
            preflight.ROOT_UID, preflight.ROOT_GID = old_uid, old_gid

    def test_live_wal_fails_closed_before_sqlite_open(self) -> None:
        old_uid, old_gid = preflight.ROOT_UID, preflight.ROOT_GID
        try:
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "state.sqlite3"
                self._make_state_db(path)
                Path(str(path) + "-wal").write_bytes(b"nonempty")
                preflight.ROOT_UID = os.getuid()
                preflight.ROOT_GID = os.getgid()
                with mock.patch.object(preflight, "STATE_DB", path):
                    with self.assertRaises(preflight.RuntimePreflightError):
                        preflight._verify_state_db()
        finally:
            preflight.ROOT_UID, preflight.ROOT_GID = old_uid, old_gid

    def test_systemctl_mutations_are_not_allowlisted(self) -> None:
        with self.assertRaises(preflight.RuntimePreflightError):
            preflight._systemctl_query("restart", preflight.SOCKET_UNIT)
        with self.assertRaises(preflight.RuntimePreflightError):
            preflight._systemctl_query("enable", "--now", preflight.SOCKET_UNIT)

    def test_machine_contract_binds_exact_operator_and_partial_ready_semantics(self) -> None:
        manifest = json.loads((ROOT / "ops/deploy/hermes-deals-origin-runtime-prerequisite-preflight.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["operator"]["source_blob"], git_blob(SCRIPT.read_bytes()))
        self.assertEqual(manifest["success_result"], "HERMES_ORIGIN_RUNTIME_PREFLIGHT_PARTIAL_READY")
        self.assertFalse(manifest["operator"]["network_request_implemented"])
        self.assertFalse(manifest["operator"]["credential_content_read_implemented"])
        self.assertFalse(manifest["operator"]["mutation_implemented"])
        self.assertTrue(manifest["deliberately_unproven"]["source_app_installation_scope"])
        self.assertFalse(manifest["deliberately_unproven"]["durable_replay_adapter_runtime_proven"])
        self.assertFalse(manifest["deliberately_unproven"]["host_observation_adapter_runtime_proven"])
        self.assertFalse(manifest["deliberately_unproven"]["broker_entrypoint_wired"])
        self.assertFalse(manifest["deliberately_unproven"]["genuine_hermes_audit_authorized"])


if __name__ == "__main__":
    unittest.main()
