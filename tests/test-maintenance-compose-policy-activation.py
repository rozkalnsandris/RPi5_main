from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "ops" / "bin" / "rpi5-maintenance-compose-policy-activate"
POLICY = ROOT / "ops" / "lib" / "rpi5-update-compose-policy.sh"


class MaintenanceComposePolicyActivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = OPERATOR.read_text(encoding="utf-8")
        subprocess.run(["bash", "-n", str(OPERATOR)], check=True)
        subprocess.run(["bash", "-n", str(POLICY)], check=True)

    def test_operator_is_helper_only_and_non_deploying(self) -> None:
        required = (
            "POLICY_DEST='/usr/local/lib/rpi5-maintenance/rpi5-update-compose-policy.sh'",
            "UPDATER_DEST='/usr/local/sbin/rpi5-update'",
            'install -o root -g root -m 0644 "$policy_source" "$POLICY_DEST"',
            "WEEKLY_UPDATER_MODIFIED=false",
            "WEEKLY_UPDATER_EXECUTED=false",
            "CV_PRODUCTION_CHANGED=false",
            "LEGACY_CV_HELPER_MODIFIED=false",
            "PHASE3_MAINTENANCE_POLICY_HOST_GATE=PASS",
        )
        for marker in required:
            self.assertIn(marker, self.source)

        forbidden_patterns = (
            r"docker\s+compose\s+(?:up|pull|build|down|restart|create)\b",
            r"systemctl\s+(?:start|restart|enable|disable|stop)\b",
            r'\$UPDATER_DEST(?:"|\s)*$',
            r'\$LEGACY_CV_HELPER(?:"|\s)*$',
            r"rozkalns-cv-pull-deploy-main\s+[0-9a-f$]",
        )
        for pattern in forbidden_patterns:
            self.assertIsNone(re.search(pattern, self.source, re.MULTILINE), pattern)

        self.assertNotIn('install -o root -g root -m 0750 "$updater_source"', self.source)
        self.assertNotIn("--allow-persistent-catchup", self.source)

    def test_operator_requires_exact_clean_current_main_and_ci(self) -> None:
        for marker in (
            '[[ "$(owner_git branch --show-current)" == main ]]',
            'owner_git status --porcelain=v1 --untracked-files=all',
            "owner_git fetch --prune origin main",
            'head_sha="$(owner_git rev-parse HEAD)"',
            'remote_sha="$(owner_git rev-parse refs/remotes/origin/main)"',
            '[[ "$head_sha" == "$remote_sha" ]]',
            "--repository \"$REPOSITORY\"",
            "head_sha=$head_sha",
            'row.get("event") == "push"',
            'row.get("head_branch") == "main"',
            'row.get("head_sha") == sha',
            '"validate"',
            '"gitleaks"',
            '"public-automation-baseline / public automation policy"',
            "RPI5_MAIN_EXACT_SHA_CI=PASS",
        ):
            self.assertIn(marker, self.source)

        self.assertIn(
            "unset app_token runs_json jobs_json GH_TOKEN GITHUB_TOKEN",
            self.source,
        )
        self.assertNotIn("echo \"$app_token\"", self.source)
        self.assertNotIn("printf '%s' \"$app_token\"", self.source)

    def test_operator_rolls_back_only_policy_on_post_install_failure(self) -> None:
        for marker in (
            "policy_installed=false",
            "had_previous_policy=false",
            'backup="$work/previous-policy"',
            "restore_policy()",
            'if (( rc != 0 )) && [[ "$policy_installed" == true ]]',
            'install -o root -g root -m 0644 "$backup" "$POLICY_DEST"',
            'rm -f -- "$POLICY_DEST"',
            "trap 'rc=$?; restore_policy \"$rc\"; exit \"$rc\"' EXIT",
            "policy_installed=true",
            "policy_installed=false",
        ):
            self.assertIn(marker, self.source)

    def test_live_proof_is_read_only_and_buildable_aware(self) -> None:
        for marker in (
            'source "$POLICY_DEST"',
            'rpi5_select_compose_update_targets "$cv_project_dir"',
            'contains_value cvbot "${RPI5_COMPOSE_BUILDABLE_SERVICES[@]}"',
            'contains_value cvbot "${RPI5_COMPOSE_CHANGED_REGISTRY_SERVICES[@]}"',
            'rpi5_build_compose_up_args 240 false "$cv_project_dir"',
            'contains_value --no-build "${RPI5_COMPOSE_UP_ARGS[@]}"',
            'contains_value --no-deps "${RPI5_COMPOSE_UP_ARGS[@]}"',
            "CVBOT_CLASSIFICATION=buildable-local",
            "CVBOT_GENERIC_RECREATE_AUTHORIZED=false",
            "COMPOSE_POLICY_LIVE_READONLY_PROOF=PASS",
        ):
            self.assertIn(marker, self.source)

    def test_operator_preserves_runtime_and_timer_boundaries(self) -> None:
        for marker in (
            "CV_STATE='/var/lib/rozkalns-cv-deploy/current-sha'",
            "LEGACY_CV_HELPER='/usr/local/sbin/rozkalns-cv-deploy-main'",
            "CV_PULL_TIMER='rozkalns-cv-pull-deploy.timer'",
            "MAINTENANCE_TIMER='rpi5-update.timer'",
            '[[ "$cv_timer_enabled_before" != enabled && "$cv_timer_active_before" != active ]]',
            '[[ "$installed_updater_after" == "$installed_updater_before" ]]',
            '[[ "$legacy_helper_after" == "$legacy_helper_before" ]]',
            '[[ "$production_after" == "$production_before" ]]',
            '[[ "$cv_timer_enabled_after" == "$cv_timer_enabled_before" ]]',
            '[[ "$cv_timer_active_after" == "$cv_timer_active_before" ]]',
            '[[ "$maintenance_timer_enabled_after" == "$maintenance_timer_enabled_before" ]]',
            '[[ "$maintenance_timer_active_after" == "$maintenance_timer_active_before" ]]',
        ):
            self.assertIn(marker, self.source)


if __name__ == "__main__":
    unittest.main()
