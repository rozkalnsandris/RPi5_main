#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops" / "deploy" / "rozkalns-cv-post-cutover-reconciliation-v1.json"
OLD_CUTOVER = ROOT / "ops" / "deploy" / "rozkalns-cv-simple-deploy-cutover-v1.json"
COMPAT = ROOT / "ops" / "contracts" / "simple-deploy-rozkalns-cv-compat-v1.json"
HOST = ROOT / "ops" / "contracts" / "simple-deploy-host-v1.json"
REGISTRY = ROOT / "ops" / "deploy" / "executor-operations.json"
OPERATOR = ROOT / "ops" / "bin" / "rozkalns-cv-post-cutover-reconcile"

LIVE_SOURCE = "6c226ac797602007b960da8dad114f794f450717"
LIVE_DIGEST = "sha256:dd33f110db46f92953241680bf86b475cdbb10fd76ec7f5e5ec6299ea2a97480"
LEGACY_STATE = "4986a6d80460bd6d7681c70e09e61a15e31007f4"
LEGACY_CVBOT_IMAGE = "rozkalns-cv-cvbot:8661337c1020c4d70e1da129209c5ffd7ad9bf7e"
EXPECTED_ARTIFACTS = {
    "/var/lib/rozkalns-cv-deploy/current-sha": "root:root:644",
    "/usr/local/sbin/rozkalns-cv-pull-deploy": "root:root:755",
    "/usr/local/libexec/rozkalns-cv/deploy-readiness": "root:root:755",
    "/etc/systemd/system/rozkalns-cv-pull-deploy.service": "root:root:644",
    "/etc/systemd/system/rozkalns-cv-pull-deploy.timer": "root:root:644",
    "/usr/local/sbin/rozkalns-cv-manual-rollout-operator": "root:root:755",
    "/usr/local/sbin/rozkalns-cv-pull-deploy-canary": "root:root:755",
    "/usr/local/sbin/rozkalns-cv-pull-deploy-main": "root:root:755",
    "/etc/sudoers.d/rozkalns-cv-pull-deploy": "root:root:440",
    "/usr/local/sbin/rozkalns-cv-pull-deploy-preflight": "root:root:755",
    "/usr/local/libexec/rozkalns-cv/classify-deploy-impact": "root:root:755",
    "/usr/local/libexec/rozkalns-cv/rozkalns-cv-deploy-library": "root:root:755",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class RozkalnsCvPostCutoverReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load(CONTRACT)
        cls.operator = OPERATOR.read_text(encoding="utf-8")
        completed = subprocess.run(
            ["bash", "-n", str(OPERATOR)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stdout)

    def test_contract_binds_observed_live_runtime_and_residuals(self) -> None:
        self.assertEqual(
            self.contract["schema"],
            "rozkalns.rpi5-main.rozkalns-cv-post-cutover-reconciliation.v1",
        )
        self.assertEqual(self.contract["issue"], 913)
        self.assertFalse(self.contract["execution_enabled"])
        self.assertEqual(self.contract["authorization_class"], "STRICT")
        self.assertFalse(self.contract["ordinary_live_all_eligible"])
        self.assertTrue(self.contract["one_time"])

        live = self.contract["observed_live_runtime"]
        self.assertEqual(live["source_sha"], LIVE_SOURCE)
        self.assertEqual(live["image_digest"], LIVE_DIGEST)
        self.assertEqual(live["compose_project"], "rozkalns-cv")
        self.assertEqual(live["compose_service"], "cv")
        self.assertEqual(live["required_port_bind"], "127.0.0.1:8088")
        self.assertTrue(live["runtime_current_at_observation"])

        residual = self.contract["legacy_residual"]
        self.assertEqual(residual["cvbot"]["image"], LEGACY_CVBOT_IMAGE)
        self.assertTrue(residual["legacy_cv_container_required_absent"])
        self.assertEqual(residual["production_state"]["expected_sha"], LEGACY_STATE)
        observed = {
            row["path"]: f'{row["owner"]}:{row["group"]}:{row["mode"]}'
            for row in residual["retirement_artifacts"]
        }
        self.assertEqual(observed, EXPECTED_ARTIFACTS)

    def test_operator_is_check_by_default_and_apply_is_confirmed(self) -> None:
        for marker in (
            'MODE="${1:-check}"',
            "--expected-main",
            "RECONCILE-ROZKALNS-CV-POST-CUTOVER",
            "ROZKALNS_CV_POST_CUTOVER_RECONCILIATION_CHECK=PASS",
            "ROZKALNS_CV_POST_CUTOVER_RECONCILIATION_APPLY=PASS",
            "NO_OP_ALREADY_RECONCILED",
        ):
            self.assertIn(marker, self.operator)

    def test_operator_preserves_exact_live_runtime_identity(self) -> None:
        for marker in (
            "LIVE_CONTAINER='rozkalns-cv-cv-1'",
            f"LIVE_SOURCE='{LIVE_SOURCE}'",
            f"LIVE_IMAGE='ghcr.io/rozkalnsandris/rozkalns-cv@{LIVE_DIGEST}'",
            "LIVE_PORT='127.0.0.1:8088'",
            "SIMPLE-DEPLOY CV container identity changed during reconciliation",
            "CV liveness is not HTTP 200",
            "CV readiness is not HTTP 200",
        ):
            self.assertIn(marker, self.operator)

    def test_only_exact_legacy_cvbot_has_docker_lifecycle_mutation(self) -> None:
        self.assertIn('docker stop --time 20 "$LEGACY_ID"', self.operator)
        self.assertIn('docker rm "$LEGACY_ID"', self.operator)
        self.assertIn('LEGACY_ID="$id"', self.operator)
        self.assertIn('[[ "$(docker inspect "$LEGACY_CVBOT" --format \'{{.Id}}\')" == "$LEGACY_ID" ]]', self.operator)
        self.assertNotRegex(self.operator, r"docker\s+rm\s+(?:-[^\s]*f|--force)")
        filtered = self.operator.replace('docker stop --time 20 "$LEGACY_ID"', "")
        filtered = filtered.replace('docker rm "$LEGACY_ID"', "")
        self.assertIsNone(
            re.search(
                r"(^|\s)docker\s+(run|create|start|stop|restart|rm|rename|pull|rmi)(\s|$)",
                filtered,
            )
        )

    def test_root_exec_requires_reviewed_installed_operator(self) -> None:
        for marker in (
            "INSTALLED_OPERATOR='/usr/local/sbin/rozkalns-cv-post-cutover-reconcile'",
            "RPI_REPO='/home/andris/RPi5_main'",
            '[[ "${BASH_SOURCE[0]}" == "$INSTALLED_OPERATOR" ]]',
            '[[ -f "$INSTALLED_OPERATOR" && ! -L "$INSTALLED_OPERATOR" ]]',
            "'root:root:500'",
            'git hash-object "$INSTALLED_OPERATOR"',
            'owner_git rev-parse "$EXPECTED_MAIN:$SOURCE_REL"',
            "never a checkout script as root",
        ):
            self.assertIn(marker, self.operator)
        self.assertNotIn('repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")', self.operator)

    def test_retirement_file_allowlist_is_exact(self) -> None:
        for path, stat in EXPECTED_ARTIFACTS.items():
            self.assertIn(f"'{path}|{stat}'", self.operator)
        self.assertEqual(self.operator.count("|root:root:"), len(EXPECTED_ARTIFACTS))
        self.assertIn('rm -f -- "$path"', self.operator)
        self.assertIn('retirement artifact changed before removal', self.operator)
        self.assertIn('retirement artifact metadata changed before removal', self.operator)
        self.assertNotIn("rm -rf", self.operator)

    def test_systemd_mutation_is_only_daemon_reload(self) -> None:
        self.assertIn("systemctl daemon-reload", self.operator)
        self.assertIsNone(
            re.search(
                r"systemctl\s+(start|stop|restart|try-restart|reload|enable|disable|mask|unmask)",
                self.operator,
            )
        )

    def test_protected_boundaries_are_not_operator_targets(self) -> None:
        protected = self.contract["protected_boundaries"]
        self.assertFalse(protected["private_env_content_access"])
        self.assertFalse(protected["persistent_data_content_access"])
        self.assertFalse(protected["database_or_application_data_mutation"])
        self.assertFalse(protected["cloudflare_or_network_mutation"])
        for forbidden in (
            "/etc/rozkalns-simple-deployer/private/rozkalns-cv.env",
            "/etc/rozkalns-simple-deployer/compose/rozkalns-cv.yml",
            "/var/lib/rozkalns-simple-deployer/receipts/rozkalns-cv-rpi5.json",
            "docker/cv/bot/.env",
            "docker/cv/bot/data",
        ):
            self.assertNotIn(forbidden, self.operator)

    def test_old_cutover_is_historical_and_no_longer_registered(self) -> None:
        old = load(OLD_CUTOVER)
        lifecycle = old["lifecycle"]
        self.assertEqual(
            lifecycle["status"],
            "HISTORICAL_SUPERSEDED_BY_OBSERVED_SIMPLE_DEPLOY_RUNTIME",
        )
        self.assertEqual(lifecycle["superseded_by_issue"], 913)
        self.assertTrue(lifecycle["reexecution_as_current_cutover_forbidden"])

        registry = load(REGISTRY)
        ids = {row["operation_id"] for row in registry["operations"]}
        self.assertNotIn("rpi5-main.rozkalns-cv-simple-deploy-cutover.v1", ids)
        self.assertIn("rpi5-main.rozkalns-cv-post-cutover-reconcile.v1", ids)

    def test_compat_and_host_contract_report_observed_live_state(self) -> None:
        compat = load(COMPAT)
        self.assertEqual(
            compat["status"],
            "LIVE_SIMPLE_DEPLOY_OBSERVED_LEGACY_RECONCILIATION_REQUIRED",
        )
        self.assertEqual(compat["observed_runtime"]["source_sha"], LIVE_SOURCE)
        self.assertEqual(compat["observed_runtime"]["image_digest"], LIVE_DIGEST)
        self.assertFalse(
            compat["boundaries"]["target_installation_requires_separate_exact_live_cutover"]
        )
        self.assertTrue(
            compat["boundaries"]["existing_runtime_retirement_requires_separate_exact_live_authority"]
        )

        host = load(HOST)
        self.assertFalse(
            host["activation"]["rozkalns_cv_target_installation_requires_separate_exact_live_cutover"]
        )
        self.assertTrue(
            host["activation"]["rozkalns_cv_existing_runtime_retirement_requires_separate_exact_live_authority"]
        )

    def test_executor_registration_is_strict_and_inert(self) -> None:
        registry = load(REGISTRY)
        self.assertFalse(registry["execution_enabled"])
        operations = {row["operation_id"]: row for row in registry["operations"]}
        op = operations["rpi5-main.rozkalns-cv-post-cutover-reconcile.v1"]
        self.assertEqual(op["authorization_class"], "STRICT")
        self.assertFalse(op["ordinary_live_all_eligible"])
        self.assertEqual(op["rollback_policy"], "NONE")
        self.assertEqual(
            op["queue_match"]["repository_entrypoint"],
            "ops/bin/rozkalns-cv-post-cutover-reconcile",
        )
        self.assertIn("global-execution:disabled", op["dependencies"])

    def test_installation_gate_and_exact_id_are_source_only(self) -> None:
        policy = self.contract["operator_installation"]
        self.assertEqual(policy["reviewed_source"], "ops/bin/rozkalns-cv-post-cutover-reconcile")
        self.assertEqual(policy["exact_installed_path"], "/usr/local/sbin/rozkalns-cv-post-cutover-reconcile")
        self.assertEqual((policy["owner"], policy["group"], policy["mode"]), ("root", "root", "0500"))
        self.assertTrue(policy["installed_git_blob_must_match_exact_main"])
        self.assertTrue(policy["checkout_root_execution_forbidden"])
        self.assertTrue(policy["separate_live_installation_authorization_required"])
        self.assertTrue(self.contract["verification"]["legacy_cvbot_container_id_must_be_stable_until_stop"])

    def test_source_merge_never_grants_live_authority(self) -> None:
        state = self.contract["source_only_state"]
        self.assertFalse(state["live_authorized"])
        self.assertFalse(state["runtime_mutation_permitted_by_this_file"])
        self.assertFalse(state["protected_runtime_content_access_authorized"])
        self.assertFalse(state["merge_authorized"])

        failure = self.contract["failure_semantics"]
        self.assertTrue(failure["fail_closed"])
        self.assertFalse(failure["automatic_retry"])
        self.assertFalse(failure["automatic_cleanup"])
        self.assertFalse(failure["automatic_rollback"])
        self.assertFalse(failure["alternate_mutation_path"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
