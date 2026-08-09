from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CANARY = ROOT / "ops" / "bin" / "rozkalns-cv-pull-deploy-canary"
INSTALLER = ROOT / "scripts" / "install-cv-pull-deploy-canary.sh"


class CvPullDeployCanaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.canary = CANARY.read_text(encoding="utf-8")
        cls.installer = INSTALLER.read_text(encoding="utf-8")

    def test_shell_sources_parse(self) -> None:
        for path in (CANARY, INSTALLER):
            completed = subprocess.run(
                ["bash", "-n", str(path)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout)

    def test_canary_requires_exact_duplicate_manual_approval(self) -> None:
        for marker in (
            "--target-sha",
            "--approve-manual-rollout",
            '[[ "$APPROVED_SHA" == "$TARGET_SHA" ]]',
            "manual rollout approval does not match target SHA",
            "approved target is no longer exact current origin/main",
            "origin/main advanced after approval checks; rerun with a new approval",
        ):
            self.assertIn(marker, self.canary)
        self.assertIn("PULL_DEPLOY_PREFLIGHT_RESULT", self.canary)
        self.assertIn("MANUAL_ROLLOUT_REQUIRED", self.canary)
        self.assertIn("preflight deploy impact is not manual rollout", self.canary)
        self.assertIn("preflight unexpectedly authorized production mutation", self.canary)

    def test_canary_runs_only_from_root_owned_installed_path(self) -> None:
        self.assertIn(
            "/usr/local/sbin/rozkalns-cv-pull-deploy-canary",
            self.canary,
        )
        self.assertIn("root:root:755", self.canary)
        self.assertIn("production canary must run as an unprivileged user", self.canary)
        self.assertIn("production canary must run as andris", self.canary)
        self.assertNotIn("/home/andris", self.canary)
        self.assertNotIn("/home/andris", self.installer)

    def test_canary_requires_exact_transport_and_control_artifacts(self) -> None:
        for marker in (
            "/usr/local/sbin/rozkalns-cv-pull-deploy-preflight",
            "/usr/local/libexec/rozkalns-cv/classify-deploy-impact",
            "/usr/local/libexec/rozkalns-cv/rozkalns-cv-deploy-library",
            "/usr/local/sbin/rozkalns-cv-pull-deploy-main",
            "runner/pull-deploy/rozkalns-cv-pull-deploy-preflight",
            "runner/pull-deploy/classify_deploy_impact.py",
            "runner/release/rozkalns-cv-deploy-main",
            "runner/release/rozkalns-cv-pull-deploy-main",
            'git hash-object "${installed_paths[$index]}"',
            "installed CV artifact does not match approved target",
        ):
            self.assertIn(marker, self.canary)

    def test_canary_has_exactly_one_explicit_production_sudo_boundary(self) -> None:
        self.assertEqual(self.canary.count("sudo -n"), 1)
        self.assertIn(
            'sudo -n "$PULL_HELPER" "$TARGET_SHA" "$EVIDENCE_DIR"',
            self.canary,
        )
        self.assertNotIn("rozkalns-cv-deploy-main \"$TARGET_SHA\"", self.canary)
        self.assertNotIn("github-cv-runner", self.canary)
        self.assertNotIn("GH_TOKEN", self.canary)
        self.assertNotIn("GITHUB_TOKEN", self.canary)

    def test_canary_requires_timer_disabled_before_and_after_mutation(self) -> None:
        for marker in (
            "recurring CV pull-deploy timer is enabled",
            "recurring CV pull-deploy timer is active",
            "recurring timer became enabled during canary",
            "recurring timer became active during canary",
            "TIMER_ENABLED_AFTER",
            "TIMER_ACTIVE_AFTER",
            "LEGACY_RUNNER_RETIREMENT_AUTHORIZED=false",
        ):
            self.assertIn(marker, self.canary)
        self.assertNotIn("systemctl enable", self.canary)
        self.assertNotIn("systemctl start", self.canary)

    def test_canary_evidence_is_bounded_and_requires_transaction_commit(self) -> None:
        for marker in (
            "rozkalns-cv-pull-deploy/evidence",
            "rozkalns-cv-main-deploy-canary-",
            "DEPLOY_RESULT",
            "FINAL_STATE_SHA",
            "PRODUCTION_CHANGED",
            "MUTATION_STARTED",
            "TRANSACTION_COMMITTED",
            "ROLLBACK_PERFORMED",
            "SHARED_INGRESS_CONTROLLED",
            "DATABASE_MIGRATIONS_EXECUTED",
            "CV_PRODUCTION_CANARY=PASS",
        ):
            self.assertIn(marker, self.canary)

    def test_canary_requires_transactional_public_contract_evidence(self) -> None:
        for marker in (
            "PUBLIC_SITE=PASS",
            "PUBLIC_MODULE_MIME=PASS",
            "PUBLIC_CACHE_IMMUTABLE=PASS",
            "PUBLIC_NOSNIFF=PASS",
            "PUBLIC_CSP_NONCE=PASS",
            "TRANSACTIONAL_PUBLIC_CONTRACTS=PASS",
        ):
            self.assertIn(marker, self.canary)

    def test_canary_preserves_legacy_helper_and_reconciles_readiness(self) -> None:
        for marker in (
            "/usr/local/sbin/rozkalns-cv-deploy-main",
            "LEGACY_HELPER_BEFORE",
            "LEGACY_HELPER_AFTER",
            "LEGACY_HELPER_MODIFIED=false",
            "/usr/local/sbin/rozkalns-cv-pull-deploy",
            "NO_OP_ALREADY_CURRENT",
            "READINESS_REASON",
            "CURRENT",
            "READINESS_RECONCILIATION=CURRENT",
        ):
            self.assertIn(marker, self.canary)

    def test_installer_only_installs_manual_canary_and_never_activates_it(self) -> None:
        for marker in (
            "ops/bin/rozkalns-cv-pull-deploy-canary",
            "DEST_CANARY='/usr/local/sbin/rozkalns-cv-pull-deploy-canary'",
            "RPi5_main checkout is not exact origin/main",
            "CV pull-deploy timer must remain disabled for canary installation",
            "CV pull-deploy timer must remain inactive for canary installation",
            "CV_PULL_DEPLOY_CANARY_INSTALL=PASS",
            "PRODUCTION_CHANGED=false",
            "DEPLOY_TRANSPORT_CHANGED=false",
            "LEGACY_RUNNER_CHANGED=false",
        ):
            self.assertIn(marker, self.installer)
        self.assertNotIn("systemctl enable", self.installer)
        self.assertNotIn("systemctl start", self.installer)
        self.assertNotIn("sudo ", self.installer)
        self.assertNotIn("rozkalns-cv-pull-deploy-main *", self.installer)


if __name__ == "__main__":
    unittest.main()
