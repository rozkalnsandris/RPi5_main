from __future__ import annotations

from dataclasses import replace
import inspect
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.hermes_deals_runner_smoke_install import (
    HELPER_SHA256,
    INSTALL_TARGET_ALIAS,
    LIVE_ENVELOPE_SCHEMA,
    LIVE_GATE_ID,
    OPERATION_ID,
    OWNER_NUMERIC_ID,
    REGISTRATION_SHA256,
    SOURCE_REPOSITORY,
    SOURCE_REPOSITORY_ID,
    SOURCE_SHA,
)
from deploy_executor.hermes_deals_runner_smoke_install_consumer import (
    CanonicalRunnerSmokeInstallEvidence,
    RunnerSmokeInstallConsumerError,
    prepare_install_live_envelope,
    source_readiness,
)

AUTH_CREATED = "2026-09-12T16:00:00Z"
SERVER_TIME = "2026-09-12T16:00:10Z"


def canonical_evidence() -> CanonicalRunnerSmokeInstallEvidence:
    return CanonicalRunnerSmokeInstallEvidence(
        authorization_issue_number=17,
        authorization_created_at=AUTH_CREATED,
        github_server_time=SERVER_TIME,
        owner_numeric_id=OWNER_NUMERIC_ID,
        owner_type="User",
        app_authored=False,
        operation_id=OPERATION_ID,
        live_gate_id=LIVE_GATE_ID,
        target_alias=INSTALL_TARGET_ALIAS,
        source_repository=SOURCE_REPOSITORY,
        source_repository_id=SOURCE_REPOSITORY_ID,
        source_sha=SOURCE_SHA,
        rpi5_main_sha="1" * 40,
        rpi5_main_merged_reachable=True,
        rpi5_main_ci_success=True,
        hermes_source_merged_reachable=True,
        hermes_source_ci_success=True,
        helper_sha256=HELPER_SHA256,
        registration_sha256=REGISTRATION_SHA256,
        request_body_sha256="2" * 64,
        identical_body_refetch=True,
        ttl_valid=True,
        replay_available=True,
        live_authorized=True,
        rollback_policy="NONE",
    )


class FakeCanonicalRevalidator:
    def __init__(self, first=None, second=None):
        self.first = first or canonical_evidence()
        self.second = self.first if second is None else second
        self.calls: list[int] = []

    def revalidate(self, authorization_issue_number: int):
        self.calls.append(authorization_issue_number)
        return self.first if len(self.calls) == 1 else self.second


class RunnerSmokeInstallConsumerTests(unittest.TestCase):
    def test_exact_authorization_is_revalidated_twice_and_prepares_installer_envelope(self):
        canonical = FakeCanonicalRevalidator()
        envelope = prepare_install_live_envelope(17, canonical_revalidator=canonical)
        self.assertEqual(canonical.calls, [17, 17])
        self.assertEqual(envelope["schema"], LIVE_ENVELOPE_SCHEMA)
        self.assertEqual(envelope["authorization_issue_number"], 17)
        self.assertEqual(envelope["source_sha"], SOURCE_SHA)
        self.assertEqual(envelope["helper_sha256"], HELPER_SHA256)
        self.assertEqual(envelope["registration_sha256"], REGISTRATION_SHA256)

    def test_only_positive_issue_number_crosses_caller_boundary(self):
        signature = inspect.signature(prepare_install_live_envelope)
        self.assertEqual(tuple(signature.parameters), ("authorization_issue_number", "canonical_revalidator"))
        self.assertEqual(signature.parameters["canonical_revalidator"].kind, inspect.Parameter.KEYWORD_ONLY)
        for value in (0, -1, True, "17", {"authorization_issue_number": 17}):
            with self.subTest(value=value):
                with self.assertRaises(RunnerSmokeInstallConsumerError):
                    prepare_install_live_envelope(value, canonical_revalidator=FakeCanonicalRevalidator())

    def test_identity_scope_and_artifact_drift_fail_closed(self):
        changes = (
            {"owner_numeric_id": 1},
            {"owner_type": "Bot"},
            {"app_authored": True},
            {"operation_id": "wrong"},
            {"live_gate_id": "wrong"},
            {"target_alias": "wrong"},
            {"source_repository": "wrong/repo"},
            {"source_repository_id": 1},
            {"source_sha": "3" * 40},
            {"helper_sha256": "4" * 64},
            {"registration_sha256": "5" * 64},
            {"rollback_policy": "BUILTIN_TRANSACTIONAL_V1"},
        )
        for changed in changes:
            with self.subTest(changed=changed):
                evidence = replace(canonical_evidence(), **changed)
                with self.assertRaises(RunnerSmokeInstallConsumerError):
                    prepare_install_live_envelope(17, canonical_revalidator=FakeCanonicalRevalidator(evidence))

    def test_ttl_refetch_replay_and_ci_proofs_fail_closed(self):
        for field in (
            "rpi5_main_merged_reachable",
            "rpi5_main_ci_success",
            "hermes_source_merged_reachable",
            "hermes_source_ci_success",
            "identical_body_refetch",
            "ttl_valid",
            "replay_available",
            "live_authorized",
        ):
            with self.subTest(field=field):
                evidence = replace(canonical_evidence(), **{field: False})
                with self.assertRaises(RunnerSmokeInstallConsumerError):
                    prepare_install_live_envelope(17, canonical_revalidator=FakeCanonicalRevalidator(evidence))
        stale = replace(canonical_evidence(), authorization_created_at="2026-09-12T15:00:00Z")
        with self.assertRaises(RunnerSmokeInstallConsumerError):
            prepare_install_live_envelope(17, canonical_revalidator=FakeCanonicalRevalidator(stale))

    def test_body_hash_and_rpi5_sha_are_canonical(self):
        for changed in (
            {"rpi5_main_sha": "not-a-sha"},
            {"request_body_sha256": "not-a-hash"},
        ):
            with self.subTest(changed=changed):
                evidence = replace(canonical_evidence(), **changed)
                with self.assertRaises(RunnerSmokeInstallConsumerError):
                    prepare_install_live_envelope(17, canonical_revalidator=FakeCanonicalRevalidator(evidence))

    def test_second_revalidation_drift_fails_closed(self):
        first = canonical_evidence()
        second = replace(first, request_body_sha256="3" * 64)
        with self.assertRaisesRegex(RunnerSmokeInstallConsumerError, "evidence drifted"):
            prepare_install_live_envelope(17, canonical_revalidator=FakeCanonicalRevalidator(first, second))
        later = replace(first, github_server_time="2026-09-12T16:00:41Z")
        with self.assertRaisesRegex(RunnerSmokeInstallConsumerError, "GitHub time drifted"):
            prepare_install_live_envelope(17, canonical_revalidator=FakeCanonicalRevalidator(first, later))

    def test_consumer_has_no_apply_or_execution_primitive(self):
        source = (ROOT / "ops/lib/deploy_executor/hermes_deals_runner_smoke_install_consumer.py").read_text()
        for prohibited in ("subprocess", "os.system", "Popen", "shell=True", "PosixFixedInstallBackend(", "apply_install("):
            self.assertNotIn(prohibited, source)
        ready = source_readiness()
        self.assertEqual(ready["request_authority"], ("authorization_issue_number",))
        self.assertFalse(ready["external_apply_entrypoint_enabled"])
        self.assertFalse(ready["runtime_activation_enabled"])
        self.assertFalse(ready["global_executor_execution_enabled"])
        self.assertFalse(ready["authorization_consumed"])
        self.assertFalse(ready["production_mutation_started"])

    def test_contract_and_doc_keep_consumer_source_only(self):
        import json
        contract = json.loads((ROOT / "ops/contracts/hermes-deals-runner-smoke-install-v2.json").read_text())
        consumer = contract["authorization_consumer"]
        self.assertEqual(consumer["request_authority"], ["authorization_issue_number"])
        self.assertFalse(consumer["external_entrypoint_enabled"])
        self.assertFalse(consumer["runtime_activation_enabled"])
        self.assertFalse(consumer["app_authored_allowed"])
        self.assertTrue(contract["handoff"]["live_envelope_consumer_implemented"])
        self.assertFalse(contract["handoff"]["live_envelope_consumer_enabled"])
        self.assertFalse(contract["handoff"]["source_merge_authorizes_live"])
        doc = (ROOT / "docs/HERMES_DEALS_RUNNER_SMOKE_INSTALL.md").read_text()
        self.assertIn("prepare_install_live_envelope()", doc)
        self.assertIn("does not call `apply_install()`", doc)


if __name__ == "__main__":
    unittest.main()
