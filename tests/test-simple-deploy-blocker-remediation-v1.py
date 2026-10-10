#!/usr/bin/env python3
"""Cross-contract, source-only regression for five-target #60 blocker design."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "ops/contracts/simple-deploy-blocker-remediation-v1.json"
DOC = ROOT / "docs/SIMPLE_DEPLOY_BLOCKER_REMEDIATION_V1.md"
PARENT = ROOT / "ops/contracts/simple-deploy-timer-restoration-v1.json"
V2 = ROOT / "ops/contracts/simple-deploy-hermes-prerequisite-materialization-v2.json"
V3 = ROOT / "ops/contracts/simple-deploy-hermes-prerequisite-materialization-v3.json"
TECH = ROOT / "ops/deploy/hermes-tech-simple-deploy-cutover-v1.json"
REGISTRY = ROOT / "ops/deploy/simple-deploy-targets-v1.json"
EXE = ROOT / "ops/lib/deploy_executor/simple_deploy_v1.py"
MAKEFILE = ROOT / "Makefile"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class BlockerRemediationDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.p = load(POLICY)
        cls.doc = DOC.read_text(encoding="utf-8")
        cls.registry = load(REGISTRY)
        cls.parent = load(PARENT)

    def test_additive_default_deny_no_live(self) -> None:
        p = self.p
        self.assertEqual(p["schema"], "rpi5.simple-deploy.blocker-remediation-design.v1")
        self.assertEqual(p["status"], "SOURCE_ONLY_DEFAULT_DENY_NO_EXECUTOR_NO_LIVE")
        self.assertEqual(p["decision"]["default"], "BLOCKED_NO_TIMER_START")
        for key in ("all_five_required", "do_not_skip_failed_targets",
                    "do_not_change_installed_registry", "source_merge_is_not_live"):
            self.assertIs(p["decision"][key], True)
        self.assertTrue(all(value is False for value in p["authority"].values()))
        self.assertEqual(self.parent["decision"]["default"], "BLOCKED_NO_START")
        self.assertEqual(len(self.parent["decision"]["required_gates"]), 9)
        self.assertEqual(self.parent["source"]["invocation"], "--all")
        self.assertEqual(len(self.registry["targets"]), 5)
        self.assertEqual(self.p["evidence"]["source_sha"].__len__(), 40)
        self.assertTrue(self.p["evidence"]["snapshot_only"])

    def test_shared_weather_parent_must_not_be_reowned(self) -> None:
        deals = self.p["hermes_deals"]
        shared = deals["shared_parent"]
        conflict = deals["legacy_conflict"]
        self.assertEqual(shared["path"], "/etc/rozkalns-simple-deployer/private")
        self.assertEqual((shared["observed_owner"], shared["observed_group"], shared["observed_mode"]),
                         ("root", "rozkalns-simple-deployer", "0750"))
        self.assertEqual((conflict["legacy_owner"], conflict["legacy_group"], conflict["legacy_mode"]),
                         ("root", "root", "0700"))
        self.assertTrue(conflict["incompatible_with_installed_weather_parent"])
        self.assertTrue(shared["no_chown_chmod_or_replace"])
        self.assertTrue(shared["weather_requires_preservation"])
        self.assertEqual(load(V2)["destination"]["modes"]["private_root"], "0700")
        self.assertEqual(load(V3)["inherits"]["phase_b_parent_and_publication_semantics_from"],
                         "ops/contracts/simple-deploy-hermes-prerequisite-materialization-v2.json")
        for key, value in deals["future_contract_requirements"].items():
            self.assertTrue(value, key)
        self.assertEqual(deals["snapshot"]["prerequisites"], "NOT_READY")

    def test_hermes_tech_404_is_pre_cutover_only(self) -> None:
        tech = self.p["hermes_tech"]
        cutover = load(TECH)
        registry = next(x for x in self.registry["targets"]
                        if x["target_alias"] == tech["target"])
        self.assertFalse(cutover["execution_enabled"])
        self.assertEqual(tech["baseline"]["liveness_http"], 404)
        self.assertEqual(tech["baseline"]["readiness_http"], 404)
        self.assertTrue(tech["before_cutover"]["legacy_404_is_not_post_cutover_failure"])
        self.assertTrue(tech["before_cutover"]["no_parallel_port_ownership"])
        self.assertTrue(tech["before_cutover"]["do_not_disable_legacy_units_in_source_lanes"])
        self.assertEqual(tech["after_separate_authorized_cutover"]["required_liveness_status"], 200)
        self.assertEqual(tech["after_separate_authorized_cutover"]["required_readiness_status"], 200)
        self.assertEqual(cutover["verification"]["required_http_status"], 200)
        self.assertEqual(registry["health"]["liveness_url"], cutover["verification"]["liveness_url"])
        self.assertEqual(registry["health"]["readiness_url"], cutover["verification"]["readiness_url"])
        self.assertTrue(tech["after_separate_authorized_cutover"]["no_automatic_recovery"])

    def test_cv_unknown_failure_cannot_be_inferred_from_oci(self) -> None:
        cv = self.p["cv"]
        self.assertEqual(cv["pointer_failure"], "POINTER_RESOLUTION_FAILED")
        self.assertIs(cv["last_mutation_started"], False)
        self.assertEqual(cv["persisted_failure_subclass"], "NOT_PRESENT_IN_LAST_STATUS")
        self.assertEqual(cv["anonymous_oci"]["scoped_pull_head"], "SUCCESS")
        self.assertEqual(cv["anonymous_oci"]["production_digest_compared_to_last_success_receipt"], "DIFF")
        self.assertTrue(cv["buildx"]["no_docker_execution_in_this_design"])
        self.assertTrue(cv["buildx"]["presence_does_not_prove_cli_runtime"])
        self.assertTrue(cv["future_diagnostics"]["forbid_raw_stderr_or_auth_headers"])
        self.assertTrue(cv["future_diagnostics"]["no_reconcile_as_diagnostic"])
        self.assertTrue(cv["future_diagnostics"]["do_not_promote_pointer_diff_to_deploy_approval"])
        source = EXE.read_text(encoding="utf-8")
        self.assertIn("def _classify_pointer_stderr", source)
        self.assertIn('"POINTER_RESOLUTION_FAILED"', source)
        self.assertIn('"{{json .Manifest}}"', source)
        self.assertEqual(len(set(cv["future_diagnostics"]["allowlisted_classes"])), 10)

    def test_privacy_docs_ci_and_no_source_executor(self) -> None:
        for key, value in self.p["privacy"].items():
            self.assertTrue(value, key)
        for marker in ("BLOCKED_NO_TIMER_START", "root:rozkalns-simple-deployer",
                       "root:root", "0750", "0700", "HTTP **404**",
                       "POST", "POINTER_RESOLUTION_FAILED", "Production deploy/change REQUIRED: NO"):
            if marker == "POST":
                continue
            self.assertIn(marker, self.doc)
        for forbidden in ("192.168.", "HOME_LAT", "HOME_LON", "token=", "POSTGRES_PASSWORD="):
            self.assertNotIn(forbidden, self.doc)
        recipe = "\tpython3 ./tests/test-simple-deploy-blocker-remediation-v1.py"
        self.assertEqual(MAKEFILE.read_text(encoding="utf-8").count(recipe), 1)
        self.assertIn("validate: test secret-scan public-safety",
                      MAKEFILE.read_text(encoding="utf-8"))
        self.assertIn("docs/SIMPLE_DEPLOY_BLOCKER_REMEDIATION_V1.md",
                      (ROOT / "docs/SIMPLE_DEPLOY_TIMER_RESTORATION_V1.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
