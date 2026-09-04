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
    PULL_HELPER_CAPABILITY,
    PULL_HELPER_SOURCE_BLOB,
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
)
from deploy_executor.hermes_deals_origin_privileged_dispatcher import (
    DISPATCH_PLAN_SCHEMA,
    INSTALLED_HELPER_PATH,
    prepare_hermes_deals_origin_privileged_dispatch,
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


class HermesDealsOriginPrivilegedDispatcherTests(unittest.TestCase):
    def request(self) -> dict[str, object]:
        return {
            "schema": REQUEST_SCHEMA,
            "authorization_issue_number": 17,
        }

    def test_plan_binds_exact_capability_helper_and_two_canonical_arguments(self):
        canonical = FakeCanonicalRevalidator()
        host = FakeHostEvidenceResolver()
        plan = prepare_hermes_deals_origin_privileged_dispatch(
            self.request(),
            canonical_revalidator=canonical,
            host_evidence_resolver=host,
        )

        self.assertEqual(plan.schema, DISPATCH_PLAN_SCHEMA)
        self.assertEqual(plan.result, "PRIVILEGED_DISPATCH_SOURCE_READY")
        self.assertEqual(plan.authorization_issue_number, 17)
        self.assertEqual(plan.operation_id, OPERATION_ID)
        self.assertEqual(plan.source_repository, SOURCE_REPOSITORY)
        self.assertEqual(plan.registered_source_sha, SOURCE_SHA)
        self.assertEqual(plan.canonical_as_of, "2026-09-04")
        self.assertEqual(plan.capability, PULL_HELPER_CAPABILITY)
        self.assertEqual(plan.helper_source_blob, PULL_HELPER_SOURCE_BLOB)
        self.assertEqual(plan.installed_helper_path, INSTALLED_HELPER_PATH)
        self.assertEqual(plan.helper_argument_names, PULL_HELPER_ARGUMENTS)
        self.assertEqual(plan.helper_arguments, (SOURCE_SHA, "2026-09-04"))
        self.assertTrue(plan.privileged_dispatch_implemented)
        self.assertFalse(plan.privileged_dispatch_enabled)
        self.assertFalse(plan.host_wiring_enabled)
        self.assertFalse(plan.genuine_hermes_audit_authorized)
        self.assertFalse(plan.runner_retirement_eligible)
        self.assertFalse(plan.production_mutation_started)
        self.assertEqual(canonical.calls, [17, 17])
        self.assertEqual(host.calls, [SOURCE_SHA])

    def test_caller_cannot_supply_dispatch_parameters_or_capability(self):
        for field in (
            "source_sha",
            "registered_source_sha",
            "as_of",
            "canonical_as_of",
            "helper_path",
            "path",
            "argv",
            "environment",
            "sudo",
            "capability",
            "command",
            "shell",
        ):
            with self.subTest(field=field):
                request = self.request()
                request[field] = "untrusted"
                canonical = FakeCanonicalRevalidator()
                host = FakeHostEvidenceResolver()
                with self.assertRaises(HermesDealsOriginDispatchRequestError):
                    prepare_hermes_deals_origin_privileged_dispatch(
                        request,
                        canonical_revalidator=canonical,
                        host_evidence_resolver=host,
                    )
                self.assertEqual(canonical.calls, [])
                self.assertEqual(host.calls, [])

    def test_source_or_authorization_time_drift_fails_before_plan(self):
        for drifted in (
            replace(canonical_evidence(), source_sha="3" * 40),
            replace(
                canonical_evidence(),
                authorization_created_at="2026-09-04T07:26:49Z",
            ),
        ):
            with self.subTest(drifted=drifted):
                with self.assertRaises(HermesDealsOriginPrivilegedConsumerError):
                    prepare_hermes_deals_origin_privileged_dispatch(
                        self.request(),
                        canonical_revalidator=FakeCanonicalRevalidator(
                            canonical_evidence(),
                            drifted,
                        ),
                        host_evidence_resolver=FakeHostEvidenceResolver(),
                    )

    def test_host_evidence_cannot_add_path_or_argument_authority(self):
        expanded = host_evidence()
        expanded["helper_path"] = "/untrusted"
        with self.assertRaises(HermesDealsOriginPrivilegedConsumerError):
            prepare_hermes_deals_origin_privileged_dispatch(
                self.request(),
                canonical_revalidator=FakeCanonicalRevalidator(),
                host_evidence_resolver=FakeHostEvidenceResolver(expanded),
            )

    def test_dispatcher_source_has_no_process_or_generic_privilege_surface(self):
        source = (
            ROOT
            / "ops"
            / "lib"
            / "deploy_executor"
            / "hermes_deals_origin_privileged_dispatcher.py"
        ).read_text(encoding="utf-8")
        forbidden = (
            "import subprocess",
            "from subprocess",
            "os.system(",
            "Popen(",
            "shell=True",
            "bash -c",
            "sh -c",
            "eval(",
            "sudo ",
            "systemctl ",
            "adapter.apply(",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_source_readiness_is_implemented_but_all_live_gates_remain_false(self):
        readiness = source_readiness()
        self.assertTrue(readiness["privileged_dispatch_implemented"])
        self.assertFalse(readiness["privileged_dispatch_enabled"])
        self.assertFalse(readiness["host_wiring_enabled"])
        self.assertFalse(readiness["genuine_hermes_audit_authorized"])
        self.assertFalse(readiness["runner_retirement_eligible"])
        self.assertFalse(readiness["production_mutation_started"])
        self.assertFalse(readiness["process_launch_surface"])
        self.assertEqual(readiness["capability"], PULL_HELPER_CAPABILITY)
        self.assertEqual(readiness["helper_source_blob"], PULL_HELPER_SOURCE_BLOB)
        self.assertEqual(readiness["installed_helper_path"], INSTALLED_HELPER_PATH)
        self.assertEqual(readiness["helper_argument_names"], PULL_HELPER_ARGUMENTS)
        self.assertEqual(
            readiness["caller_authority"],
            ("authorization_issue_number",),
        )
        self.assertEqual(
            readiness["canonical_parameters"],
            ("registered_source_sha", "canonical_as_of"),
        )


if __name__ == "__main__":
    unittest.main()
