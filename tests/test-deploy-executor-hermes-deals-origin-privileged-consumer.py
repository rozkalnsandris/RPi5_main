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
    HOST_EVIDENCE_SCHEMA,
    CanonicalHermesOriginEvidence,
    HermesDealsOriginPrivilegedConsumerError,
    evaluate_hermes_deals_origin_privileged_consumer,
    source_readiness,
)


SOURCE_SHA = "1" * 40
CURRENT_MAIN_SHA = "2" * 40
REQUEST_ID = "123e4567-e89b-42d3-a456-426614174000"


def canonical_evidence() -> CanonicalHermesOriginEvidence:
    return CanonicalHermesOriginEvidence(
        authorization_issue_number=17,
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
        authorization_owner_verified=True,
        authorization_ttl_valid=True,
        authorization_body_unchanged=True,
        queue_ready=True,
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
        "evidence_read_only": True,
        "protected_values_included": False,
    }


class FakeCanonicalRevalidator:
    def __init__(self, evidence: CanonicalHermesOriginEvidence | None = None):
        self.evidence = evidence or canonical_evidence()
        self.calls: list[tuple[str, object]] = []
        self.fail_final = False

    def revalidate(self, authorization_issue_number: int) -> CanonicalHermesOriginEvidence:
        self.calls.append(("revalidate", authorization_issue_number))
        return self.evidence

    def verify_unchanged(self, evidence: CanonicalHermesOriginEvidence) -> None:
        self.calls.append(("verify_unchanged", evidence.request_id))
        if self.fail_final:
            raise HermesDealsOriginPrivilegedConsumerError(
                "final authorization revalidation failed"
            )


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

    def test_exact_identity_is_revalidated_and_remains_non_executable(self):
        canonical = FakeCanonicalRevalidator()
        host = FakeHostEvidenceResolver()

        ready = evaluate_hermes_deals_origin_privileged_consumer(
            self.request(),
            canonical_revalidator=canonical,
            host_evidence_resolver=host,
        )

        self.assertEqual(ready.result, "PRIVILEGED_CONSUMER_READY")
        self.assertEqual(ready.authorization_issue_number, 17)
        self.assertEqual(ready.operation_id, OPERATION_ID)
        self.assertEqual(ready.source_sha, SOURCE_SHA)
        self.assertEqual(ready.host_evidence_id, "host-origin-audit-readonly-1")
        self.assertTrue(ready.privileged_consumer_implemented)
        self.assertFalse(ready.privileged_dispatch_enabled)
        self.assertFalse(ready.host_wiring_enabled)
        self.assertFalse(ready.genuine_hermes_audit_authorized)
        self.assertFalse(ready.runner_retirement_eligible)
        self.assertFalse(ready.production_mutation_started)
        self.assertEqual(
            canonical.calls,
            [
                ("revalidate", 17),
                ("verify_unchanged", REQUEST_ID),
            ],
        )
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
        )
        for field in prohibited:
            with self.subTest(field=field):
                canonical = FakeCanonicalRevalidator()
                host = FakeHostEvidenceResolver()
                request = self.request()
                request[field] = "untrusted"
                with self.assertRaises(HermesDealsOriginDispatchRequestError):
                    evaluate_hermes_deals_origin_privileged_consumer(
                        request,
                        canonical_revalidator=canonical,
                        host_evidence_resolver=host,
                    )
                self.assertEqual(canonical.calls, [])
                self.assertEqual(host.calls, [])

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
                    evaluate_hermes_deals_origin_privileged_consumer(
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
                evaluate_hermes_deals_origin_privileged_consumer(
                    self.request(),
                    canonical_revalidator=FakeCanonicalRevalidator(evidence),
                    host_evidence_resolver=FakeHostEvidenceResolver(),
                )

    def test_authorization_queue_source_ci_and_baseline_must_be_freshly_valid(self):
        fields = (
            "authorization_owner_verified",
            "authorization_ttl_valid",
            "authorization_body_unchanged",
            "queue_ready",
            "source_reachable_from_main",
            "source_ci_success",
            "baseline_matched",
            "adapter_preflight_read_only",
        )
        for field in fields:
            with self.subTest(field=field):
                evidence = replace(canonical_evidence(), **{field: False})
                with self.assertRaises(HermesDealsOriginPrivilegedConsumerError):
                    evaluate_hermes_deals_origin_privileged_consumer(
                        self.request(),
                        canonical_revalidator=FakeCanonicalRevalidator(evidence),
                        host_evidence_resolver=FakeHostEvidenceResolver(),
                    )

    def test_host_evidence_is_exact_sanitized_and_source_bound(self):
        cases: list[dict[str, object]] = []

        expanded = host_evidence()
        expanded["dispatcher_path"] = "/untrusted"
        cases.append(expanded)

        protected = host_evidence()
        protected["protected_values_included"] = True
        cases.append(protected)

        wrong_source = host_evidence()
        wrong_source["registered_source_sha"] = "3" * 40
        cases.append(wrong_source)

        wrong_identity = host_evidence()
        wrong_identity["dispatcher_identity_match"] = False
        cases.append(wrong_identity)

        for evidence in cases:
            with self.subTest(evidence=evidence):
                canonical = FakeCanonicalRevalidator()
                with self.assertRaises(HermesDealsOriginPrivilegedConsumerError):
                    evaluate_hermes_deals_origin_privileged_consumer(
                        self.request(),
                        canonical_revalidator=canonical,
                        host_evidence_resolver=FakeHostEvidenceResolver(evidence),
                    )
                self.assertEqual(canonical.calls, [("revalidate", 17)])

    def test_final_authorization_revalidation_failure_does_not_emit_ready(self):
        canonical = FakeCanonicalRevalidator()
        canonical.fail_final = True
        with self.assertRaisesRegex(
            HermesDealsOriginPrivilegedConsumerError,
            "final authorization revalidation failed",
        ):
            evaluate_hermes_deals_origin_privileged_consumer(
                self.request(),
                canonical_revalidator=canonical,
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
