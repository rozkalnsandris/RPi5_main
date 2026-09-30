#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = ROOT / "scripts/install-simple-deploy-v1.py"
spec = importlib.util.spec_from_file_location("simple_deploy_installer", INSTALLER_PATH)
assert spec and spec.loader
installer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = installer
spec.loader.exec_module(installer)

CONTRACT = json.loads((ROOT / "ops/deploy/simple-deploy-installer-v1.json").read_text())
HOST = json.loads((ROOT / "ops/contracts/simple-deploy-host-v1.json").read_text())
SYSUSERS = (ROOT / "ops/sysusers/rozkalns-simple-deployer.conf").read_text()
SERVICE = (ROOT / "ops/systemd/rozkalns-simple-deployer.service").read_text()
DOC = (ROOT / "docs/SIMPLE_DEPLOY_HOST_V1.md").read_text()
PLAN = (ROOT / "docs/AUTOMATION_MASTER_PLAN.md").read_text()


class SimpleDeployInstallerSourceTests(unittest.TestCase):
    def test_sysusers_declares_static_principal_and_docker_membership(self) -> None:
        lines = [line for line in SYSUSERS.splitlines() if line and not line.startswith("#")]
        self.assertEqual(lines, [
            'u rozkalns-simple-deployer - "Rozkalns SIMPLE-DEPLOY reconciler" /var/lib/rozkalns-simple-deployer /usr/sbin/nologin',
            'm rozkalns-simple-deployer docker',
        ])
        self.assertNotIn("u!", SYSUSERS)  # host systemd 252; u! was added later

    def test_installer_contract_matches_fixed_source_targets(self) -> None:
        self.assertEqual(CONTRACT["issue"], 672)
        self.assertEqual(CONTRACT["reconciled_by_issue"], 674)
        self.assertEqual(CONTRACT["activation_issue"], 669)
        self.assertEqual(CONTRACT["status"], "SOURCE_ONLY_RECONCILED_FOR_INSTALL_SCHEMA_ACTIVATION_SPLIT")
        self.assertEqual(CONTRACT["principal"]["mechanism"], "systemd-sysusers")
        self.assertEqual(CONTRACT["principal"]["supplementary_groups"], ["docker"])
        self.assertTrue(CONTRACT["principal"]["first_install_requires_user_group_absent"])
        expected = [(str(t.target), f"{t.mode:04o}") for t in installer.TRACKED_FILES]
        actual = [(item["target"], item["mode"]) for item in CONTRACT["files"]]
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 10)
        self.assertEqual(len(CONTRACT["directories"]), 5)
        self.assertFalse(CONTRACT["source_merge_authorizes_live"])
        self.assertTrue(any(item["path"] == "/etc/rozkalns-simple-deployer/docker-anonymous" for item in CONTRACT["directories"]))
        repair = CONTRACT["phase_b_post_install_repair"]
        self.assertEqual(repair["base_source_sha"], installer.PHASE_B_REPAIR_BASE_SHA)
        self.assertEqual(repair["mode"], "--phase-b-repair")
        self.assertFalse(repair["source_merge_authorizes_live"])
        self.assertEqual(repair["allowed_replaced_files"], [str(installer.PHASE_B_SCHEMA_MODULE_TARGET), "/etc/rozkalns-simple-deployer/identity.json"])
        self.assertEqual([item["path"] for item in repair["state_directories"]], [str(installer.PHASE_B_STATE_ROOT), str(installer.PHASE_B_DOCKER_CONFIG)])

    def test_identity_is_exact_sha_only_and_parser_compatible(self) -> None:
        source_sha = "a" * 40
        identity = json.loads(installer._identity_bytes(source_sha))
        self.assertEqual(identity, {
            "schema": "rozkalns.rpi5-main.simple-deploy.identity.v1",
            "repository": "rozkalnsandris/RPi5_main",
            "source_sha": source_sha,
        })
        with self.assertRaises(installer.SimpleDeployInstallerError):
            installer._identity_bytes("main")

    def test_all_tracked_sources_exist_and_are_fixed(self) -> None:
        generated = 0
        for target in installer.TRACKED_FILES:
            self.assertTrue(target.target.is_absolute())
            if target.source_path is None:
                generated += 1
                self.assertEqual(str(target.target), "/etc/rozkalns-simple-deployer/identity.json")
            else:
                self.assertTrue((ROOT / target.source_path).is_file(), target.source_path)
        self.assertEqual(generated, 1)
        source = INSTALLER_PATH.read_text()
        self.assertIn('shell=False', source)
        self.assertNotIn('subprocess.call', source)
        self.assertNotIn('os.system(', source)
        self.assertNotIn('systemctl', source)

    def test_existing_install_target_is_rejected_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            existing = Path(temp) / "existing-target"
            existing.write_text("occupied\n", encoding="utf-8")
            with self.assertRaisesRegex(
                installer.SimpleDeployInstallerError,
                "first-install target already exists",
            ):
                installer._require_absent(existing)

            existing.unlink()
            existing.symlink_to("missing-target")
            with self.assertRaisesRegex(
                installer.SimpleDeployInstallerError,
                "first-install target already exists",
            ):
                installer._require_absent(existing)

    def test_receipt_keeps_activation_and_docker_side_effects_false(self) -> None:
        receipt = json.loads(
            installer._receipt("TEST", "a" * 40, installer.Progress())
        )
        self.assertFalse(receipt["daemon_reload_performed"])
        self.assertFalse(receipt["service_started"])
        self.assertFalse(receipt["timer_enabled_or_started"])
        self.assertFalse(receipt["docker_command_executed"])
        self.assertFalse(receipt["target_reconciliation_executed"])
        self.assertFalse(receipt["database_or_data_mutation"])

    def test_phase_b_repair_is_base_sha_pinned_and_scope_bounded(self) -> None:
        self.assertEqual(installer.PHASE_B_REPAIR_BASE_SHA, "b57ed42d5eb01f15b62c1f53459ffe0539a57d9c")
        self.assertEqual(str(installer.PHASE_B_STATE_ROOT), "/var/lib/rozkalns-simple-deployer")
        self.assertEqual(str(installer.PHASE_B_DOCKER_CONFIG), "/var/lib/rozkalns-simple-deployer/docker-anonymous")
        schema_target = installer.PHASE_B_SCHEMA_MODULE_TARGET

        def changed_only_schema(source_sha, target):
            marker = b"new" if source_sha != installer.PHASE_B_REPAIR_BASE_SHA and target.target == schema_target else b"old"
            return marker

        with mock.patch.object(installer, "_source_bytes_at", side_effect=changed_only_schema):
            changed = installer._phase_b_changed_targets("a" * 40)
        self.assertEqual([target.target for target, _ in changed], [schema_target])

        other = next(target for target in installer.TRACKED_FILES if target.source_path and target.target != schema_target)
        def unauthorized_change(source_sha, target):
            if source_sha != installer.PHASE_B_REPAIR_BASE_SHA and target.target in (schema_target, other.target):
                return b"new"
            return b"old"
        with mock.patch.object(installer, "_source_bytes_at", side_effect=unauthorized_change):
            with self.assertRaisesRegex(installer.SimpleDeployInstallerError, "unauthorized installed target"):
                installer._phase_b_changed_targets("a" * 40)

    def test_phase_b_repair_receipt_keeps_runtime_and_data_actions_false(self) -> None:
        receipt = json.loads(installer._phase_b_receipt("TEST", "a" * 40, installer.Progress()))
        self.assertEqual(receipt["base_source_sha"], installer.PHASE_B_REPAIR_BASE_SHA)
        self.assertFalse(receipt["daemon_reload_performed"])
        self.assertFalse(receipt["service_started"])
        self.assertFalse(receipt["timer_enabled_or_started"])
        self.assertFalse(receipt["docker_command_executed"])
        self.assertFalse(receipt["target_reconciliation_executed"])
        self.assertFalse(receipt["database_or_data_mutation"])

    def test_installer_stops_before_activation_or_docker(self) -> None:
        excluded = set(CONTRACT["not_performed_by_installer"])
        self.assertEqual(excluded, {
            "systemd-daemon-reload",
            "service-start",
            "timer-enable",
            "timer-start",
            "docker-command",
            "target-reconciliation",
            "database-or-data-mutation",
        })
        failure = CONTRACT["failure"]
        self.assertFalse(failure["automatic_retry"])
        self.assertFalse(failure["automatic_cleanup"])
        self.assertFalse(failure["automatic_rollback"])
        self.assertEqual(failure["post_first_mutation"], "STOP_FAIL_CLOSED")

    def test_service_uses_static_principal_and_systemd_state_directory(self) -> None:
        self.assertIn("User=rozkalns-simple-deployer", SERVICE)
        self.assertIn("Group=rozkalns-simple-deployer", SERVICE)
        self.assertIn("SupplementaryGroups=docker", SERVICE)
        self.assertIn("StateDirectory=rozkalns-simple-deployer", SERVICE)
        self.assertIn("StateDirectoryMode=0700", SERVICE)
        self.assertNotIn("DynamicUser=true", SERVICE)

    def test_host_contract_exposes_installer_without_live_side_effects(self) -> None:
        self.assertEqual(HOST["installer"]["issue"], 672)
        self.assertEqual(HOST["schema_init_bridge"]["issue"], 674)
        self.assertTrue(HOST["schema_init_bridge"]["requires_separate_exact_data_authority"])
        self.assertTrue(HOST["schema_init_bridge"]["activation_requires_schema_ready"])
        self.assertEqual(HOST["installer"]["entrypoint"], "scripts/install-simple-deploy-v1.py")
        self.assertEqual(HOST["installer"]["principal_mechanism"], "systemd-sysusers")
        self.assertFalse(HOST["installer"]["source_merge_executes_installer"])
        self.assertFalse(HOST["installer"]["installer_runs_daemon_reload"])
        self.assertFalse(HOST["installer"]["installer_starts_service_or_timer"])
        self.assertFalse(HOST["installer"]["installer_runs_docker_or_reconciliation"])
        self.assertTrue(HOST["activation"]["current_issue_669_must_be_freshly_reconciled_before_live"])

    def test_docs_preserve_669_authority_boundary(self) -> None:
        self.assertIn("#672", DOC)
        self.assertIn("#669 must be freshly reconciled", DOC)
        self.assertIn("does not silently widen #669", DOC)
        self.assertIn("#672 source-only deterministic installer/principal prerequisite", PLAN)
        self.assertIn("principal provisioning", PLAN)


if __name__ == "__main__":
    unittest.main()
