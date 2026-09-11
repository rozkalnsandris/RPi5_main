#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from hermes_publisher_guard import (  # noqa: E402
    ObservedPublication,
    PublicationGuardError,
    PublicationSpec,
    validate_publication,
)

CONTRACT = ROOT / "ops/contracts/existing-issue-source-hardening-v1.json"


class BundleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(CONTRACT.read_text())

    def test_top_level_contract_is_exact_and_live_disabled(self) -> None:
        self.assertEqual(
            set(self.data),
            {
                "schema_version",
                "contract",
                "implementation_issue",
                "status",
                "jobs",
                "host_gap_map",
                "publisher_boundary",
                "cloudflare_compensating_controls",
                "m2m_endpoint_classes",
                "mqtt_legacy_credential_migration",
                "mutation",
            },
        )
        self.assertEqual(self.data["implementation_issue"], 464)
        self.assertEqual(self.data["status"], "SOURCE_ONLY_BUNDLE_READY_LIVE_DISABLED")
        self.assertTrue(all(value is False for key, value in self.data["mutation"].items() if key != "production_mutation_started"))
        self.assertFalse(self.data["mutation"]["production_mutation_started"])

    def test_all_ten_jobs_have_deterministic_result(self) -> None:
        jobs = self.data["jobs"]
        self.assertEqual([job["job"] for job in jobs], list(range(1, 11)))
        self.assertEqual(
            [job["issue"] for job in jobs],
            [453, 27, 93, 110, 117, 177, 179, 206, 207, 189],
        )
        allowed = {"DONE", "SOURCE_READY_LIVE_LATER", "SKIPPED_SUPERSEDED"}
        self.assertTrue(all(job["result"] in allowed and job["evidence"] for job in jobs))

    def test_existing_source_evidence_paths_exist(self) -> None:
        for job in self.data["jobs"]:
            for evidence in job["evidence"]:
                if "/" in evidence:
                    self.assertTrue((ROOT / evidence).exists(), evidence)

    def test_host_gap_map_is_bounded(self) -> None:
        gaps = self.data["host_gap_map"]
        self.assertEqual(len(gaps), 8)
        self.assertEqual(len({gap["id"] for gap in gaps}), 8)
        self.assertTrue(all(gap["state"].startswith("OPEN_") for gap in gaps))
        self.assertTrue(all("future_gate" in gap and "required_evidence" in gap for gap in gaps))

    def test_publisher_boundary_adds_no_generic_authority(self) -> None:
        publisher = self.data["publisher_boundary"]
        for key in (
            "raw_write_credential_visible_to_runtime",
            "generic_git_authority",
            "generic_ssh_authority",
            "generic_shell_authority",
            "production_wiring_enabled",
            "credential_placement_enabled",
            "real_push_enabled",
        ):
            self.assertFalse(publisher[key])
        self.assertIn("remote_main_race_guard", publisher["required_checks"])
        self.assertIn("fast_forward_only_intent", publisher["required_checks"])

    def test_cloudflare_controls_are_proposals_only(self) -> None:
        model = self.data["cloudflare_compensating_controls"]
        self.assertFalse(model["bot_fight_mode_dependency"])
        self.assertFalse(model["live_apply_enabled"])
        self.assertEqual(set(model["forbidden_primary_identity"]), {"dynamic_cloud_runner_ip", "user_agent"})
        for proposal in model["proposals"]:
            self.assertTrue(proposal["methods"])
            self.assertTrue(proposal["rationale"])
            self.assertTrue(proposal["rollback"].startswith("remove_exact_rule"))

    def test_m2m_endpoint_classes_are_bounded(self) -> None:
        classes = {item["class"]: item for item in self.data["m2m_endpoint_classes"]}
        self.assertEqual(set(classes), {"provider_webhook", "service_auth_api", "readonly_health"})
        self.assertIn("hmac", classes["provider_webhook"]["auth"])
        for item in classes.values():
            self.assertFalse(item["raw_request_logging"])
            self.assertTrue(item["methods"])
            self.assertTrue(item["body_limit_required"])
            self.assertTrue(item["timeout_required"])

    def test_mqtt_contract_keeps_live_actions_disabled(self) -> None:
        mqtt = self.data["mqtt_legacy_credential_migration"]
        self.assertFalse(mqtt["credential_values_in_git"])
        self.assertFalse(mqtt["credential_values_in_argv"])
        self.assertFalse(mqtt["mqtt_publish_authorized"])
        self.assertFalse(mqtt["service_restart_authorized"])
        self.assertFalse(mqtt["legacy_revocation_authorized"])
        self.assertTrue(mqtt["rollback_requires_predeclared_per_consumer_plan"])


class PublisherGuardTests(unittest.TestCase):
    def spec(self, **changes: object) -> PublicationSpec:
        data = dict(
            expected_repository="rozkalnsandris/hermes-tech",
            expected_branch="main",
            expected_base_sha="a" * 40,
            expected_publication_sha="b" * 40,
            expected_parent_sha="a" * 40,
            expected_subject="publish generated content",
            expected_changed_paths=("generated/a.json", "generated/b.json"),
            expected_remote_main_sha="a" * 40,
        )
        data.update(changes)
        return PublicationSpec(**data)

    def observed(self, **changes: object) -> ObservedPublication:
        data = dict(
            repository="rozkalnsandris/hermes-tech",
            branch="main",
            base_sha="a" * 40,
            publication_sha="b" * 40,
            parent_sha="a" * 40,
            subject="publish generated content",
            changed_paths=("generated/b.json", "generated/a.json"),
            remote_main_sha="a" * 40,
        )
        data.update(changes)
        return ObservedPublication(**data)

    def test_valid_request_is_source_validated_without_push(self) -> None:
        result = validate_publication(self.spec(), self.observed())
        self.assertEqual(result["decision"], "SOURCE_VALIDATED_NO_PUSH")
        self.assertFalse(result["network_push_executed"])
        self.assertTrue(result["fast_forward_only_intent"])
        self.assertTrue(result["post_push_exact_sha_required"])

    def test_rejects_remote_main_race(self) -> None:
        with self.assertRaisesRegex(PublicationGuardError, "remote_main"):
            validate_publication(self.spec(), self.observed(remote_main_sha="c" * 40))

    def test_rejects_changed_path_drift(self) -> None:
        with self.assertRaisesRegex(PublicationGuardError, "changed_paths_mismatch"):
            validate_publication(self.spec(), self.observed(changed_paths=("generated/a.json", "unexpected.py")))

    def test_rejects_parent_or_subject_drift(self) -> None:
        with self.assertRaises(PublicationGuardError):
            validate_publication(self.spec(), self.observed(parent_sha="c" * 40))
        with self.assertRaisesRegex(PublicationGuardError, "subject_mismatch"):
            validate_publication(self.spec(), self.observed(subject="different"))

    def test_rejects_unsafe_and_duplicate_paths(self) -> None:
        with self.assertRaises(PublicationGuardError):
            validate_publication(self.spec(expected_changed_paths=("../secret",)), self.observed(changed_paths=("../secret",)))
        with self.assertRaises(PublicationGuardError):
            validate_publication(self.spec(expected_changed_paths=("a", "a")), self.observed(changed_paths=("a", "a")))

    def test_rejects_wrong_repository_branch_and_sha_shape(self) -> None:
        with self.assertRaisesRegex(PublicationGuardError, "repository_mismatch"):
            validate_publication(self.spec(), self.observed(repository="other/repo"))
        with self.assertRaisesRegex(PublicationGuardError, "branch_mismatch"):
            validate_publication(self.spec(), self.observed(branch="feature"))
        with self.assertRaisesRegex(PublicationGuardError, "publication_sha_invalid"):
            validate_publication(self.spec(), self.observed(publication_sha="bad"))


if __name__ == "__main__":
    unittest.main()
