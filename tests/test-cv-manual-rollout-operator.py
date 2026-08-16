from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "ops" / "bin" / "rozkalns-cv-manual-rollout-operator"
INSTALLER = ROOT / "scripts" / "install-cv-manual-rollout-operator.sh"
CANARY = ROOT / "ops" / "bin" / "rozkalns-cv-pull-deploy-canary"
CONTROLLER = ROOT / "ops" / "bin" / "rozkalns-cv-pull-deploy"
TIMER = ROOT / "ops" / "systemd" / "rozkalns-cv-pull-deploy.timer"
SERVICE = ROOT / "ops" / "systemd" / "rozkalns-cv-pull-deploy.service"


class CvManualRolloutOperatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.operator = OPERATOR.read_text(encoding="utf-8")
        cls.installer = INSTALLER.read_text(encoding="utf-8")

    def test_shell_sources_parse(self) -> None:
        for path in (OPERATOR, INSTALLER):
            completed = subprocess.run(
                ["bash", "-n", str(path)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout)

    def test_operator_requires_exact_duplicate_manual_approval(self) -> None:
        for marker in (
            "--target-sha",
            "--approve-manual-rollout",
            '[[ "$APPROVED_SHA" == "$TARGET_SHA" ]]',
            "manual rollout approval does not match target SHA",
        ):
            self.assertIn(marker, self.operator)

    def test_operator_is_root_owned_interactive_boundary_without_new_sudoers(self) -> None:
        for marker in (
            "manual rollout operator must run as root via sudo",
            "/usr/local/sbin/rozkalns-cv-manual-rollout-operator",
            "root:root:755",
            "SUDOERS_CHANGED=false",
        ):
            self.assertIn(marker, self.operator + self.installer)
        self.assertNotIn("sudo -n", self.operator)
        self.assertNotIn("sudoers", self.operator.lower())

    def test_operator_pins_reviewed_runtime_artifacts(self) -> None:
        paths = {
            "CANARY": CANARY,
            "CONTROLLER": CONTROLLER,
            "TIMER": TIMER,
            "SERVICE": SERVICE,
        }
        for name, path in paths.items():
            match = re.search(
                rf"^EXPECTED_{name}_BLOB='([0-9a-f]{{40}})'$",
                self.operator,
                flags=re.MULTILINE,
            )
            self.assertIsNotNone(match, name)
            completed = subprocess.run(
                ["git", "hash-object", str(path)],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout)
            self.assertEqual(match.group(1), completed.stdout.strip(), name)

    def test_operator_accepts_only_coherent_initial_timer_states(self) -> None:
        self.assertIn("enabled/active)", self.operator)
        self.assertIn("disabled/inactive)", self.operator)
        self.assertIn("unexpected initial recurring timer state", self.operator)
        self.assertNotIn("enabled/inactive)", self.operator)
        self.assertNotIn("disabled/active)", self.operator)

    def test_operator_installs_exit_trap_before_pausing_timer(self) -> None:
        trap_index = self.operator.index("trap finalize EXIT")
        pause_index = self.operator.index('systemctl disable --now "$TIMER_UNIT"')
        self.assertLess(trap_index, pause_index)
        self.assertIn("RESTORE_RECURRING_TIMER=true", self.operator)
        self.assertIn('systemctl enable --now "$TIMER_UNIT"', self.operator)
        self.assertIn("TIMER_RESTORE_ATTEMPTED", self.operator)
        self.assertIn("FINAL_TIMER_ENABLED", self.operator)
        self.assertIn("FINAL_TIMER_ACTIVE", self.operator)

    def test_operator_waits_for_in_flight_service_before_canary(self) -> None:
        wait_index = self.operator.index('systemctl is-active --quiet "$SERVICE_UNIT"')
        canary_index = self.operator.index('    "$CANARY" \\\n')
        self.assertLess(wait_index, canary_index)
        self.assertIn("did not stop within 60 seconds", self.operator)

    def test_operator_delegates_production_mutation_only_to_existing_canary(self) -> None:
        self.assertIn('runuser -u "$OWNER" -- env', self.operator)
        self.assertIn('    "$CANARY" \\\n', self.operator)
        self.assertIn('--target-sha "$TARGET_SHA"', self.operator)
        self.assertIn('--approve-manual-rollout "$APPROVED_SHA"', self.operator)
        self.assertNotIn("rozkalns-cv-pull-deploy-main", self.operator)
        self.assertNotIn("current-sha", self.operator)
        self.assertNotIn("docker ", self.operator)

    def test_installer_is_source_only_and_never_toggles_or_executes_runtime(self) -> None:
        for marker in (
            "RPi5_main checkout is not exact origin/main",
            "RPi5_main checkout must remain on main",
            "RPi5_main checkout is not clean",
            "manual rollout operator artifact contract is stale",
            "CV_MANUAL_ROLLOUT_OPERATOR_INSTALL=PASS",
            "TIMER_STATE_CHANGED=false",
            "PRODUCTION_CHANGED=false",
            "DEPLOY_EXECUTED=false",
        ):
            self.assertIn(marker, self.installer)
        for forbidden in (
            "systemctl enable",
            "systemctl disable",
            "systemctl start",
            "systemctl stop",
            "rozkalns-cv-pull-deploy-canary --target",
            "rozkalns-cv-pull-deploy-main",
        ):
            self.assertNotIn(forbidden, self.installer)


if __name__ == "__main__":
    unittest.main()
