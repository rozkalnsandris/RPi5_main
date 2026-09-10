#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/deploy/rpi5-main-weather-public-runtime-trusted-checkout-bootstrap.json"
INSTALL = ROOT / "ops/deploy/weather-public-runtime-helper-install.json"
EXECUTION = ROOT / "ops/deploy/weather-public-runtime-execution.json"
DOC = ROOT / "docs/WEATHER_PUBLIC_RUNTIME_EXECUTOR_SOURCE.md"
MAKEFILE = ROOT / "Makefile"

EXPECTED_SCHEMA = "rozkalns.rpi5-main.weather-public-runtime-trusted-checkout-bootstrap.v1"
EXPECTED_BASE = "95b6b95b132614cbc330d6d764d0557079a67534"
EXPECTED_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
TARGET = "RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-trusted"
AUTH_SHA = "EXPLICIT_COMPOSITE_STRICT_LIVE_EXACT_RPI5_MAIN_SHA"
CONTRACT_PATH = "ops/deploy/rpi5-main-weather-public-runtime-trusted-checkout-bootstrap.json"
SUCCESSOR_CONTRACT_PATH = "ops/deploy/rpi5-main-weather-public-runtime-install-trusted-checkout-bootstrap.json"
SUCCESSOR_TARGET = "RPi5_CHECKOUT_PARENT/RPi5_main-weather-public-runtime-install-trusted"
REQUIRED_PATHS = [
    "ops/deploy/weather-public-runtime-helper-install.json",
    "ops/deploy/weather-public-runtime-execution.json",
    "ops/deploy/weather-public-runtime-host-wiring.json",
    "ops/bin/rozkalns-weather-public-runtime-stage-helper",
]
FORBIDDEN = {
    "reset",
    "rebase",
    "clean",
    "checkout",
    "switch",
    "merge",
    "pull",
    "worktree remove",
    "worktree prune",
    "branch",
    "commit",
    "push",
    "force",
}


def validate_contract_shape(contract: dict) -> None:
    if contract.get("schema") != EXPECTED_SCHEMA:
        raise ValueError("schema")
    manager = contract.get("manager_checkout", {})
    trusted = contract.get("trusted_checkout", {})
    if manager.get("origin") != EXPECTED_ORIGIN:
        raise ValueError("origin")
    if manager.get("derivation") != "RPi5_CHECKOUT_PARENT/RPi5_main":
        raise ValueError("manager path")
    if trusted.get("derivation") != TARGET:
        raise ValueError("target")
    if trusted.get("expected_sha_authority") != AUTH_SHA:
        raise ValueError("sha authority")
    if trusted.get("minimum_reviewed_ancestor") != EXPECTED_BASE:
        raise ValueError("ancestor")
    if trusted.get("required_paths") != REQUIRED_PATHS:
        raise ValueError("post-create paths")
    mutations = contract.get("allowed_git_mutations", [])
    expected_mutations = [
        ["git", "fetch", "origin", "main"],
        ["git", "worktree", "add", "--detach", TARGET, AUTH_SHA],
    ]
    if [item.get("argv") for item in mutations] != expected_mutations:
        raise ValueError("mutation surface")
    if not FORBIDDEN.issubset(set(contract.get("forbidden_git_operations", []))):
        raise ValueError("forbidden git operations")


class WeatherTrustedCheckoutBootstrapContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT.read_text())
        cls.install = json.loads(INSTALL.read_text())
        cls.execution = json.loads(EXECUTION.read_text())
        cls.doc = DOC.read_text()
        cls.makefile = MAKEFILE.read_text()

    def test_identity_is_fixed_and_source_only(self) -> None:
        c = self.contract
        validate_contract_shape(c)
        self.assertEqual(c["repository"], "rozkalnsandris/RPi5_main")
        self.assertIs(c["source_only"], True)
        self.assertIs(c["trusted_checkout"]["must_be_absent_before_first_mutation"], True)
        self.assertEqual(c["trusted_checkout"]["expected_sha_format"], "LOWERCASE_40_HEX")
        self.assertIs(c["trusted_checkout"]["fresh_origin_main_must_equal_expected_sha"], True)

    def test_manager_checkout_can_be_dirty_and_detached_but_never_repaired(self) -> None:
        manager = self.contract["manager_checkout"]
        self.assertIs(manager["working_tree_content_may_be_dirty"], True)
        self.assertIs(manager["head_may_be_detached"], True)
        self.assertIs(manager["working_tree_content_mutation_allowed"], False)
        self.assertIs(manager["index_mutation_allowed"], False)
        self.assertIs(manager["head_advance_allowed"], False)
        self.assertTrue(FORBIDDEN.issubset(set(self.contract["forbidden_git_operations"])))

    def test_only_fetch_and_one_fixed_detached_worktree_are_represented(self) -> None:
        mutations = self.contract["allowed_git_mutations"]
        self.assertEqual([item["order"] for item in mutations], [1, 2])
        self.assertEqual(mutations[0]["argv"], ["git", "fetch", "origin", "main"])
        self.assertEqual(
            mutations[1]["argv"],
            ["git", "worktree", "add", "--detach", TARGET, AUTH_SHA],
        )
        self.assertTrue(all(item["working_tree_content_mutation"] is False for item in mutations))

    def test_wrong_identity_or_git_surface_fixture_is_rejected(self) -> None:
        mutations = {
            "manager_checkout.origin": "https://example.invalid/RPi5_main.git",
            "trusted_checkout.derivation": "RPi5_CHECKOUT_PARENT/other-target",
            "trusted_checkout.expected_sha_authority": "CALLER_SHA",
            "trusted_checkout.minimum_reviewed_ancestor": "0" * 40,
        }
        for dotted_key, value in mutations.items():
            with self.subTest(dotted_key=dotted_key):
                fixture = copy.deepcopy(self.contract)
                section, key = dotted_key.split(".", 1)
                fixture[section][key] = value
                with self.assertRaises(ValueError):
                    validate_contract_shape(fixture)
        fixture = copy.deepcopy(self.contract)
        fixture["allowed_git_mutations"][1]["argv"][4] = "RPi5_CHECKOUT_PARENT/injected"
        with self.assertRaises(ValueError):
            validate_contract_shape(fixture)

    def test_post_fetch_and_failure_semantics_are_fail_closed(self) -> None:
        gate = self.contract["post_fetch_gate"]
        self.assertIs(gate["require_origin_main_equals_expected_sha"], True)
        self.assertIs(gate["require_expected_sha_descends_from_minimum_reviewed_ancestor"], True)
        self.assertEqual(gate["main_drift_behavior"], "STOP_NO_WORKTREE_CREATION")
        failure = self.contract["failure"]
        self.assertTrue(
            all(
                failure[key] is False
                for key in (
                    "automatic_retry",
                    "automatic_cleanup",
                    "automatic_rollback",
                    "manager_repair",
                    "alternate_checkout_route",
                )
            )
        )
        self.assertEqual(failure["after_first_mutation_error"], "STOP_PRESERVE_READ_ONLY_EVIDENCE")

    def test_weather_postconditions_and_runtime_exclusions_are_frozen(self) -> None:
        self.assertEqual(self.contract["trusted_checkout"]["required_paths"], REQUIRED_PATHS)
        self.assertTrue(all(value is False for value in self.contract["safety"].values()))
        self.assertIs(self.contract["followup"]["merge_never_authorizes_live"], True)
        self.assertEqual(self.contract["followup"]["target_alias"], "rozkalns-weather-public-rpi5")
        self.assertEqual(
            self.contract["followup"]["operation_id"],
            "rozkalns-weather.public-runtime-release.v1",
        )

    def test_legacy_contract_is_preserved_but_current_surfaces_bind_successor(self) -> None:
        validate_contract_shape(self.contract)
        for surface in (self.install, self.execution):
            self.assertEqual(surface["trusted_checkout_bootstrap_contract"], SUCCESSOR_CONTRACT_PATH)
            self.assertEqual(surface["trusted_checkout_target"], SUCCESSOR_TARGET)
            self.assertNotEqual(surface["trusted_checkout_target"], TARGET)
            self.assertIs(surface["trusted_checkout_required_before_live_installation"], True)
            self.assertIs(surface["ordinary_manager_checkout_install_source_allowed"], False)

    def test_docs_and_validate_target_are_wired(self) -> None:
        self.assertIn("RPi5_main-weather-public-runtime-trusted", self.doc)
        self.assertIn(CONTRACT_PATH, self.doc)
        self.assertIn(SUCCESSOR_CONTRACT_PATH, self.doc)
        self.assertIn(SUCCESSOR_TARGET, self.doc)
        self.assertIn("evidence-only", self.doc)
        self.assertIn("git worktree add --detach", self.doc)
        self.assertIn(
            "python3 ./tests/test-rpi5-main-weather-public-runtime-trusted-checkout-bootstrap.py",
            self.makefile,
        )


if __name__ == "__main__":
    unittest.main()
