from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.p9_canary import (
    BaselineEvidence,
    GovernanceEvidence,
    P9CanaryError,
    run_p9_dry_run_canary,
)
from deploy_executor.source_evidence import SourceEvidenceError, verify_source_evidence

SHA = "a" * 40
MAIN = "b" * 40
NOW = datetime(2026, 8, 28, 18, 0, tzinfo=timezone.utc)


@dataclass
class Response:
    value: object
    server_time: datetime = NOW


class SourceClient:
    def __init__(self, *, main=MAIN, merge_base=SHA, ci_success=True, repository_id=1317143994):
        self.main = main
        self.merge_base = merge_base
        self.ci_success = ci_success
        self.repository_id = repository_id
        self.calls = []

    def get_json(self, path):
        self.calls.append(path)
        repo = "rozkalnsandris/hermes-deals"
        if path == f"/repos/{repo}":
            return Response({"id": self.repository_id, "full_name": repo, "default_branch": "main"})
        if path == f"/repos/{repo}/branches/main":
            return Response({"commit": {"sha": self.main}})
        if path == f"/repos/{repo}/compare/{SHA}...{self.main}":
            return Response({"merge_base_commit": {"sha": self.merge_base}, "behind_by": 0, "status": "ahead"})
        if "/actions/workflows/ci.yml/runs?" in path:
            conclusion = "success" if self.ci_success else "failure"
            return Response({"workflow_runs": [{"id": 91, "head_sha": SHA, "head_branch": "main", "status": "completed", "conclusion": conclusion}]})
        if path.endswith("/actions/runs/91/jobs?filter=latest&per_page=100"):
            return Response({"jobs": [{"status": "completed", "conclusion": "success"}]})
        raise AssertionError(path)


class Accepted:
    repository_id = 1328835922
    issue_id = 5001
    issue_number = 77
    request_id = "123e4567-e89b-42d3-a456-426614174000"
    canonical_payload_sha256 = "c" * 64
    raw_body_sha256 = "d" * 64
    payload = {
        "queue_issue": 15,
        "source_repository": "rozkalnsandris/hermes-deals",
        "source_sha": SHA,
        "target_alias": "hermes-deals-origin-path-audit",
        "operation_id": "hermes-deals.origin-path-audit.v1",
        "expected_baseline": {"kind": "resolver", "value": "hermes-deals.origin-path-registration.v1"},
    }


class AuthorityClient:
    def __init__(self):
        self.accepted = Accepted()
        self.calls = []
        self.verified = False

    def get_json(self, path):
        self.calls.append(path)
        if path == "/repos/rozkalnsandris/ops-workflows":
            return Response({"id": 1328835922, "full_name": "rozkalnsandris/ops-workflows"})
        if path == "/repos/rozkalnsandris/ops-workflows/issues/15":
            return Response({"number": 15, "repository_url": "https://api.github.com/repos/rozkalnsandris/ops-workflows"})
        raise AssertionError(path)

    def read_live_auth(self, issue_number, *, governance_ok, approved_operator_app_ids=frozenset()):
        self.calls.append(("read", issue_number, governance_ok, approved_operator_app_ids))
        return self.accepted

    def verify_live_auth_unchanged(self, accepted, *, governance_ok, approved_operator_app_ids=frozenset()):
        self.calls.append(("verify", accepted.issue_number, governance_ok, approved_operator_app_ids))
        self.verified = True


class StateStore:
    def __init__(self):
        self.events = []
        self.seen = set()

    def discover(self, **kwargs):
        request_id = kwargs["request_id"]
        if request_id in self.seen:
            raise RuntimeError("replay")
        self.seen.add(request_id)
        self.events.append(("discover", request_id))

    def transition(self, request_id, state):
        self.events.append(("transition", request_id, state))


class Normalized:
    execution_enabled = False
    operation = SimpleNamespace(operation_id="hermes-deals.origin-path-audit.v1")
    def as_protocol_queue(self):
        return {"queue": "normalized"}


class Adapter:
    def __init__(self):
        self.apply_called = False
    def preflight(self, prepared):
        return {"read_only": True, "execution_enabled": False, "privileged_dispatch_ready": False, "result": "SOURCE_CANARY_CONTRACT_PASS"}
    def apply(self, prepared):
        self.apply_called = True
        raise AssertionError("P9 must never apply")


class Catalog:
    def __init__(self, adapter):
        self.adapter = adapter
    def require(self, adapter_id):
        self.adapter_id = adapter_id
        return self.adapter


class P9PrepTests(unittest.TestCase):
    def test_source_evidence_accepts_ancestor_exact_sha_and_successful_ci(self):
        result = verify_source_evidence(SourceClient(), source_repository="rozkalnsandris/hermes-deals", source_sha=SHA)
        self.assertEqual(result.repository_id, 1317143994)
        self.assertEqual(result.source_sha, SHA)
        self.assertEqual(result.current_main_sha, MAIN)
        self.assertEqual(result.workflow, "ci.yml")
        self.assertEqual(result.run_id, 91)

    def test_source_evidence_rejects_nonancestor_and_failed_ci(self):
        with self.assertRaisesRegex(SourceEvidenceError, "merge base"):
            verify_source_evidence(SourceClient(merge_base="f" * 40), source_repository="rozkalnsandris/hermes-deals", source_sha=SHA)
        with self.assertRaisesRegex(SourceEvidenceError, "no successful"):
            verify_source_evidence(SourceClient(ci_success=False), source_repository="rozkalnsandris/hermes-deals", source_sha=SHA)

    def test_source_evidence_rejects_repository_identity_drift_and_unknown_repo(self):
        with self.assertRaisesRegex(SourceEvidenceError, "numeric identity"):
            verify_source_evidence(SourceClient(repository_id=1), source_repository="rozkalnsandris/hermes-deals", source_sha=SHA)
        with self.assertRaisesRegex(SourceEvidenceError, "allowlist"):
            verify_source_evidence(SourceClient(), source_repository="rozkalnsandris/unknown", source_sha=SHA)

    def test_p9_emits_only_dry_run_ready_after_all_read_only_gates(self):
        authority = AuthorityClient()
        state = StateStore()
        adapter = Adapter()
        catalog = Catalog(adapter)
        binding_calls = []
        baseline_calls = []

        result = run_p9_dry_run_canary(
            issue_number=77,
            authority_client=authority,
            source_client=SourceClient(),
            governance=GovernanceEvidence(
                repository="rozkalnsandris/ops-workflows",
                repository_id=1328835922,
                observed_at=NOW - timedelta(seconds=30),
                writer_set_sha256="e" * 64,
                trusted=True,
            ),
            state_store=state,
            registry=object(),
            adapter_catalog=catalog,
            normalize_ready_queue=lambda issue, **kwargs: Normalized(),
            validate_queue_binding=lambda accepted, queue: binding_calls.append((accepted, queue)),
            verify_source_evidence=verify_source_evidence,
            resolve_baseline=lambda operation, expected: baseline_calls.append((operation, expected)) or BaselineEvidence(
                resolver_id="hermes-deals.origin-path-registration.v1",
                target_alias="hermes-deals-origin-path-audit",
                matched=True,
                evidence_id="registration:observed",
            ),
            prepare_operation=lambda normalized: SimpleNamespace(adapter_id="hermes-deals.origin-path-audit.v1", execution_enabled=False),
        )

        self.assertEqual(result.result, "DRY_RUN_READY")
        self.assertFalse(result.mutation_dispatch_enabled)
        self.assertFalse(result.result_writer_enabled)
        self.assertFalse(result.production_mutation_started)
        self.assertEqual(state.events[-1][2], "ACCEPTED")
        self.assertTrue(authority.verified)
        self.assertFalse(adapter.apply_called)
        self.assertEqual(len(binding_calls), 1)
        self.assertEqual(len(baseline_calls), 1)

    def test_p9_fails_closed_on_stale_governance_before_authority_acceptance(self):
        authority = AuthorityClient()
        with self.assertRaisesRegex(P9CanaryError, "stale"):
            run_p9_dry_run_canary(
                issue_number=77,
                authority_client=authority,
                source_client=SourceClient(),
                governance=GovernanceEvidence(
                    repository="rozkalnsandris/ops-workflows",
                    repository_id=1328835922,
                    observed_at=NOW - timedelta(minutes=10),
                    writer_set_sha256="e" * 64,
                    trusted=True,
                ),
                state_store=StateStore(),
                registry=object(),
                adapter_catalog=Catalog(Adapter()),
                normalize_ready_queue=lambda issue, **kwargs: Normalized(),
                validate_queue_binding=lambda accepted, queue: None,
                verify_source_evidence=verify_source_evidence,
                resolve_baseline=lambda operation, expected: BaselineEvidence("x", "hermes-deals-origin-path-audit", True, "x"),
                prepare_operation=lambda normalized: SimpleNamespace(adapter_id="x", execution_enabled=False),
            )
        self.assertFalse(any(isinstance(row, tuple) and row[0] == "read" for row in authority.calls))

    def test_p9_rejects_execution_enabled_queue_and_never_applies(self):
        class EnabledNormalized(Normalized):
            execution_enabled = True
        authority = AuthorityClient()
        adapter = Adapter()
        with self.assertRaisesRegex(P9CanaryError, "execution-disabled"):
            run_p9_dry_run_canary(
                issue_number=77,
                authority_client=authority,
                source_client=SourceClient(),
                governance=GovernanceEvidence("rozkalnsandris/ops-workflows", 1328835922, NOW, "e"*64, True),
                state_store=StateStore(), registry=object(), adapter_catalog=Catalog(adapter),
                normalize_ready_queue=lambda issue, **kwargs: EnabledNormalized(),
                validate_queue_binding=lambda accepted, queue: None,
                verify_source_evidence=verify_source_evidence,
                resolve_baseline=lambda operation, expected: BaselineEvidence("x", "hermes-deals-origin-path-audit", True, "x"),
                prepare_operation=lambda normalized: SimpleNamespace(adapter_id="x", execution_enabled=False),
            )
        self.assertFalse(adapter.apply_called)

    def test_p9_rejects_baseline_mismatch_before_adapter_preflight(self):
        adapter = Adapter()
        with self.assertRaisesRegex(P9CanaryError, "baseline"):
            run_p9_dry_run_canary(
                issue_number=77,
                authority_client=AuthorityClient(),
                source_client=SourceClient(),
                governance=GovernanceEvidence("rozkalnsandris/ops-workflows", 1328835922, NOW, "e"*64, True),
                state_store=StateStore(), registry=object(), adapter_catalog=Catalog(adapter),
                normalize_ready_queue=lambda issue, **kwargs: Normalized(),
                validate_queue_binding=lambda accepted, queue: None,
                verify_source_evidence=verify_source_evidence,
                resolve_baseline=lambda operation, expected: BaselineEvidence(
                    "hermes-deals.origin-path-registration.v1",
                    "hermes-deals-origin-path-audit",
                    False,
                    "registration:mismatch",
                ),
                prepare_operation=lambda normalized: SimpleNamespace(adapter_id="x", execution_enabled=False),
            )
        self.assertFalse(adapter.apply_called)

    def test_p9_rejects_adapter_preflight_that_enables_privileged_dispatch(self):
        class UnsafeAdapter(Adapter):
            def preflight(self, prepared):
                return {"read_only": True, "privileged_dispatch_ready": True}
        adapter = UnsafeAdapter()
        with self.assertRaisesRegex(P9CanaryError, "privileged_dispatch_ready"):
            run_p9_dry_run_canary(
                issue_number=77,
                authority_client=AuthorityClient(),
                source_client=SourceClient(),
                governance=GovernanceEvidence("rozkalnsandris/ops-workflows", 1328835922, NOW, "e"*64, True),
                state_store=StateStore(), registry=object(), adapter_catalog=Catalog(adapter),
                normalize_ready_queue=lambda issue, **kwargs: Normalized(),
                validate_queue_binding=lambda accepted, queue: None,
                verify_source_evidence=verify_source_evidence,
                resolve_baseline=lambda operation, expected: BaselineEvidence(
                    "hermes-deals.origin-path-registration.v1",
                    "hermes-deals-origin-path-audit",
                    True,
                    "registration:observed",
                ),
                prepare_operation=lambda normalized: SimpleNamespace(adapter_id="x", execution_enabled=False),
            )
        self.assertFalse(adapter.apply_called)

    def test_p9_rechecks_governance_before_final_authority_refetch(self):
        class DriftingAuthority(AuthorityClient):
            def __init__(self):
                super().__init__()
                self.governance_probes = 0
            def get_json(self, path):
                response = super().get_json(path)
                if path == "/repos/rozkalnsandris/ops-workflows":
                    self.governance_probes += 1
                    if self.governance_probes == 2:
                        return Response(response.value, NOW + timedelta(minutes=10))
                return response
        authority = DriftingAuthority()
        with self.assertRaisesRegex(P9CanaryError, "stale"):
            run_p9_dry_run_canary(
                issue_number=77,
                authority_client=authority,
                source_client=SourceClient(),
                governance=GovernanceEvidence("rozkalnsandris/ops-workflows", 1328835922, NOW, "e"*64, True),
                state_store=StateStore(), registry=object(), adapter_catalog=Catalog(Adapter()),
                normalize_ready_queue=lambda issue, **kwargs: Normalized(),
                validate_queue_binding=lambda accepted, queue: None,
                verify_source_evidence=verify_source_evidence,
                resolve_baseline=lambda operation, expected: BaselineEvidence(
                    "hermes-deals.origin-path-registration.v1",
                    "hermes-deals-origin-path-audit",
                    True,
                    "registration:observed",
                ),
                prepare_operation=lambda normalized: SimpleNamespace(adapter_id="x", execution_enabled=False),
            )
        self.assertFalse(authority.verified)


if __name__ == "__main__":
    unittest.main()
