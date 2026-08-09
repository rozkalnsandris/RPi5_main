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

    def test_controller_is_readiness_only(self) -> None:
        self.assertIn("/usr/local/sbin/rozkalns-cv-pull-deploy-preflight", self.controller)
        self.assertIn("/usr/local/libexec/rozkalns-cv/deploy-readiness", self.controller)
        self.assertIn("PRODUCTION_MUTATION_AUTHORIZED=false", self.controller)
        self.assertNotIn("rozkalns-cv-deploy-main", self.controller)
        self.assertNotIn("/usr/local/sbin/rozkalns-cv-pull-deploy-main", self.controller)
        self.assertNotIn("systemctl ", self.controller)
        self.assertNotIn("docker ", self.controller)
        self.assertNotIn("sudo ", self.controller)

    def test_controller_maps_fail_closed_preflight_states(self) -> None:
        for marker in (
            "WAIT_CI",
            "MANUAL_ROLLOUT_REQUIRED",
            "DB_HOST_APPLY_REQUIRED",
            "NO_DEPLOY",
            "WAIT_HELPER_ACTIVATION",
            "WAIT_PULL_TRANSPORT_ACTIVATION",
            "AUTO_DEPLOY_READY",
            "PREFLIGHT_FAILED",
        ):
            self.assertIn(marker, self.controller)
        self.assertIn("flock -n 9", self.controller)
        self.assertIn("NO_OP_BUSY", self.controller)

    def test_controller_keeps_legacy_and_pull_transport_waits_readiness_only(self) -> None:
        self.assertIn(
            "WAIT_HELPER_ACTIVATION|WAIT_PULL_TRANSPORT_ACTIVATION)",
            self.controller,
        )
        self.assertIn(
            "record_readiness \"$RESULT\" \"$TARGET_SHA\" \"$PRODUCTION_SHA\" 'AUTO_DEPLOY_SAFE' false \"$CI_RUN_ID\"",
            self.controller,
        )
        self.assertIn("DEPLOY_IMPACT='AUTO_DEPLOY_SAFE'", self.controller)
        self.assertIn("CONTROL_PLANE_CHANGED='false'", self.controller)
        self.assertNotIn("rozkalns-cv-pull-deploy-main \"$TARGET_SHA\"", self.controller)

    def test_service_runs_unprivileged_with_app_token_sudo_compatibility(self) -> None:
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
        self.assertIn("/usr/local/sbin/rozkalns-cv-pull-deploy-preflight", self.installer)
        self.assertIn("/usr/local/libexec/rozkalns-cv/classify-deploy-impact", self.installer)
        self.assertIn("/usr/local/sbin/rozkalns-github-app-read-token", self.installer)

    def test_readiness_helper_is_separate_root_owned_install_target(self) -> None:
        self.assertTrue(READINESS.is_file())
        self.assertIn("/usr/local/libexec/rozkalns-cv/deploy-readiness", self.controller)
        self.assertIn("DEST_READINESS=\"$DEST_LIBEXEC/deploy-readiness\"", self.installer)


if __name__ == "__main__":
    unittest.main()
