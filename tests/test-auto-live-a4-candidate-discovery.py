from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.auto_live_a4_discovery import (
    CandidateDecision,
    _aggregate,
    discover_once,
)

BASELINE = "a" * 40
TARGET = "b" * 40
PARENT = "c" * 40
DASHBOARD = "dashboard-rpi5-production-release"


class FakeGitHub:
    def __init__(self, *, tip_paths, full_paths=None, ci_success=True):
        self.tip_paths = list(tip_paths)
        self.full_paths = list(full_paths if full_paths is not None else tip_paths)
        self.ci_success = ci_success
        self.calls = []

    def _files(self, paths):
        return [{"filename": path, "status": "modified"} for path in paths]

    def get_json(self, path):
        self.calls.append(path)
        if path == "/repos/rozkalnsandris/dashboard_RPi5":
            return SimpleNamespace(value={"full_name": "rozkalnsandris/dashboard_RPi5", "default_branch": "main"})
        if path == "/repos/rozkalnsandris/dashboard_RPi5/branches/main":
            return SimpleNamespace(value={"commit": {"sha": TARGET}})
        if path.startswith("/repos/rozkalnsandris/dashboard_RPi5/actions/runs?"):
            rows = []
            if self.ci_success:
                rows = [{
                    "id": 9001,
                    "head_sha": TARGET,
                    "path": ".github/workflows/ci.yml",
                    "name": "CI",
                    "event": "push",
                    "head_branch": "main",
                    "conclusion": "success",
                }]
            return SimpleNamespace(value={"total_count": len(rows), "workflow_runs": rows})
        if path == "/repos/rozkalnsandris/dashboard_RPi5/actions/runs/9001/jobs?per_page=100":
            return SimpleNamespace(value={"total_count": 1, "jobs": [{"name": "FAST-LANE Merge Gate", "conclusion": "success"}]})
        if path == f"/repos/rozkalnsandris/dashboard_RPi5/commits/{TARGET}":
            return SimpleNamespace(value={"sha": TARGET, "parents": [{"sha": PARENT}]})
        if path == f"/repos/rozkalnsandris/dashboard_RPi5/compare/{PARENT}...{TARGET}":
            return SimpleNamespace(value={"status": "ahead", "files": self._files(self.tip_paths)})
        if path == f"/repos/rozkalnsandris/dashboard_RPi5/compare/{BASELINE}...{TARGET}":
            return SimpleNamespace(value={"status": "ahead", "files": self._files(self.full_paths)})
        raise AssertionError(path)


def baseline_evidence(**updates):
    value = {
        "schema": "rozkalns.auto-live-production-baseline-evidence.v1",
        "evidence_source": "TRUSTED_RPI5_READ_ONLY_PREFLIGHT",
        "source_repository": "rozkalnsandris/dashboard_RPi5",
        "target_alias": DASHBOARD,
        "resolver_id": "dashboard-release-plan.v1",
        "target_sha": TARGET,
        "production_baseline_sha": BASELINE,
        "trusted": True,
        "fresh": True,
    }
    value.update(updates)
    return {DASHBOARD: value}


def candidate(decision, alias, path, sha=TARGET):
    return CandidateDecision(
        decision=decision,
        reason="fixture",
        manifest_path=path,
        source_repository="x/y",
        target_alias=alias,
        static_operation_id="x.y.v1",
        target_sha=sha,
        classification="AUTO_DEPLOY_SAFE" if decision == "ELIGIBLE_CANARY" else None,
        required_ci_run_id=1,
        changed_paths=(),
    )


class DiscoveryTests(unittest.TestCase):
    def run_discovery(self, tip_paths, *, full_paths=None, ci_success=True, baselines=None, root=ROOT):
        github = FakeGitHub(tip_paths=tip_paths, full_paths=full_paths, ci_success=ci_success)
        result = discover_once(github=github, root=root, production_baselines=baselines)
        return result, github

    def dashboard_result(self, result):
        return next(item for item in result.candidates if item.target_alias == DASHBOARD)

    def test_candidate_set_comes_only_from_a2_index(self):
        result, github = self.run_discovery(["apps/web/src/app.tsx"])
        self.assertEqual([c.target_alias for c in result.candidates], [DASHBOARD, "rozkalns-weather-public-rpi5"])
        weather = next(c for c in result.candidates if c.target_alias == "rozkalns-weather-public-rpi5")
        self.assertEqual(weather.decision, "NO_ELIGIBLE_CANARY")
        self.assertEqual(weather.reason, "MANIFEST_HAS_NO_AUTOMATIC_ELIGIBLE_CLASS")
        self.assertFalse(any("rozkalns_weather" in call for call in github.calls))

    def test_safe_tip_without_live_baseline_requests_fresh_preflight(self):
        result, _ = self.run_discovery(["apps/web/src/app.tsx"])
        dashboard = self.dashboard_result(result)
        self.assertEqual(dashboard.decision, "NEEDS_FRESH_LIVE_PREFLIGHT")
        self.assertEqual(result.decision, "NEEDS_FRESH_LIVE_PREFLIGHT")
        self.assertEqual(dashboard.target_sha, TARGET)

    def test_manual_and_db_tip_reject_before_baseline(self):
        for path, expected in (
            ("apps/server/src/app.ts", "MANUAL_ROLLOUT_REQUIRED"),
            ("ops/production/contract.json", "DB_HOST_APPLY_REQUIRED"),
        ):
            with self.subTest(path=path):
                result, github = self.run_discovery([path])
                dashboard = self.dashboard_result(result)
                self.assertEqual(dashboard.decision, "OWNER_REQUIRED")
                self.assertEqual(dashboard.classification, expected)
                self.assertFalse(any(call.startswith(f"/repos/rozkalnsandris/dashboard_RPi5/compare/{BASELINE}") for call in github.calls))

    def test_unknown_tip_blocks(self):
        result, _ = self.run_discovery(["future/unclassified.bin"])
        self.assertEqual(self.dashboard_result(result).decision, "BLOCKED")
        self.assertEqual(result.decision, "BLOCKED")

    def test_missing_exact_sha_ci_blocks_before_tip_read(self):
        result, github = self.run_discovery(["apps/web/src/app.tsx"], ci_success=False)
        self.assertEqual(self.dashboard_result(result).reason, "EXACT_TARGET_SHA_REQUIRED_CI_NOT_SUCCESSFUL")
        self.assertFalse(any(f"/commits/{TARGET}" in call for call in github.calls))

    def test_valid_fresh_baseline_safe_full_range_is_eligible(self):
        result, _ = self.run_discovery(
            ["apps/web/src/app.tsx"],
            full_paths=["apps/web/src/app.tsx", "apps/web/src/page.tsx"],
            baselines=baseline_evidence(),
        )
        dashboard = self.dashboard_result(result)
        self.assertEqual(dashboard.decision, "ELIGIBLE_CANARY")
        self.assertEqual(dashboard.classification, "AUTO_DEPLOY_SAFE")
        self.assertEqual(result.decision, "ELIGIBLE_CANARY")
        self.assertEqual(result.selected_target_alias, DASHBOARD)
        self.assertEqual(result.selected_target_sha, TARGET)

    def test_full_range_manual_or_db_requires_owner(self):
        for path, expected in (
            ("package-lock.json", "MANUAL_ROLLOUT_REQUIRED"),
            ("tools/release.mjs", "DB_HOST_APPLY_REQUIRED"),
        ):
            with self.subTest(path=path):
                result, _ = self.run_discovery(
                    ["apps/web/src/app.tsx"],
                    full_paths=["apps/web/src/app.tsx", path],
                    baselines=baseline_evidence(),
                )
                dashboard = self.dashboard_result(result)
                self.assertEqual(dashboard.decision, "OWNER_REQUIRED")
                self.assertEqual(dashboard.classification, expected)

    def test_stale_untrusted_or_mismatched_baseline_blocks(self):
        cases = (
            {"fresh": False},
            {"trusted": False},
            {"target_sha": "d" * 40},
            {"resolver_id": "wrong.v1"},
        )
        for update in cases:
            with self.subTest(update=update):
                result, _ = self.run_discovery(["apps/web/src/app.tsx"], baselines=baseline_evidence(**update))
                self.assertEqual(self.dashboard_result(result).decision, "BLOCKED")
                self.assertEqual(result.decision, "BLOCKED")

    def test_already_current_is_not_a_canary(self):
        result, _ = self.run_discovery(
            ["apps/web/src/app.tsx"],
            baselines=baseline_evidence(production_baseline_sha=TARGET),
        )
        self.assertEqual(self.dashboard_result(result).reason, "PRODUCTION_ALREADY_AT_TARGET")
        self.assertEqual(result.decision, "NO_ELIGIBLE_CANARY")

    def test_stable_tie_break_does_not_expand_eligibility(self):
        result = _aggregate((candidate("ELIGIBLE_CANARY", "z-target", "m/z.json"), candidate("ELIGIBLE_CANARY", "a-target", "m/a.json")))
        self.assertEqual(result.decision, "ELIGIBLE_CANARY")
        self.assertEqual(result.selected_target_alias, "a-target")
        self.assertEqual(result.selected_manifest_path, "m/a.json")

    def test_no_candidate_eligible_is_deterministic(self):
        result = _aggregate((candidate("NO_ELIGIBLE_CANARY", "a", "m/a.json", None),))
        self.assertEqual(result.decision, "NO_ELIGIBLE_CANARY")
        self.assertIsNone(result.selected_target_sha)

    def contract_root(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        paths = [
            "ops/deploy/auto-live-controller-v1.json",
            "ops/deploy/auto-live-manifests.json",
            "ops/deploy/auto-live-manifests/dashboard-rpi5.json",
            "ops/deploy/auto-live-manifests/rozkalns-weather.json",
            "ops/deploy/executor-operations.json",
        ]
        for rel in paths:
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, dst)
        return tmp, root

    def test_missing_manifest_fails_closed(self):
        tmp, root = self.contract_root()
        try:
            (root / "ops/deploy/auto-live-manifests/dashboard-rpi5.json").unlink()
            result, _ = self.run_discovery(["apps/web/src/app.tsx"], root=root)
            self.assertEqual(result.decision, "BLOCKED")
            self.assertTrue(result.reason.startswith("SOURCE_OR_EVIDENCE_INVALID:"))
        finally:
            tmp.cleanup()

    def test_missing_static_operation_fails_closed(self):
        tmp, root = self.contract_root()
        try:
            p = root / "ops/deploy/executor-operations.json"
            value = json.loads(p.read_text())
            value["operations"] = [op for op in value["operations"] if op["operation_id"] != "dashboard-rpi5.production-release.v1"]
            p.write_text(json.dumps(value))
            result, _ = self.run_discovery(["apps/web/src/app.tsx"], root=root)
            self.assertEqual(result.decision, "BLOCKED")
            self.assertIn("static_operation_id does not resolve exactly once", result.reason)
        finally:
            tmp.cleanup()

    def test_machine_contract_and_source_remain_non_mutating(self):
        contract = json.loads((ROOT / "ops/deploy/auto-live-a4-candidate-discovery.json").read_text())
        self.assertEqual(contract["status"], "A4_DISCOVERY_SOURCE_READY_LIVE_DISABLED")
        self.assertTrue(all(value is False for value in contract["mutation"].values()))
        self.assertFalse(contract["continuity"]["volatile_candidate_sha_is_canonical_state"])
        self.assertNotIn("current_dashboard_sha", json.dumps(contract).lower())
        source = (ROOT / "ops/lib/deploy_executor/auto_live_a4_discovery.py").read_text()
        for forbidden in ("subprocess", "systemctl", "docker ", ".apply(", "prepare_operation("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
