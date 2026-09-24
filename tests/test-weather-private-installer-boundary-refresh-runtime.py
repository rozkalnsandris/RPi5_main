from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "ops/lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from deploy_executor import weather_private_installer_boundary_refresh as contract  # noqa: E402
from deploy_executor import weather_private_installer_boundary_refresh_runtime as runtime  # noqa: E402

CURRENT = "f" * 40
STALE = "c" * 40


def stale_plan() -> contract.RefreshPlan:
    return contract.build_refresh_plan(
        contract.BoundaryEvidence(
            exact_source_sha=CURRENT,
            current_main_sha=CURRENT,
            exact_main_ci_success=True,
            manager_origin=contract.REVIEWED_ORIGIN,
            manager_snapshot_stable=True,
            trusted_present=True,
            entrypoint_present=True,
            trusted_uid=0,
            trusted_gid=0,
            trusted_mode=0o755,
            trusted_origin=contract.REVIEWED_ORIGIN,
            trusted_head_sha=STALE,
            trusted_detached=True,
            trusted_clean=True,
            trusted_head_reviewed_ancestor=True,
            trusted_entrypoint_matches_head=True,
            installed_uid=0,
            installed_gid=0,
            installed_mode=0o755,
            installed_entrypoint_matches_head=True,
            trusted_entrypoint_matches_exact_source=True,
            installed_entrypoint_matches_exact_source=True,
        )
    )


def exact_plan() -> contract.RefreshPlan:
    return contract.build_refresh_plan(
        contract.BoundaryEvidence(
            exact_source_sha=CURRENT,
            current_main_sha=CURRENT,
            exact_main_ci_success=True,
            manager_origin=contract.REVIEWED_ORIGIN,
            manager_snapshot_stable=True,
            trusted_present=True,
            entrypoint_present=True,
            trusted_uid=0,
            trusted_gid=0,
            trusted_mode=0o755,
            trusted_origin=contract.REVIEWED_ORIGIN,
            trusted_head_sha=CURRENT,
            trusted_detached=True,
            trusted_clean=True,
            trusted_head_reviewed_ancestor=True,
            trusted_entrypoint_matches_head=True,
            installed_uid=0,
            installed_gid=0,
            installed_mode=0o755,
            installed_entrypoint_matches_head=True,
            trusted_entrypoint_matches_exact_source=True,
            installed_entrypoint_matches_exact_source=True,
        )
    )


@dataclass
class Accepted:
    request_id: str = "request-1"


class Replay:
    def __init__(self):
        self.consumed: list[str] = []
        self.succeeded: list[str] = []

    def consume(self, request_id: str):
        self.consumed.append(request_id)

    def mark_succeeded(self, request_id: str):
        self.succeeded.append(request_id)


class Backend:
    def __init__(self, receipt=None, error: Exception | None = None):
        self.receipt = receipt or {
            "status": "BOUNDARY_EXACT",
            "operation_id": contract.OPERATION_ID,
            "target_alias": contract.TARGET_ALIAS,
            "source_sha": CURRENT,
            "authorization_consumed": True,
            "production_mutation_started": True,
            "mutation_categories": [item[0] for item in contract.MUTATION_BUDGET[:2]],
            "rollback_policy": "NONE",
        }
        self.error = error
        self.calls = 0

    def apply(self, prepared):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.receipt


def evidence(plan: contract.RefreshPlan) -> runtime.CanonicalBoundaryRefreshEvidence:
    return runtime.CanonicalBoundaryRefreshEvidence(
        authorization_issue_number=42,
        authorization_issue_id=4200,
        authorization_created_at="2026-09-24T00:00:00Z",
        request_id="request-1",
        request_body_sha256="a" * 64,
        current_source_sha=CURRENT,
        queue_issue_number=99,
        exact_entrypoint_sha256="b" * 64,
        stale_head_sha=STALE,
        plan=contract.public_plan(plan),
    )


def prepared(plan: contract.RefreshPlan) -> runtime.PreparedBoundary:
    fixture_root = Path("/srv/repo-owner")
    return runtime.PreparedBoundary(
        exact_source_sha=CURRENT,
        exact_entrypoint_sha256="b" * 64,
        stale_head_sha=STALE,
        stale_entrypoint_sha256="b" * 64,
        manager=runtime.ManagerCheckout(
            fixture_root / "RPi5_main",
            "repo-owner",
            1000,
            1000,
            fixture_root,
        ),
        manager_snapshot=("d" * 40, "e" * 64),
        plan=plan,
    )


class InstallerBoundaryRefreshRuntimeTests(unittest.TestCase):
    def test_source_readiness_freezes_only_issue_700_budget_and_fixed_targets(self):
        readiness = runtime.source_readiness()
        self.assertEqual(readiness["implementation_issue"], 721)
        self.assertEqual(readiness["source_contract_issue"], 700)
        self.assertEqual(readiness["operation_id"], contract.OPERATION_ID)
        self.assertEqual(readiness["caller_authority"], ("authorization_issue_number",))
        self.assertEqual(readiness["mutation_budget"], contract.MUTATION_BUDGET)
        self.assertEqual(readiness["manager_checkout_resolver"], "repo-owner-home/RPi5_main")
        self.assertEqual(readiness["trusted_checkout"], contract.TRUSTED_CHECKOUT)
        self.assertEqual(readiness["entrypoint_destination"], contract.ENTRYPOINT_DESTINATION)
        self.assertFalse(readiness["generic_shell_authority"])
        self.assertFalse(readiness["backend_install_allowed"])
        self.assertFalse(readiness["source_merge_authorizes_live"])

    def test_registry_reuses_exact_three_category_max_one_budget(self):
        registry = runtime._fixed_registry()
        self.assertFalse(registry.execution_enabled)
        self.assertEqual(len(registry.operations), 1)
        operation = registry.operations[0]
        self.assertEqual(operation.operation_id, contract.OPERATION_ID)
        self.assertEqual(operation.target_alias, contract.TARGET_ALIAS)
        self.assertEqual(
            tuple((item.category, item.max_operations) for item in operation.mutation_budget),
            contract.MUTATION_BUDGET,
        )
        self.assertEqual(operation.rollback_policy, "NONE")
        self.assertFalse(operation.ordinary_live_all_eligible)

    def test_exact_state_is_preconsume_noop(self):
        plan = exact_plan()
        replay = Replay()
        backend = Backend()
        result = runtime.execute_prevalidated_refresh(
            evidence(plan),
            prepared=prepared(plan),
            accepted=Accepted(),
            replay=replay,
            backend=backend,
        )
        self.assertEqual(result["status"], "ALREADY_EXACT")
        self.assertFalse(result["authorization_consumed"])
        self.assertFalse(result["production_mutation_started"])
        self.assertEqual(replay.consumed, [])
        self.assertEqual(replay.succeeded, [])
        self.assertEqual(backend.calls, 0)

    def test_stale_state_consumes_once_then_applies_once(self):
        plan = stale_plan()
        replay = Replay()
        backend = Backend()
        result = runtime.execute_prevalidated_refresh(
            evidence(plan),
            prepared=prepared(plan),
            accepted=Accepted(),
            replay=replay,
            backend=backend,
        )
        self.assertEqual(result["status"], "BOUNDARY_EXACT")
        self.assertEqual(replay.consumed, ["request-1"])
        self.assertEqual(replay.succeeded, ["request-1"])
        self.assertEqual(backend.calls, 1)

    def test_failure_after_consume_does_not_mark_success_or_retry(self):
        plan = stale_plan()
        replay = Replay()
        backend = Backend(error=runtime.WeatherNextPrivateInstallerBoundaryRefreshRuntimeError("boom"))
        with self.assertRaisesRegex(runtime.WeatherNextPrivateInstallerBoundaryRefreshRuntimeError, "boom"):
            runtime.execute_prevalidated_refresh(
                evidence(plan),
                prepared=prepared(plan),
                accepted=Accepted(),
                replay=replay,
                backend=backend,
            )
        self.assertEqual(replay.consumed, ["request-1"])
        self.assertEqual(replay.succeeded, [])
        self.assertEqual(backend.calls, 1)

    def test_authorization_or_plan_drift_fails_before_consume(self):
        plan = stale_plan()
        replay = Replay()
        backend = Backend()
        wrong = Accepted(request_id="request-other")
        with self.assertRaises(runtime.WeatherNextPrivateInstallerBoundaryRefreshRuntimeError):
            runtime.execute_prevalidated_refresh(
                evidence(plan),
                prepared=prepared(plan),
                accepted=wrong,
                replay=replay,
                backend=backend,
            )
        self.assertEqual(replay.consumed, [])
        self.assertEqual(backend.calls, 0)

    def test_current_identical_entrypoint_case_keeps_replace_optional(self):
        source = (ROOT / "ops/lib/deploy_executor/weather_private_installer_boundary_refresh_runtime.py").read_text(encoding="utf-8")
        self.assertIn(
            "if _sha256(_read_regular(installed)) != prepared.exact_entrypoint_sha256:",
            source,
        )
        self.assertIn("executed.append(MUTATION_BUDGET[2][0])", source)
        self.assertLess(
            source.index("if _sha256(_read_regular(installed)) != prepared.exact_entrypoint_sha256:"),
            source.index("executed.append(MUTATION_BUDGET[2][0])"),
        )

    def test_git_transport_is_fixed_and_forbidden_repair_commands_are_absent(self):
        source = (ROOT / "ops/lib/deploy_executor/weather_private_installer_boundary_refresh_runtime.py").read_text(encoding="utf-8")
        self.assertIn('"--no-optional-locks"', source)
        self.assertIn('mutation_ops = {"fetch"}', source)
        self.assertIn('tuple(args[:2]) != ("checkout", "--detach")', source)
        for forbidden in ('"clone"', '"reset"', '"clean"', '"pull"', '"rebase"', '"switch"'):
            self.assertNotIn(forbidden, source)

    def test_dispatch_contains_only_fixed_refresh_operation_route(self):
        source = (ROOT / "ops/lib/deploy_executor/weather_private_privileged_dispatch.py").read_text(encoding="utf-8")
        self.assertIn("INSTALLER_BOUNDARY_REFRESH_OPERATION_ID", source)
        self.assertIn("run_privileged_installer_boundary_refresh(issue_number)", source)


if __name__ == "__main__":
    unittest.main()
