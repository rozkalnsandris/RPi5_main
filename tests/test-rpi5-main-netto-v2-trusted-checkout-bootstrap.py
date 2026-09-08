#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/deploy/rpi5-main-netto-v2-trusted-checkout-bootstrap.json"
DOC = ROOT / "docs/RPI5_MAIN_NETTO_V2_TRUSTED_CHECKOUT_BOOTSTRAP.md"
INSTALL_DOC = ROOT / "docs/HERMES_DEALS_NETTO_NONROOT_PREFLIGHT_V2_INSTALLATION.md"
WORKFLOW = ROOT / ".github/workflows/netto-v2-installer-contract.yml"

EXPECTED_BASE = "9bdab44ecdbdf016626cd50cb5b37d0ee265fb24"
EXPECTED_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
TARGET = "RPi5_CHECKOUT_PARENT/RPi5_main-netto-nonroot-preflight-v2-installer-trusted"


class TrustedCheckoutBootstrapContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT.read_text())
        cls.doc = DOC.read_text()
        cls.install_doc = INSTALL_DOC.read_text()
        cls.workflow = WORKFLOW.read_text()

    def test_identity_is_fixed_and_source_only(self) -> None:
        c = self.contract
        self.assertEqual(
            c["schema"],
            "rozkalns.rpi5-main.netto-v2-trusted-checkout-bootstrap.v1",
        )
        self.assertEqual(c["repository"], "rozkalnsandris/RPi5_main")
        self.assertIs(c["source_only"], True)
        self.assertEqual(c["manager_checkout"]["origin"], EXPECTED_ORIGIN)
        self.assertEqual(c["trusted_checkout"]["derivation"], TARGET)
        self.assertEqual(c["trusted_checkout"]["minimum_reviewed_ancestor"], EXPECTED_BASE)
        self.assertEqual(
            c["trusted_checkout"]["expected_sha_authority"],
            "EXPLICIT_COMPOSITE_LIVE_EXACT_RPI5_MAIN_SHA",
        )

    def test_only_two_reviewed_git_mutations_exist(self) -> None:
        mutations = self.contract["allowed_git_mutations"]
        self.assertEqual([item["order"] for item in mutations], [1, 2])
        self.assertEqual(mutations[0]["argv"], ["git", "fetch", "origin", "main"])
        self.assertEqual(
            mutations[1]["argv"],
            [
                "git",
                "worktree",
                "add",
                "--detach",
                TARGET,
                "EXPLICIT_COMPOSITE_LIVE_EXACT_RPI5_MAIN_SHA",
            ],
        )
        self.assertTrue(all(item["working_tree_content_mutation"] is False for item in mutations))

    def test_manager_checkout_never_gets_repaired(self) -> None:
        manager = self.contract["manager_checkout"]
        self.assertIs(manager["working_tree_content_may_be_dirty"], True)
        self.assertIs(manager["working_tree_content_mutation_allowed"], False)
        self.assertIs(manager["index_mutation_allowed"], False)
        self.assertIs(manager["head_advance_allowed"], False)
        forbidden = set(self.contract["forbidden_git_operations"])
        for name in {"reset", "rebase", "clean", "merge", "pull", "commit", "push", "force"}:
            self.assertIn(name, forbidden)

    def test_drift_and_failure_are_fail_closed(self) -> None:
        gate = self.contract["post_fetch_gate"]
        self.assertIs(gate["require_origin_main_equals_expected_sha"], True)
        self.assertIs(gate["require_expected_sha_descends_from_minimum_reviewed_ancestor"], True)
        self.assertEqual(gate["main_drift_behavior"], "STOP_NO_WORKTREE_CREATION")
        failure = self.contract["failure"]
        self.assertIs(failure["automatic_retry"], False)
        self.assertIs(failure["automatic_cleanup"], False)
        self.assertIs(failure["automatic_rollback"], False)

    def test_no_runtime_or_install_authority_is_added(self) -> None:
        safety = self.contract["safety"]
        self.assertTrue(all(value is False for value in safety.values()))
        self.assertIs(self.contract["followup"]["merge_never_authorizes_live"], True)

    def test_documentation_and_ci_are_wired(self) -> None:
        self.assertIn(EXPECTED_BASE, self.doc)
        self.assertIn("git fetch origin main", self.doc)
        self.assertIn("git worktree add --detach", self.doc)
        self.assertIn("RPi5_main-netto-nonroot-preflight-v2-installer-trusted", self.install_doc)
        self.assertIn(
            "ops/deploy/rpi5-main-netto-v2-trusted-checkout-bootstrap.json",
            self.workflow,
        )
        self.assertIn(
            "tests/test-rpi5-main-netto-v2-trusted-checkout-bootstrap.py",
            self.workflow,
        )
        self.assertIn(
            "python3 ./tests/test-rpi5-main-netto-v2-trusted-checkout-bootstrap.py",
            self.workflow,
        )


if __name__ == "__main__":
    unittest.main()
