#!/usr/bin/env python3
"""Fail-closed source-only SIMPLE-DEPLOY restoration design tests."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "ops/contracts/simple-deploy-timer-restoration-v1.json"
DOC = ROOT / "docs/SIMPLE_DEPLOY_TIMER_RESTORATION_V1.md"
REGISTRY = ROOT / "ops/deploy/simple-deploy-targets-v1.json"
SERVICE = ROOT / "ops/systemd/rozkalns-simple-deployer.service"
TIMER = ROOT / "ops/systemd/rozkalns-simple-deployer.timer"


class TimerRestorationDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = json.loads(POLICY.read_text(encoding="utf-8"))
        cls.registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        cls.doc = DOC.read_text(encoding="utf-8")

    def test_all_current_source_targets_in_scheduler_scope(self) -> None:
        p = self.policy
        self.assertEqual(p["schema"], "rpi5.simple-deploy.timer-restoration-design.v1")
        self.assertEqual(p["status"], "SOURCE_ONLY_NOT_INSTALLED_NO_RUNTIME_GUARD")
        self.assertTrue(self.registry["execution_enabled"])
        aliases = [t["target_alias"] for t in self.registry["targets"]]
        self.assertEqual(len(aliases), 5)
        self.assertEqual(len(aliases), len(set(aliases)))
        self.assertEqual(p["source"]["reviewed_targets"], aliases)
        self.assertTrue(p["source"]["registry_enabled"])
        self.assertEqual(p["source"]["invocation"], "--all")
        self.assertIn(" --all", SERVICE.read_text(encoding="utf-8"))

    def test_no_safe_window_and_no_implicit_live(self) -> None:
        self.assertIn("OnBootSec=2min", TIMER.read_text(encoding="utf-8"))
        self.assertIn("Persistent=true", TIMER.read_text(encoding="utf-8"))
        t = self.policy["timer"]
        self.assertTrue(t["onboot_elapsed_can_trigger_immediate"])
        self.assertIs(t["safe_delay_after_start_assumed"], False)
        self.assertEqual(t["pre_live_state"], "DISABLED_INACTIVE_DEAD")
        self.assertTrue(t["no_pending_reload"])
        self.assertTrue(t["separate_enable_start_live_required"])
        self.assertTrue(t["no_runtime_registry_override"])
        self.assertTrue(t["no_timer_or_service_source_modification"])
        self.assertTrue(self.policy["decision"]["no_implicit_merge_or_live"])
        self.assertTrue(self.policy["decision"]["no_automatic_retry_rollback_cleanup"])

    def test_mandatory_gates_default_block(self) -> None:
        decision = self.policy["decision"]
        self.assertEqual(decision["default"], "BLOCKED_NO_START")
        self.assertEqual(decision["failure_disposition"], "BLOCKED_NO_START")
        self.assertEqual(decision["standing_reconciliation_scope"], "ALL_INSTALLED_TARGETS")
        self.assertEqual(len(decision["required_gates"]), 9)
        self.assertEqual(len(set(decision["required_gates"])), 9)
        for marker in (
            "ALL_INSTALLED_TARGETS_REVIEWED_AND_ADOPTED",
            "OCI_POINTER_VERIFIED_AFTER_ANONYMOUS_CHALLENGE",
            "NO_PENDING_MUTATION_AT_HANDOFF",
            "EXACT_SEPARATE_OWNER_LIVE_AUTHORIZATION",
        ):
            self.assertIn(marker, decision["required_gates"])
            self.assertIn(marker, self.doc)

    def test_no_failed_target_or_unknown_pointer_bypass(self) -> None:
        t = self.policy["target_acceptance"]
        self.assertEqual(t["permitted_current_status"], ["SUCCESS", "NO_OP_CURRENT"])
        for name in (
            "compose_source_and_installed_hash_must_match",
            "first_adoption_requires_separate_owner_live",
            "blocked_must_equal_false",
            "no_prior_stop_error",
            "no_unresolved_pre_mutation_failure",
            "valid_last_success_receipt_required",
            "pointer_digest_must_equal_receipt",
            "current_health_readiness_evidence_required",
            "unknown_is_blocked",
        ):
            self.assertTrue(t[name])
        pointer = self.policy["pointer"]
        self.assertEqual(pointer["initial_http_401"], "AUTH_CHALLENGE_NOT_DIGEST_EVIDENCE")
        self.assertEqual(pointer["unknown_or_failed_resolution"], "BLOCKED_NO_START")
        self.assertTrue(pointer["credential_read_forbidden"])
        self.assertTrue(pointer["raw_auth_headers_or_tokens_publication_forbidden"])
        self.assertTrue(pointer["no_docker_execution_in_this_design"])
        self.assertEqual(pointer["concurrent_publisher_race"], "BLOCK_UNLESS_EXPLICIT_STANDING_DEPLOY_RISK")

    def test_privacy_and_source_only_decision_boundary(self) -> None:
        b = self.policy["publication_boundary"]
        for field in ("no_raw_config_logs_secrets", "only_sanitized_status_and_digest_comparison",
                      "no_runtime_or_docker_or_systemd_mutation"):
            self.assertTrue(b[field])
        for marker in ("SOURCE-ONLY", "HTTP 401", "COMPOSE_CONTRACT_INVALID",
                       "POINTER_RESOLUTION_FAILED", "BLOCKED_NO_START",
                       "Production deploy/change REQUIRED: NO"):
            self.assertIn(marker, self.doc)
        for private_literal in ("192.168.", "10.0.0.", "HOME_LAT", "HOME_LON", "token="):
            self.assertNotIn(private_literal, self.doc)


if __name__ == "__main__":
    unittest.main()
