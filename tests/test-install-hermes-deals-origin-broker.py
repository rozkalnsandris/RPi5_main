from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/install-hermes-deals-origin-broker.py"
MANIFEST = ROOT / "ops/deploy/hermes-deals-origin-broker-installer.json"
spec = importlib.util.spec_from_file_location("hermes_installer", SCRIPT)
assert spec is not None and spec.loader is not None
installer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = installer
spec.loader.exec_module(installer)


class HermesOriginBrokerInstallerTests(unittest.TestCase):
    def test_frozen_target_surface_is_exact_and_bounded(self) -> None:
        self.assertEqual(len(installer.TARGETS), 10)
        self.assertEqual(
            {item.source_path for item in installer.TARGETS},
            {
                "ops/lib/deploy_executor/hermes_deals_origin_privileged_broker.py",
                "ops/lib/deploy_executor/hermes_deals_origin_source_auth.py",
                "ops/lib/deploy_executor/hermes_deals_origin_helper_launch.py",
                "ops/lib/deploy_executor/hermes_deals_origin_canonical_revalidator.py",
                "ops/lib/deploy_executor/hermes_deals_origin_host_evidence.py",
                "ops/lib/deploy_executor/hermes_deals_origin_broker_composition.py",
                "ops/lib/deploy_executor/p9_source_auth.py",
                "ops/bin/rozkalns-hermes-deals-origin-broker",
                "ops/systemd/rozkalns-hermes-deals-origin-broker.socket",
                "ops/systemd/rozkalns-hermes-deals-origin-broker@.service",
            },
        )
        self.assertEqual(
            installer.SYSTEMCTL_MUTATIONS,
            (
                ("daemon-reload",),
                ("enable", "--now", installer.SOCKET_UNIT),
            ),
        )

    def test_git_blob_matches_git_object_rule(self) -> None:
        self.assertEqual(
            installer._git_blob(b"hello\n"),
            "ce013625030ba8dba906f756967f9e9ca394464a",
        )

    def test_git_trust_is_exact_command_scoped_without_env_widening(self) -> None:
        completed = mock.Mock(returncode=0, stdout=b"ok\n", stderr=b"")
        with mock.patch.object(installer.subprocess, "run", return_value=completed) as run:
            installer._git("rev-parse", "HEAD")
        argv = run.call_args.args[0]
        self.assertEqual(
            argv[:5],
            (
                str(installer.GIT),
                "-c",
                f"safe.directory={installer.ROOT}",
                "-C",
                str(installer.ROOT),
            ),
        )
        self.assertNotIn("safe.directory=*", argv)
        self.assertNotIn("--global", argv)
        self.assertNotIn("--system", argv)
        self.assertEqual(
            run.call_args.kwargs["env"],
            {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
        )
        self.assertEqual(SCRIPT.read_text(encoding="utf-8").count("str(GIT)"), 1)

    def test_installer_manifest_is_bound_to_script_and_exact_targets(self) -> None:
        value = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(
            value["installer"]["source_blob"],
            installer._git_blob(SCRIPT.read_bytes()),
        )
        self.assertEqual(
            [
                (row["source"], row["target"], row["source_blob"], row["mode"])
                for row in value["install_targets"]
            ],
            [
                (
                    target.source_path,
                    str(target.target_path),
                    target.expected_blob,
                    f"{target.mode:04o}",
                )
                for target in installer.TARGETS
            ],
        )
        self.assertEqual(
            value["installer"]["git_trust_scope"],
            "COMMAND_ONLY_EXACT_REPO_ROOT",
        )
        self.assertFalse(value["installer"]["git_safe_directory_wildcard"])
        self.assertFalse(value["installer"]["git_global_or_system_config_mutation"])
        safety = value["source_safety_state"]
        self.assertFalse(safety["live_install_eligible"])
        self.assertFalse(safety["runtime_preflight_proven"])
        self.assertFalse(safety["broker_entrypoint_wired"])
        self.assertFalse(safety["privileged_dispatch_enabled"])
        self.assertFalse(safety["genuine_hermes_audit_authorized"])
        self.assertFalse(safety["production_mutation_started"])

    def test_existing_target_fails_closed_without_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "target"
            target = installer.Target("source", path, "0" * 40, 0o644)
            self.assertEqual(installer._existing_target_state(target, b"x"), "absent")
            path.write_bytes(b"already here")
            with self.assertRaises(installer.HermesOriginBrokerInstallerError):
                installer._existing_target_state(target, b"x")

    def test_credential_preflight_checks_metadata_only(self) -> None:
        old_path = installer.SOURCE_CREDENTIAL
        old_uid = installer.ROOT_UID
        old_gid = installer.ROOT_GID
        try:
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "credential.pem"
                path.write_bytes(b"fixture-content-must-not-be-read")
                os.chmod(path, 0o600)
                installer.SOURCE_CREDENTIAL = path
                installer.ROOT_UID = os.getuid()
                installer.ROOT_GID = os.getgid()
                installer._credential_metadata_preflight()
                os.chmod(path, 0o640)
                with self.assertRaises(installer.HermesOriginBrokerInstallerError):
                    installer._credential_metadata_preflight()
        finally:
            installer.SOURCE_CREDENTIAL = old_path
            installer.ROOT_UID = old_uid
            installer.ROOT_GID = old_gid

    def test_systemctl_rejects_any_non_allowlisted_mutation_before_spawn(self) -> None:
        with self.assertRaises(installer.HermesOriginBrokerInstallerError):
            installer._systemctl("restart", installer.SOCKET_UNIT)

    def test_public_receipt_keeps_dispatch_and_audit_disabled(self) -> None:
        receipt = json.loads(
            installer._receipt(
                result="TEST",
                expected_sha="a" * 40,
                files_materialized=10,
                mutation_started=True,
                systemd_activated=True,
            )
        )
        self.assertFalse(receipt["credential_content_read"])
        self.assertFalse(receipt["credential_mutated"])
        self.assertFalse(receipt["helper_executed"])
        self.assertFalse(receipt["genuine_audit_authorized"])
        self.assertFalse(receipt["broker_dispatch_enabled"])
        self.assertFalse(receipt["host_wiring_enabled"])


if __name__ == "__main__":
    unittest.main()
