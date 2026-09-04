from __future__ import annotations

from dataclasses import replace
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.hermes_deals_origin_adapter import (
    ADAPTER_ID,
    INVOCATION_BUDGET,
    OPERATION_ID,
    PULL_HELPER_ARGUMENTS,
    REQUIRED_DEPENDENCIES,
    REQUIRED_EXCLUSIONS,
    ROLLBACK_POLICY,
    SOURCE_REPOSITORY,
    TARGET_ALIAS,
)
from deploy_executor.hermes_deals_origin_dispatch_request import (
    HermesDealsOriginDispatchRequestError,
    SCHEMA as REQUEST_SCHEMA,
)
from deploy_executor.hermes_deals_origin_privileged_consumer import (
    AUTHORIZATION_CLASS,
    CANONICAL_AS_OF_SOURCE,
    HOST_EVIDENCE_SCHEMA,
    CanonicalHermesOriginEvidence,
    HermesDealsOriginPrivilegedConsumerError,
    consume_privileged_request,
    evaluate_hermes_deals_origin_privileged_consumer,
    source_readiness,
)


SOURCE_SHA = "1" * 40
CURRENT_MAIN_SHA = "2" * 40
REQUEST_ID = "123e4567-e89b-42d3-a456-426614174000"
AUTHORIZATION_CREATED_AT = "2026-09-04T07:26:48Z"


def canonical_evidence() -> CanonicalHermesOriginEvidence:
    return CanonicalHermesOriginEvidence(
        authorization_issue_number=17,
        authorization_created_at=AUTHORIZATION_CREATED_AT,
        request_id=REQUEST_ID,
        queue_issue=41,
        source_repository=SOURCE_REPOSITORY,
        source_sha=SOURCE_SHA,
        current_main_sha=CURRENT_MAIN_SHA,
        source_ci_run_id=9001,
        operation_id=OPERATION_ID,
        adapter_id=ADAPTER_ID,
        target_alias=TARGET_ALIAS,
        authorization_class=AUTHORIZATION_CLASS,
        ordinary_live_all_eligible=False,
        rollback_policy=ROLLBACK_POLICY,
        mutation_budget=INVOCATION_BUDGET,
        exclusions=tuple(sorted(REQUIRED_EXCLUSIONS)),
        dependencies=tuple(sorted(REQUIRED_DEPENDENCIES)),
        isolated_authorization_surface_valid=True,
        authorization_owner_verified=True,
        authorization_ttl_valid=True,
        authorization_body_unchanged=True,
        authorization_replay_available=True,
        queue_ready=True,
        queue_binding_valid=True,
        registry_execution_enabled=False,
        source_reachable_from_main=True,
        source_ci_success=True,
        baseline_matched=True,
        prepared_execution_enabled=False,
        adapter_preflight_read_only=True,
        adapter_preflight_privileged_dispatch_ready=False,
    )


def host_evidence() -> dict[str, object]:
    return {
        "schema": HOST_EVIDENCE_SCHEMA,
        "evidence_id": "host-origin-audit-readonly-1",
        "operation_id": OPERATION_ID,
        "registered_source_sha": SOURCE_SHA,
        "registration_name": "origin-path-audit",
        "registration_owner_root": True,
        "registration_mode_0600": True,
        "dispatcher_identity_match": True,
        "probe_identity_match": True,
        "workflow_identity_match": True,
        "pull_helper_identity_match": True,
        "pull_helper_interface_match": True,
        "evidence_read_only": True,
        "evidence_fresh": True,
        "protected_values_included": False,
    }


class FakeCanonicalRevalidator:
    def __init__(
        self,
        first: CanonicalHermesOriginEvidence | None = None,
        second: CanonicalHermesOriginEvidence | None = None,
    ):
        self.first = first or canonical_evidence()
        self.second = second if second is not None else self.first
        self.calls: list[int] = []

    def revalidate(self, authorization_issue_number: int) -> CanonicalHermesOriginEvidence:
        self.calls.append(authorization_issue_number)
        return self.first if len(self.calls) == 1 else self.second


class FakeHostEvidenceResolver:
    def __init__(self, evidence: dict[str, object] | None = None):
        self.evidence = evidence or host_evidence()
        self.calls: list[str] = []

    def resolve(self, *, source_sha: str) -> dict[str, object]:
        self.calls.append(source_sha)
        return dict(self.evidence)


class HermesDealsOriginPrivilegedConsumerTests(unittest.TestCase):
    def request(self) -> dict[str, object]:
        return {
            "schema": REQUEST_SCHEMA,
            "authorization_issue_number": 17,
        }

    def test_exact_identity_is_fully_revalidated_twice_and_remains_non_executable(self):
        canonical = FakeCanonicalRevalidator()
        host = FakeHostEvidenceResolver()

        ready = consume_privileged_request(
            self.request(),
            canonical_revalidator=canonical,
            host_evidence_resolver=host,
        )

        self.assertEqual(ready.result, "PRIVILEGED_CONSUMER_READY")
        self.assertEqual(ready.authorization_issue_number, 17)
        self.assertEqual(ready.authorization_created_at, AUTHORIZATION_CREATED_AT)
        self.assertEqual(ready.canonical_as_of, "2026-09-04")
        self.assertEqual(ready.operation_id, OPERATION_ID)
        self.assertEqual(ready.source_sha, SOURCE_SHA)
        self.assertEqual(ready.host_evidence_id, "host-origin-audit-readonly-1")
        self.assertTrue(ready.privileged_consumer_implemented)
        self.assertFalse(ready.privileged_dispatch_enabled)
        self.assertFalse(ready.host_wiring_enabled)
        self.assertFalse(ready.genuine_hermes_audit_authorized)
        self.assertFalse(ready.runner_retirement_eligible)
        self.assertFalse(ready.production_mutation_started)
        self.assertEqual(canonical.calls, [17, 17])
        self.assertEqual(host.calls, [SOURCE_SHA])

    def test_compatibility_wrapper_uses_same_fail_closed_consumer(self):
        canonical = FakeCanonicalRevalidator()
        host = FakeHostEvidenceResolver()
        ready = evaluate_hermes_deals_origin_privileged_consumer(
            self.request(),
            canonical_revalidator=canonical,
            host_evidence_resolver=host,
        )
        self.assertEqual(ready.canonical_as_of, "2026-09-04")
        self.assertEqual(canonical.calls, [17, 17])
        self.assertEqual(host.calls, [SOURCE_SHA])

    def test_expanded_request_never_reaches_canonical_revalidator(self):
        prohibited = (
            "command",
            "shell",
            "path",
            "argv",
            "environment",
            "sudo",
            "source_sha",
            "as_of",
            "artifact_dir",
            "repository_entrypoint",
            "capability",
        )
        for field in prohibited:
            with self.subTest(field=field):
                canonical = FakeCanonicalRevalidator()
                host = FakeHostEvidenceResolver()
                request = self.request()
                request[field] = "untrusted"
                with self.assertRaises(HermesDealsOriginDispatchRequestError):
                    consume_privileged_request(
                        request,
                        canonical_revalidator=canonical,
                        host_evidence_resolver=host,
                    )
                self.assertEqual(canonical.calls, [])
                self.assertEqual(host.calls, [])

    def test_authorization_created_at_must_be_canonical_github_utc(self):
        for value in (
            "2026-09-04T09:26:48+02:00",
            "2026-09-04T07:26:48.000Z",
            "2026-09-04",
            "not-a-time",
        ):
            with self.subTest(value=value):
                evidence = replace(canonical_evidence(), authorization_created_at=value)
                with self.assertRaisesRegex(
                    HermesDealsOriginPrivilegedConsumerError,
                    "authorization_created_at",
                ):
                    consume_privileged_request(
                        self.request(),
                        canonical_revalidator=FakeCanonicalRevalidator(evidence),
                        host_evidence_resolver=FakeHostEvidenceResolver(),
                    )

    def test_wrong_operation_source_or_strict_policy_fails_closed(self):
        cases = (
            replace(canonical_evidence(), operation_id="other.operation.v1"),
            replace(canonical_evidence(), source_repository="other/repo"),
            replace(canonical_evidence(), authorization_class="ORDINARY"),
            replace(canonical_evidence(), ordinary_live_all_eligible=True),
            replace(canonical_evidence(), rollback_policy="BUILTIN_TRANSACTIONAL_V1"),
            replace(
                canonical_evidence(),
                mutation_budget=(("hermes-deals.read-only-audit-invocation", 2),),
            ),
            replace(canonical_evidence(), registry_execution_enabled=True),
            replace(canonical_evidence(), prepared_execution_enabled=True),
            replace(
                canonical_evidence(),
                adapter_preflight_privileged_dispatch_ready=True,
            ),
        )
        for evidence in cases:
            with self.subTest(evidence=evidence):
                with self.assertRaises(HermesDealsOriginPrivilegedConsumerError):
                    consume_privileged_request(
                        self.request(),
                        canonical_revalidator=FakeCanonicalRevalidator(evidence),
                        host_evidence_resolver=FakeHostEvidenceResolver(),
                    )

    def test_missing_provenance_or_exclusion_fails_closed(self):
        missing_dependency = next(iter(REQUIRED_DEPENDENCIES))
        dependencies = tuple(
            item for item in sorted(REQUIRED_DEPENDENCIES) if item != missing_dependency
        )
        missing_exclusion = next(iter(REQUIRED_EXCLUSIONS))
        exclusions = tuple(
            item for item in sorted(REQUIRED_EXCLUSIONS) if item != missing_exclusion
        )
        for evidence in (
            replace(canonical_evidence(), dependencies=dependencies),
            replace(canonical_evidence(), exclusions=exclusions),
        ):
            with self.assertRaises(HermesDealsOriginPrivilegedConsumerError):
                consume_privileged_request(
                    self.request(),
                    canonical_revalidator=FakeCanonicalRevalidator(evidence),
                    host_evidence_resolver=FakeHostEvidenceResolver(),
                )

    def test_full_canonical_trust_state_must_be_valid(self):
        fields = (
            "isolated_authorization_surface_valid",
            "authorization_owner_verified",
            "authorization_ttl_valid",
            "authorization_body_unchanged",
            "authorization_replay_available",
            "queue_ready",
            "queue_binding_valid",
            "source_reachable_from_main",
            "source_ci_success",
            "baseline_matched",
            "adapter_preflight_read_only",
        )
        for field in fields:
            with self.subTest(field=field):
                evidence = replace(canonical_evidence(), **{field: False})
                with self.assertRaises(HermesDealsOriginPrivilegedConsumerError):
                    consume_privileged_request(
                        self.request(),
                        canonical_revalidator=FakeCanonicalRevalidator(evidence),
                        host_evidence_resolver=FakeHostEvidenceResolver(),
                    )

    def test_host_evidence_is_exact_fresh_sanitized_source_and_pull_helper_bound(self):
        cases: list[dict[str, object]] = []

        expanded = host_evidence()
        expanded["dispatcher_path"] = "/untrusted"
        cases.append(expanded)

        protected = host_evidence()
        protected["protected_values_included"] = True
        cases.append(protected)

        stale = host_evidence()
        stale["evidence_fresh"] = False
        cases.append(stale)

        wrong_source = host_evidence()
        wrong_source["registered_source_sha"] = "3" * 40
        cases.append(wrong_source)

        wrong_legacy_identity = host_evidence()
        wrong_legacy_identity["dispatcher_identity_match"] = False
        cases.append(wrong_legacy_identity)

        wrong_pull_helper_identity = host_evidence()
        wrong_pull_helper_identity["pull_helper_identity_match"] = False
        cases.append(wrong_pull_helper_identity)

        wrong_pull_helper_interface = host_evidence()
        wrong_pull_helper_interface["pull_helper_interface_match"] = False
        cases.append(wrong_pull_helper_interface)

        missing_pull_helper_identity = host_evidence()
        del missing_pull_helper_identity["pull_helper_identity_match"]
        cases.append(missing_pull_helper_identity)

        for evidence in cases:
            with self.subTest(evidence=evidence):
                canonical = FakeCanonicalRevalidator()
                with self.assertRaises(HermesDealsOriginPrivilegedConsumerError):
                    consume_privileged_request(
                        self.request(),
                        canonical_revalidator=canonical,
                        host_evidence_resolver=FakeHostEvidenceResolver(evidence),
                    )
                self.assertEqual(canonical.calls, [17])

    def test_final_full_revalidation_failure_does_not_emit_ready(self):
        stale = replace(canonical_evidence(), authorization_ttl_valid=False)
        with self.assertRaises(HermesDealsOriginPrivilegedConsumerError):
            consume_privileged_request(
                self.request(),
                canonical_revalidator=FakeCanonicalRevalidator(
                    canonical_evidence(),
                    stale,
                ),
                host_evidence_resolver=FakeHostEvidenceResolver(),
            )

    def test_final_evidence_drift_does_not_emit_ready(self):
        drifted_values = (
            replace(canonical_evidence(), source_ci_run_id=9002),
            replace(
                canonical_evidence(),
                authorization_created_at="2026-09-04T07:26:49Z",
            ),
        )
        for drifted in drifted_values:
            with self.subTest(drifted=drifted):
                with self.assertRaisesRegex(
                    HermesDealsOriginPrivilegedConsumerError,
                    "canonical evidence drifted",
                ):
                    consume_privileged_request(
                        self.request(),
                        canonical_revalidator=FakeCanonicalRevalidator(
                            canonical_evidence(),
                            drifted,
                        ),
                        host_evidence_resolver=FakeHostEvidenceResolver(),
                    )

    def test_consumer_source_exposes_no_execution_primitive(self):
        source = (
            ROOT
            / "ops"
            / "lib"
            / "deploy_executor"
            / "hermes_deals_origin_privileged_consumer.py"
        ).read_text(encoding="utf-8")
        forbidden = (
            "import subprocess",
            "from subprocess",
            "os.system(",
            "Popen(",
            "adapter.apply(",
            ".consume(",
            "sudo --",
            "systemctl ",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_source_readiness_keeps_live_gates_false(self):
        readiness = source_readiness()
        self.assertTrue(readiness["privileged_consumer_implemented"])
        self.assertTrue(readiness["runner_independent_pull_helper_bound"])
        self.assertEqual(readiness["pull_helper_arguments"], PULL_HELPER_ARGUMENTS)
        self.assertEqual(readiness["canonical_as_of_source"], CANONICAL_AS_OF_SOURCE)
        self.assertTrue(readiness["full_canonical_revalidation_after_host_evidence"])
        self.assertFalse(readiness["privileged_dispatch_enabled"])
        self.assertFalse(readiness["host_wiring_enabled"])
        self.assertFalse(readiness["genuine_hermes_audit_authorized"])
        self.assertFalse(readiness["runner_retirement_eligible"])
        self.assertFalse(readiness["production_mutation_started"])
        self.assertEqual(
            readiness["request_authority"],
            ("authorization_issue_number",),
        )
        self.assertEqual(
            readiness["host_evidence_schema"],
            HOST_EVIDENCE_SCHEMA,
        )


if __name__ == "__main__":
    unittest.main()
