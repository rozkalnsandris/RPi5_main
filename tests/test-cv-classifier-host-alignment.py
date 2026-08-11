from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "scripts" / "activate-cv-classifier-baseline.sh"
MAKEFILE = ROOT / "Makefile"


class CVClassifierHostAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = OPERATOR.read_text(encoding="utf-8")

    def test_operator_is_registered_and_parses_as_bash(self) -> None:
        makefile = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn(
            "python3 ./tests/test-cv-classifier-host-alignment.py",
            makefile,
        )
        subprocess.run(["bash", "-n", str(OPERATOR)], check=True)

    def test_operator_is_exactly_pinned_to_152_alignment(self) -> None:
        required = [
            "TARGET_CV_SHA='4a0069a97022841da07a687a197ea8cfacc56cd6'",
            "EXPECTED_PRODUCTION_SHA='f5431265232f356fa27f6204f0cba56e1e730928'",
            "OLD_CLASSIFIER_BLOB='e9020c00328122a1a028c9734002f0ea1c956f2f'",
            "TARGET_CLASSIFIER_BLOB='7fb09d469eaeb574b2bba39474cc7a6bb55504da'",
            "TARGET_PREFLIGHT_BLOB='2592e4e38e933f01409d5816c05defd22e661f6c'",
            "TARGET_PULL_LIBRARY_BLOB='ade60abbfea3cf56b1a56bbc1b2e0669b1a1b983'",
            "TARGET_PULL_WRAPPER_BLOB='ddaa8c7f8c0776e77be18b2cd5ea8a9489900e70'",
        ]
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.text)

    def test_operator_requires_exact_main_ci_for_both_repositories(self) -> None:
        for marker in (
            "require_exact_main_ci",
            'row.get("event") == "push"',
            'row.get("head_branch") == "main"',
            'row.get("head_sha") == sha',
            '"validate", "gitleaks", "public-automation-baseline / public automation policy"',
            'else {"validate"}',
            'require_exact_main_ci "$RPI_REPOSITORY" "$rpi_head" rpi validate.yml',
            'require_exact_main_ci "$CV_REPOSITORY" "$TARGET_CV_SHA" cv ci.yml',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.text)

    def test_only_classifier_is_installed_and_has_rollback(self) -> None:
        self.assertIn(
            'install -o root -g root -m 0755 "$candidate" "$CLASSIFIER"',
            self.text,
        )
        self.assertIn(
            'install -o root -g root -m 0755 "$backup" "$CLASSIFIER"',
            self.text,
        )
        self.assertIn("CV_CLASSIFIER_ALIGNMENT_ROLLBACK=PASS", self.text)
        self.assertIn("CV_CLASSIFIER_ARTIFACT_INSTALL=PASS", self.text)
        for forbidden in (
            'install -o root -g root -m 0755 "$candidate" "$PREFLIGHT"',
            'install -o root -g root -m 0755 "$candidate" "$PULL_LIBRARY"',
            'install -o root -g root -m 0755 "$candidate" "$PULL_WRAPPER"',
        ):
            self.assertNotIn(forbidden, self.text)

    def test_post_install_preflight_must_remain_manual_and_non_mutating(self) -> None:
        for marker in (
            '[[ "$preflight_result" == MANUAL_ROLLOUT_REQUIRED ]]',
            '[[ "$deploy_impact" == MANUAL_ROLLOUT_REQUIRED ]]',
            '[[ "$control_changed" == true ]]',
            '[[ "$mutation_authorized" == false ]]',
            "POST_ALIGNMENT_PREFLIGHT=MANUAL_ROLLOUT_REQUIRED",
            "CONTROL_PLANE_CHANGED=true",
            "PRODUCTION_MUTATION_AUTHORIZED=false",
            "CV_PRODUCTION_CHANGED=false",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.text)

    def test_timer_service_runtime_and_legacy_are_invariants(self) -> None:
        for marker in (
            "TIMER_UNIT='rozkalns-cv-pull-deploy.timer'",
            "SERVICE_UNIT='rozkalns-cv-pull-deploy.service'",
            '[[ "$pre_timer_enabled" != enabled ]]',
            '[[ "$pre_timer_active" != active ]]',
            '[[ "$pre_service_active" != active ]]',
            "LEGACY_CV_HELPER_MODIFIED=false",
            "PULL_TRANSPORT_MODIFIED=false",
            "CVBOT_HEALTH=healthy",
            "LOCAL_SITE=PASS",
            "PUBLIC_SITE=PASS",
            "PHASE3_163_CLASSIFIER_HOST_ALIGNMENT=PASS",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.text)

    def test_operator_never_invokes_production_or_maintenance_execution(self) -> None:
        for forbidden in (
            'sudo -n "$PULL_WRAPPER"',
            "rozkalns-cv-pull-deploy-canary --target-sha",
            "rpi5-update.sh",
            "rpi5-update-controlled.sh",
            "systemctl enable",
            "systemctl start",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.text)


if __name__ == "__main__":
    unittest.main()
