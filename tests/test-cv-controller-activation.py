from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "ops" / "bin" / "rozkalns-cv-controller-activate"
MAKEFILE = ROOT / "Makefile"


class CvControllerActivationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = OPERATOR.read_text(encoding="utf-8")

    def test_operator_is_registered_in_validation(self) -> None:
        makefile = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn(
            "python3 ./tests/test-cv-controller-activation.py",
            makefile,
        )

    def test_activation_is_pinned_to_recovered_cv_baseline(self) -> None:
        required = [
            "EXPECTED_CV_SHA='f5431265232f356fa27f6204f0cba56e1e730928'",
            "CV_MAIN_PRODUCTION_RECONCILIATION=PASS",
            "CV_EXACT_MAIN_CI=PASS",
            "CV_CONTROL_ARTIFACT_IDENTITY=PASS",
            "PHASE3_MAINTENANCE_POLICY_RECHECK=PASS",
            "PRE_ACTIVATION_RUNTIME_HEALTH=PASS",
        ]
        for marker in required:
            self.assertIn(marker, self.text)

    def test_exact_workflow_ci_is_required(self) -> None:
        self.assertIn(
            'actions/workflows/$workflow/runs?branch=main&head_sha=$sha&status=completed',
            self.text,
        )
        self.assertIn(
            'require_exact_main_ci "$RPI_REPOSITORY" "$rpi_head" rpi validate.yml',
            self.text,
        )
        self.assertIn(
            'require_exact_main_ci "$CV_REPOSITORY" "$EXPECTED_CV_SHA" cv ci.yml',
            self.text,
        )
        for job in (
            '"validate"',
            '"gitleaks"',
            '"public-automation-baseline / public automation policy"',
        ):
            self.assertIn(job, self.text)

    def test_only_reviewed_installer_crosses_host_artifact_boundary(self) -> None:
        self.assertEqual(
            self.text.count('bash "$repo/$INSTALLER_REL" "$repo"'),
            1,
        )
        for marker in (
            "CV_CONTROLLER_ARTIFACT_INSTALL=PASS",
            "POST_INSTALL_PREFLIGHT=NO_OP_ALREADY_CURRENT",
            "PHASE3_140_CONTROLLER_HOST_ACTIVATION=PASS",
            "PRODUCTION_MUTATION_AUTHORIZED=false",
            "PRODUCTION_MUTATION_ATTEMPTED=false",
        ):
            self.assertIn(marker, self.text)

        # Data-only references in arrays are allowed. Reject actual direct
        # command positions instead. Restrict whitespace to spaces/tabs so a
        # data-only array row cannot consume the following newline/`)` token.
        direct_controller = re.compile(
            r'(?m)^[ \t]*"\$DEST_CONTROLLER"[ \t]*(?:$|[<>|;&])'
        )
        direct_pull_wrapper = re.compile(
            r'(?m)^[ \t]*"\$PULL_WRAPPER"[ \t]+\S'
        )
        self.assertIsNone(
            direct_controller.search(self.text),
            msg="controller must not execute during activation",
        )
        self.assertIsNone(
            direct_pull_wrapper.search(self.text),
            msg="pull wrapper must not execute during activation",
        )

    def test_activation_does_not_enable_or_start_recurring_execution(self) -> None:
        forbidden = (
            r"systemctl\s+enable\b",
            r"systemctl\s+start\b",
            r"systemctl\s+restart\b",
            r"docker\s+compose\s+(?:up|pull|build|down|restart|create)\b",
            r"sudo\s+-n\s+.*PULL_(?:WRAPPER|HELPER)",
        )
        for pattern in forbidden:
            self.assertIsNone(
                re.search(pattern, self.text),
                msg=f"forbidden activation behavior matched: {pattern}",
            )

        self.assertIn(
            "CV pull timer must be disabled/inactive before #140 activation",
            self.text,
        )
        self.assertIn(
            "CV pull timer became enabled/active during #140 activation",
            self.text,
        )
        self.assertIn("CV_PULL_TIMER_ENABLED=", self.text)
        self.assertIn("CV_PULL_TIMER_ACTIVE=", self.text)

    def test_post_install_preflight_must_remain_non_mutating_current(self) -> None:
        self.assertIn(
            '[[ "$preflight_result" == NO_OP_ALREADY_CURRENT ]]',
            self.text,
        )
        self.assertIn(
            '[[ "$preflight_target" == "$EXPECTED_CV_SHA" && "$preflight_production" == "$EXPECTED_CV_SHA" ]]',
            self.text,
        )
        self.assertIn(
            "CV origin/main advanced during #140 activation",
            self.text,
        )
        self.assertIn(
            "CV production state changed during #140 activation",
            self.text,
        )

    def test_failed_post_install_proof_restores_previous_artifacts(self) -> None:
        for marker in (
            "backup_artifact()",
            "restore_artifact()",
            "CV_CONTROLLER_ACTIVATION_ROLLBACK=ATTEMPTED",
            'restore_artifact "$DEST_CONTROLLER" controller',
            'restore_artifact "$DEST_READINESS" readiness',
            'restore_artifact "$DEST_SERVICE" service',
            'restore_artifact "$DEST_TIMER" timer',
            'systemctl disable --now "$TIMER_UNIT"',
        ):
            self.assertIn(marker, self.text)

    def test_legacy_pull_policy_and_runtime_health_are_invariants(self) -> None:
        for marker in (
            "LEGACY_CV_HELPER_MODIFIED=false",
            "LEGACY_CV_RUNNER_RULE_MODIFIED=false",
            "PULL_SUDO_RULE_MODIFIED=false",
            "CV_PRODUCTION_CHANGED=false",
            "CVBOT_HEALTH=healthy",
            "LOCAL_SITE=PASS",
            "PUBLIC_SITE=PASS",
        ):
            self.assertIn(marker, self.text)


if __name__ == "__main__":
    unittest.main()
