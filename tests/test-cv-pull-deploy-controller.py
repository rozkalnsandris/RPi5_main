from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "ops" / "bin" / "rozkalns-cv-pull-deploy"
INSTALLER = ROOT / "scripts" / "install-cv-pull-deploy-readiness.sh"
SERVICE = ROOT / "ops" / "systemd" / "rozkalns-cv-pull-deploy.service"
TIMER = ROOT / "ops" / "systemd" / "rozkalns-cv-pull-deploy.timer"
READINESS = ROOT / "scripts" / "cv-deploy-readiness.py"


class CvPullDeployControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.controller = CONTROLLER.read_text(encoding="utf-8")
        cls.installer = INSTALLER.read_text(encoding="utf-8")
        cls.service = SERVICE.read_text(encoding="utf-8")
        cls.timer = TIMER.read_text(encoding="utf-8")
        cls.case_body = cls.controller.split('case "$RESULT" in', 1)[1]
        cls.non_ready_case = cls.case_body.split("    READY)", 1)[0]
        cls.ready_case = cls.case_body.split("    READY)", 1)[1].split("    *)", 1)[0]

    def test_shell_sources_parse(self) -> None:
        for path in (CONTROLLER, INSTALLER):
            completed = subprocess.run(
                ["bash", "-n", str(path)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout)

    def test_controller_has_exactly_one_auto_deploy_sudo_boundary(self) -> None:
        self.assertIn("/usr/local/sbin/rozkalns-cv-pull-deploy-preflight", self.controller)
        self.assertIn("/usr/local/libexec/rozkalns-cv/deploy-readiness", self.controller)
        self.assertIn("/usr/local/sbin/rozkalns-cv-pull-deploy-main", self.controller)
        self.assertEqual(
            self.controller.count('sudo -n "$PULL_HELPER" "$TARGET_SHA" "$EVIDENCE_DIR"'),
            1,
        )
        self.assertIn("PRODUCTION_MUTATION_AUTHORIZED=true", self.ready_case)
        self.assertIn("PRODUCTION_MUTATION_ATTEMPTED=true", self.ready_case)
        self.assertNotIn("systemctl ", self.controller)
        self.assertNotIn("docker ", self.controller)

    def test_non_ready_preflight_states_cannot_invoke_pull_helper(self) -> None:
        for marker in (
            "WAIT_CI",
            "MANUAL_ROLLOUT_REQUIRED",
            "DB_HOST_APPLY_REQUIRED",
            "NO_DEPLOY",
            "WAIT_HELPER_ACTIVATION",
            "WAIT_PULL_TRANSPORT_ACTIVATION",
            "PREFLIGHT_FAILED",
        ):
            self.assertIn(marker, self.controller)
        self.assertNotIn('sudo -n "$PULL_HELPER"', self.non_ready_case)
        self.assertNotIn("AUTO_DEPLOY_EXECUTION_GATE=PASS", self.non_ready_case)
        self.assertIn("flock -n 9", self.controller)
        self.assertIn("NO_OP_BUSY", self.controller)

    def test_transport_wait_states_remain_readiness_only(self) -> None:
        self.assertIn(
            "WAIT_HELPER_ACTIVATION|WAIT_PULL_TRANSPORT_ACTIVATION)",
            self.controller,
        )
        self.assertIn(
            "record_readiness \"$RESULT\" \"$TARGET_SHA\" \"$PRODUCTION_SHA\" 'AUTO_DEPLOY_SAFE' false \"$CI_RUN_ID\"",
            self.controller,
        )
        self.assertIn("DEPLOY_IMPACT='AUTO_DEPLOY_SAFE'", self.non_ready_case)
        self.assertIn("CONTROL_PLANE_CHANGED='false'", self.non_ready_case)

    def test_ready_path_revalidates_exact_main_ci_and_pull_artifacts_before_mutation(self) -> None:
        for marker in (
            "RECHECK_OUTPUT",
            "pre-mutation App-authenticated preflight recheck failed",
            "pre-mutation preflight is no longer READY",
            "origin/main advanced before mutation",
            "production state changed before mutation",
            "pre-mutation deploy impact changed",
            "pre-mutation control-plane flag changed",
            "pre-mutation exact-SHA CI run changed",
            "pre-mutation pull library identity changed",
            "pre-mutation pull wrapper identity changed",
            "AUTO_DEPLOY_EXECUTION_GATE=PASS",
        ):
            self.assertIn(marker, self.ready_case)
        self.assertIn("[[ \"$CONTROL_PLANE_CHANGED\" == false ]]", self.ready_case)
        self.assertIn("[[ \"$CI_RUN_ID\" =~ ^[1-9][0-9]*$ ]]", self.ready_case)
        self.assertIn("root:root:755", self.ready_case)

    def test_ready_path_requires_transactional_evidence_and_post_deploy_current(self) -> None:
        for marker in (
            "DEPLOY_RESULT",
            "FINAL_STATE_SHA",
            "PRODUCTION_CHANGED",
            "MUTATION_STARTED",
            "TRANSACTION_COMMITTED",
            "ROLLBACK_PERFORMED",
            "SHARED_INGRESS_CONTROLLED",
            "DATABASE_MIGRATIONS_EXECUTED",
            "PUBLIC_SITE=PASS",
            "PUBLIC_MODULE_MIME=PASS",
            "PUBLIC_CACHE_IMMUTABLE=PASS",
            "PUBLIC_NOSNIFF=PASS",
            "PUBLIC_CSP_NONCE=PASS",
            "NO_OP_ALREADY_CURRENT",
            "record_readiness 'CURRENT'",
            "TRANSACTIONAL_PUBLIC_CONTRACTS=PASS",
            "EVIDENCE_ID",
        ):
            self.assertIn(marker, self.ready_case)
        self.assertIn("record_readiness 'DEPLOY_FAILED'", self.controller)
        self.assertIn("PULL_DEPLOY_CONTROLLER_RESULT=DEPLOY_FAILED", self.ready_case)

    def test_service_runs_unprivileged_with_app_token_and_pull_helper_sudo_compatibility(self) -> None:
        self.assertIn("User=andris", self.service)
        self.assertIn("Group=andris", self.service)
        self.assertIn("NoNewPrivileges=false", self.service)
        self.assertIn("ExecStart=/usr/local/sbin/rozkalns-cv-pull-deploy", self.service)
        self.assertIn("ProtectSystem=full", self.service)
        self.assertNotIn("GH_CONFIG_DIR", self.service)
        self.assertNotIn("github-cv-runner", self.service)

    def test_timer_matches_reference_cadence_but_is_not_activated_by_source(self) -> None:
        for marker in (
            "OnBootSec=2min",
            "OnUnitActiveSec=2min",
            "AccuracySec=15s",
            "RandomizedDelaySec=10s",
            "Unit=rozkalns-cv-pull-deploy.service",
        ):
            self.assertIn(marker, self.timer)
        self.assertNotIn("systemctl enable", self.controller)

    def test_installer_forces_timer_disabled_and_does_not_touch_deploy_helper(self) -> None:
        self.assertIn(
            "systemctl disable --now rozkalns-cv-pull-deploy.timer",
            self.installer,
        )
        self.assertNotIn("systemctl enable", self.installer)
        self.assertNotIn("systemctl start rozkalns-cv-pull-deploy.service", self.installer)
        self.assertIn("DEPLOY_HELPER_MODIFIED=false", self.installer)
        self.assertIn("PRODUCTION_CHANGED=false", self.installer)
        self.assertNotIn("rozkalns-cv-deploy-main", self.installer)
        self.assertNotIn("/usr/local/sbin/rozkalns-cv-pull-deploy-main", self.installer)
        self.assertIn("/usr/local/sbin/rozkalns-cv-pull-deploy-preflight", self.installer)
        self.assertIn("/usr/local/libexec/rozkalns-cv/classify-deploy-impact", self.installer)
        self.assertIn("/usr/local/sbin/rozkalns-github-app-read-token", self.installer)

    def test_readiness_helper_is_separate_root_owned_install_target(self) -> None:
        self.assertTrue(READINESS.is_file())
        self.assertIn("/usr/local/libexec/rozkalns-cv/deploy-readiness", self.controller)
        self.assertIn("DEST_READINESS=\"$DEST_LIBEXEC/deploy-readiness\"", self.installer)


if __name__ == "__main__":
    unittest.main()
