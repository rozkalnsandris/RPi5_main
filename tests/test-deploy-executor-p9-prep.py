from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.github_app_auth import RawResponse
from deploy_executor.p9_canary import (
    BaselineEvidence,
    P9CanaryError,
    P9DryRunReady,
    run_p9_dry_run_canary,
)
from deploy_executor.p9_isolated_auth_surface import IsolatedAuthSurfaceContract, load_contract
from deploy_executor.p9_runtime import build_p9_read_clients, run_p9_one_shot
from deploy_executor.source_evidence import SourceEvidenceError, verify_source_evidence

SHA = "a" * 40
MAIN = "b" * 40
NOW = datetime(2026, 8, 28, 18, 0, tzinfo=timezone.utc)
SURFACE_PATH = ROOT / "ops" / "deploy" / "executor-p9-isolated-auth-surface.json"


@dataclass
class Response:
    value: object
    server_time: datetime = NOW


def surface() -> IsolatedAuthSurfaceContract:
    return IsolatedAuthSurfaceContract(
        authorization_repository="rozkalnsandris/deploy-authorizations",
        authorization_repository_id=1350486101,
        accepted_repository_id=1350486101,
        queue_repository="rozkalnsandris/ops-workflows",
        queue_repository_id=1328835922,
        owner_user_id=277435981,
        activation_enabled=False,
        runtime_binding_ready=False,
        host_wiring_enabled=False,
        production_mutation_enabled=False,
    )


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
    repository_id = 1350486101
    issue_id = 5001
    issue_number = 77
    request_id = "123e4567-e89b-42d3-a456-426614174000"
    canonical_payload_sha256 = "c" * 64
    raw_body_sha256 = "d" * 64
    payload = {
        "queue_repository": "rozkalnsandris/ops-workflows",
        "queue_issue": 15,
        "source_repository": "rozkalnsandris/hermes-deals",
        "source_sha": SHA,
        "target_alias": "hermes-deals-origin-path-audit",
        "operation_id": "hermes-deals.origin-path-audit.v1",
        "expected_baseline": {
            "kind": "resolver",
            "value": "hermes-deals.origin-path-registration.v1",
        },
    }


class AuthorizationClient:
    def __init__(self, *, drift_final_identity=False):
        self.accepted = Accepted()
        self.calls = []
        self.verified = False
        self.probes = 0
        self.drift_final_identity = drift_final_identity

    def get_json(self, path):
        self.calls.append(path)
        if path == "/repos/rozkalnsandris/deploy-authorizations":
            self.probes += 1
            repo_id = 1 if self.drift_final_identity and self.probes == 2 else 1350486101
            return Response(
                {
                    "id": repo_id,
                    "full_name": "rozkalnsandris/deploy-authorizations",
                }
            )
        raise AssertionError(path)

    def read_live_auth(self, issue_number, *, governance_ok, approved_operator_app_ids=frozenset()):
        self.calls.append(("read", issue_number, governance_ok, approved_operator_app_ids))
        if approved_operator_app_ids:
            raise AssertionError("P9 must not approve operator integrations")
        return self.accepted

    def verify_live_auth_unchanged(self, accepted, *, governance_ok, approved_operator_app_ids=frozenset()):
        self.calls.append(("verify", accepted.issue_number, governance_ok, approved_operator_app_ids))
        if approved_operator_app_ids:
            raise AssertionError("P9 must not approve operator integrations")
        self.verified = True


class QueueClient:
    def __init__(self, *, repository_id=1328835922):
        self.repository_id = repository_id
        self.calls = []

    def get_json(self, path):
        self.calls.append(path)
        if path == "/repos/rozkalnsandris/ops-workflows":
            return Response(
                {
                    "id": self.repository_id,
                    "full_name": "rozkalnsandris/ops-workflows",
                }
            )
        if path == "/repos/rozkalnsandris/ops-workflows/issues/15":
            return Response(
                {
                    "number": 15,
                    "repository_url": "https://api.github.com/repos/rozkalnsandris/ops-workflows",
                }
            )
        raise AssertionError(path)


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
        return {
            "read_only": True,
            "execution_enabled": False,
            "privileged_dispatch_ready": False,
            "result": "SOURCE_CANARY_CONTRACT_PASS",
        }

    def apply(self, prepared):
        self.apply_called = True
        raise AssertionError("P9 must never apply")


class Catalog:
    def __init__(self, adapter):
        self.adapter = adapter

    def require(self, adapter_id):
        self.adapter_id = adapter_id
        return self.adapter


def baseline(matched=True):
    return BaselineEvidence(
        resolver_id="hermes-deals.origin-path-registration.v1",
        target_alias="hermes-deals-origin-path-audit",
        matched=matched,
        evidence_id="registration:observed" if matched else "registration:mismatch",
    )


def run_canary(
    *,
    authorization=None,
    queue=None,
    auth_surface=None,
    normalized_factory=Normalized,
    adapter=None,
    baseline_result=None,
):
    authorization = authorization or AuthorizationClient()
    queue = queue or QueueClient()
    auth_surface = auth_surface or surface()
    adapter = adapter or Adapter()
    binding_calls = []
    result = run_p9_dry_run_canary(
        issue_number=77,
        authorization_client=authorization,
        queue_client=queue,
        source_client=SourceClient(),
        auth_surface=auth_surface,
        state_store=StateStore(),
        registry=object(),
        adapter_catalog=Catalog(adapter),
        normalize_ready_queue=lambda issue, **kwargs: normalized_factory(),
        validate_queue_binding=lambda accepted, protocol_queue: binding_calls.append(
            (accepted, protocol_queue)
        ),
        verify_source_evidence=verify_source_evidence,
        resolve_baseline=lambda operation, expected: baseline_result or baseline(),
        prepare_operation=lambda normalized: SimpleNamespace(
            adapter_id="hermes-deals.origin-path-audit.v1",
            execution_enabled=False,
        ),
    )
    return result, authorization, queue, adapter, binding_calls


class TokenRequester:
    def __init__(self, *, write_permission=False):
        self.calls = []
        self.write_permission = write_permission

    def __call__(self, method, path, headers, body):
        self.calls.append((method, path, dict(headers), body))
        date = "Fri, 28 Aug 2026 18:00:00 GMT"
        repositories = {
            1328835922: "rozkalnsandris/ops-workflows",
            1350486101: "rozkalnsandris/deploy-authorizations",
        }
        repository_by_path = {
            "/repos/rozkalnsandris/ops-workflows/installation": 1328835922,
            "/repos/rozkalnsandris/deploy-authorizations/installation": 1350486101,
        }
        if method == "GET" and path in repository_by_path:
            return RawResponse(
                200,
                {"date": date},
                {
                    "id": 157217641,
                    "app_id": 4748870,
                    "target_id": 277435981,
                    "target_type": "User",
                    "repository_selection": "selected",
                    "account": {
                        "id": 277435981,
                        "login": "rozkalnsandris",
                        "type": "User",
                    },
                    "permissions": {
                        "issues": "write" if self.write_permission else "read",
                        "metadata": "read",
                    },
                },
            )
        if method == "POST" and path == "/app/installations/157217641/access_tokens":
            payload = json.loads(body.decode("utf-8"))
            repository_id = payload["repository_ids"][0]
            return RawResponse(
                201,
                {"date": date},
                {
                    "token": "ghs_" + str(repository_id) + "x" * 30,
                    "expires_at": "2026-08-28T19:00:00Z",
                    "permissions": {"issues": "read", "metadata": "read"},
                    "repositories": [
                        {
                            "id": repository_id,
                            "full_name": repositories[repository_id],
                        }
                    ],
                },
            )
        raise AssertionError((method, path))


class NeverSender:
    def send(self, *, method, url, headers):
        raise AssertionError("synthetic composition test must not make REST calls")


class P9PrepTests(unittest.TestCase):
    def test_source_evidence_accepts_ancestor_exact_sha_and_successful_ci(self):
        result = verify_source_evidence(
            SourceClient(),
            source_repository="rozkalnsandris/hermes-deals",
            source_sha=SHA,
        )
        self.assertEqual(result.repository_id, 1317143994)
        self.assertEqual(result.source_sha, SHA)
        self.assertEqual(result.current_main_sha, MAIN)
        self.assertEqual(result.workflow, "ci.yml")
        self.assertEqual(result.run_id, 91)

    def test_source_evidence_rejects_nonancestor_and_failed_ci(self):
        with self.assertRaisesRegex(SourceEvidenceError, "merge base"):
            verify_source_evidence(
                SourceClient(merge_base="f" * 40),
                source_repository="rozkalnsandris/hermes-deals",
                source_sha=SHA,
            )
        with self.assertRaisesRegex(SourceEvidenceError, "no successful"):
            verify_source_evidence(
                SourceClient(ci_success=False),
                source_repository="rozkalnsandris/hermes-deals",
                source_sha=SHA,
            )

    def test_source_evidence_rejects_repository_identity_drift_and_unknown_repo(self):
        with self.assertRaisesRegex(SourceEvidenceError, "numeric identity"):
            verify_source_evidence(
                SourceClient(repository_id=1),
                source_repository="rozkalnsandris/hermes-deals",
                source_sha=SHA,
            )
        with self.assertRaisesRegex(SourceEvidenceError, "allowlist"):
            verify_source_evidence(
                SourceClient(),
                source_repository="rozkalnsandris/unknown",
                source_sha=SHA,
            )

    def test_p9_emits_only_dry_run_ready_after_split_read_only_gates(self):
        result, authorization, queue, adapter, binding_calls = run_canary()
        self.assertEqual(result.result, "DRY_RUN_READY")
        self.assertFalse(result.mutation_dispatch_enabled)
        self.assertFalse(result.result_writer_enabled)
        self.assertFalse(result.production_mutation_started)
        self.assertTrue(authorization.verified)
        self.assertFalse(adapter.apply_called)
        self.assertEqual(len(binding_calls), 1)
        self.assertIn("/repos/rozkalnsandris/deploy-authorizations", authorization.calls)
        self.assertNotIn(
            "/repos/rozkalnsandris/ops-workflows/issues/15",
            authorization.calls,
        )
        self.assertIn(
            "/repos/rozkalnsandris/ops-workflows/issues/15",
            queue.calls,
        )

    def test_p9_rejects_dormant_surface_drift_before_authority_acceptance(self):
        authorization = AuthorizationClient()
        with self.assertRaisesRegex(P9CanaryError, "runtime_binding_ready"):
            run_canary(
                authorization=authorization,
                auth_surface=replace(surface(), runtime_binding_ready=True),
            )
        self.assertFalse(
            any(
                isinstance(row, tuple) and row[0] == "read"
                for row in authorization.calls
            )
        )

    def test_p9_rejects_queue_repository_identity_drift(self):
        with self.assertRaisesRegex(P9CanaryError, "queue repository identity"):
            run_canary(queue=QueueClient(repository_id=1))

    def test_p9_rejects_execution_enabled_queue_and_never_applies(self):
        class EnabledNormalized(Normalized):
            execution_enabled = True

        adapter = Adapter()
        with self.assertRaisesRegex(P9CanaryError, "execution-disabled"):
            run_canary(normalized_factory=EnabledNormalized, adapter=adapter)
        self.assertFalse(adapter.apply_called)

    def test_p9_rejects_baseline_mismatch_before_adapter_preflight(self):
        adapter = Adapter()
        with self.assertRaisesRegex(P9CanaryError, "baseline"):
            run_canary(adapter=adapter, baseline_result=baseline(matched=False))
        self.assertFalse(adapter.apply_called)

    def test_p9_rejects_adapter_preflight_that_enables_privileged_dispatch(self):
        class UnsafeAdapter(Adapter):
            def preflight(self, prepared):
                return {
                    "read_only": True,
                    "execution_enabled": False,
                    "privileged_dispatch_ready": True,
                }

        adapter = UnsafeAdapter()
        with self.assertRaisesRegex(P9CanaryError, "privileged_dispatch_ready"):
            run_canary(adapter=adapter)
        self.assertFalse(adapter.apply_called)

    def test_p9_rejects_adapter_preflight_missing_required_safety_evidence(self):
        cases = (
            ({"execution_enabled": False, "privileged_dispatch_ready": False}, "read_only"),
            ({"read_only": True, "privileged_dispatch_ready": False}, "execution_enabled"),
            ({"read_only": True, "execution_enabled": False}, "privileged_dispatch_ready"),
        )
        for preflight_result, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                class IncompleteAdapter(Adapter):
                    def preflight(self, prepared):
                        return preflight_result

                adapter = IncompleteAdapter()
                with self.assertRaisesRegex(P9CanaryError, expected_error):
                    run_canary(adapter=adapter)
                self.assertFalse(adapter.apply_called)

    def test_p9_rechecks_authorization_repository_identity_before_final_refetch(self):
        authorization = AuthorizationClient(drift_final_identity=True)
        with self.assertRaisesRegex(P9CanaryError, "authorization repository identity"):
            run_canary(authorization=authorization)
        self.assertFalse(authorization.verified)

    def test_runtime_builds_two_single_repository_tokens_never_one_broad_token(self):
        contract = load_contract(SURFACE_PATH)
        requester = TokenRequester()
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "key.pem"
            key.write_bytes(b"K" * 512)
            key.chmod(0o600)
            clients = build_p9_read_clients(
                auth_surface=contract,
                private_key=key,
                sender=NeverSender(),
                requester=requester,
                signer=lambda payload, _key: b"signature",
            )
            queue_token = clients.queue.token_provider.get_installation_token()
            auth_token = clients.authorization.token_provider.get_installation_token()

        self.assertNotEqual(queue_token.value, auth_token.value)
        self.assertFalse(any(path == "/" for _, path, _, _ in requester.calls))
        self.assertEqual(
            [
                path
                for method, path, _headers, _body in requester.calls
                if method == "GET"
            ],
            [
                "/repos/rozkalnsandris/ops-workflows/installation",
                "/repos/rozkalnsandris/deploy-authorizations/installation",
            ],
        )
        bodies = [
            json.loads(body.decode("utf-8"))
            for method, path, _headers, body in requester.calls
            if method == "POST" and path.endswith("/access_tokens")
        ]
        self.assertEqual(
            bodies,
            [
                {"repository_ids": [1328835922], "permissions": {"issues": "read"}},
                {"repository_ids": [1350486101], "permissions": {"issues": "read"}},
            ],
        )
        self.assertNotIn(
            {"repository_ids": [1328835922, 1350486101], "permissions": {"issues": "read"}},
            bodies,
        )

    def test_runtime_one_shot_loads_accepted_surface_and_keeps_mutation_flags_false(self):
        ready = P9DryRunReady(
            result="DRY_RUN_READY",
            issue_number=77,
            request_id=Accepted.request_id,
            queue_issue=15,
            source_repository="rozkalnsandris/hermes-deals",
            source_sha=SHA,
            current_main_sha=MAIN,
            operation_id="hermes-deals.origin-path-audit.v1",
            target_alias="hermes-deals-origin-path-audit",
            baseline_resolver="hermes-deals.origin-path-registration.v1",
            baseline_evidence_id="registration:observed",
            source_ci_run_id=91,
        )
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "key.pem"
            key.write_bytes(b"K" * 512)
            key.chmod(0o600)
            with patch(
                "deploy_executor.p9_runtime.run_p9_dry_run_canary",
                return_value=ready,
            ) as mocked:
                result = run_p9_one_shot(
                    issue_number=77,
                    isolated_auth_contract_path=SURFACE_PATH,
                    executor_private_key=key,
                    source_client=object(),
                    state_store=object(),
                    registry=object(),
                    adapter_catalog=object(),
                    normalize_ready_queue=lambda *args, **kwargs: None,
                    validate_queue_binding=lambda *args, **kwargs: None,
                    verify_source_evidence=lambda *args, **kwargs: None,
                    resolve_baseline=lambda *args, **kwargs: None,
                    prepare_operation=lambda *args, **kwargs: None,
                    sender=NeverSender(),
                    requester=TokenRequester(),
                    signer=lambda payload, _key: b"signature",
                )

        self.assertIs(result, ready)
        kwargs = mocked.call_args.kwargs
        self.assertIsNot(kwargs["authorization_client"], kwargs["queue_client"])
        self.assertEqual(
            kwargs["auth_surface"].authorization_repository_id,
            1350486101,
        )
        self.assertFalse(kwargs["auth_surface"].runtime_binding_ready)
        self.assertFalse(result.production_mutation_started)
        self.assertFalse(result.mutation_dispatch_enabled)
        self.assertFalse(result.result_writer_enabled)


if __name__ == "__main__":
    unittest.main()
