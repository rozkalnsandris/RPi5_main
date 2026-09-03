from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dashboard-rpi5-production-candidate-stager.py"
CONTRACT = ROOT / "ops" / "deploy" / "dashboard-candidate-stager-v1.json"
loader = importlib.machinery.SourceFileLoader("dashboard_candidate_stager_repair_tested", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
module = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = module
loader.exec_module(module)


def manifest_for(path: str = "apps/web/dist/index.html", data: bytes = b"ok") -> tuple[bytes, str]:
    entry = {"path": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    core = {
        "schema": module.MANIFEST_SCHEMA,
        "sourceSha": module.REVIEWED_SOURCE_SHA,
        "releasePath": f"/opt/dashboard_RPi5/releases/{module.REVIEWED_SOURCE_SHA}",
        "nodeMajor": 24,
        "hashAlgorithm": "sha256",
        "fileCount": 1,
        "totalBytes": len(data),
        "files": [entry],
    }
    digest = hashlib.sha256(json.dumps(core, separators=(",", ":")).encode()).hexdigest()
    return json.dumps({**core, "candidateSha256": digest}, separators=(",", ":")).encode(), digest


class CandidateStagerRepairTests(unittest.TestCase):
    def test_fixed_input_is_root_owned_and_outside_executor_state(self) -> None:
        self.assertEqual(str(module.INPUT_BASE), "/var/lib/rozkalns-dashboard-candidate-input")
        self.assertEqual(str(module.INPUT_ROOT), f"{module.INPUT_BASE}/{module.REVIEWED_SOURCE_SHA}")
        self.assertFalse(str(module.INPUT_ROOT).startswith("/var/lib/rozkalns-deploy-executor/"))
        self.assertEqual(module._handoff_ids(), (0, 0))
        self.assertEqual(module.INPUT_BASE_MODE, 0o755)
        self.assertEqual(module.INPUT_DIRECTORY_MODE, 0o555)
        self.assertEqual(module.INPUT_FILE_MODE, 0o444)

    def test_machine_contract_matches_source_and_stays_disabled(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertFalse(contract["execution_enabled"])
        self.assertEqual(contract["preverified_input"]["root"], str(module.INPUT_ROOT))
        self.assertEqual(contract["preverified_input"]["owner"], "root")
        self.assertEqual(contract["preverified_input"]["group"], "root")
        self.assertFalse(contract["preverified_input"]["under_executor_state_directory"])
        self.assertFalse(contract["provenance"]["handoff_under_executor_state_directory"])
        self.assertFalse(contract["source_state"]["live_authority"])
        self.assertFalse(contract["source_state"]["merge_authorizes_staging"])

    def test_input_base_metadata_is_verified_before_candidate_root(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('base = _open_abs_dir(INPUT_BASE, "candidate input base")', source)
        self.assertIn('label="candidate input base"', source)
        self.assertIn("mode=INPUT_BASE_MODE", source)

    def test_exact_source_and_digest_binding(self) -> None:
        raw, digest = manifest_for()
        parsed = module._parse_manifest(raw, expected_digest=digest)
        self.assertEqual(parsed.source_sha, module.REVIEWED_SOURCE_SHA)
        self.assertEqual(parsed.candidate_sha256, digest)
        with self.assertRaisesRegex(module.CandidateStagerError, "LIVE binding"):
            module._parse_manifest(raw, expected_digest="0" * 64)

    def test_manifest_path_traversal_and_reserved_components_are_rejected(self) -> None:
        for path in ("../escape", "/absolute", "a/../b", "a//b", "a\\b", "node_modules/x", "candidate-manifest.json"):
            with self.subTest(path=path):
                with self.assertRaises(module.CandidateStagerError):
                    module._safe_parts(path)

    def test_cli_exposes_only_exact_digest_apply_and_ack(self) -> None:
        args = module._parse_args(["--expected-candidate", "a" * 64, "--apply", "--ack", module.ACK])
        self.assertEqual(args.expected_candidate, "a" * 64)
        self.assertTrue(args.apply)
        self.assertEqual(args.ack, module.ACK)
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("--source", "--path", "--manifest", "--command", "--script", "--environment"):
            self.assertNotIn(forbidden, source)

    def test_mutation_budget_and_output_namespace_are_unchanged(self) -> None:
        self.assertEqual(module.STAGING_MUTATION_BUDGET, (
            ("staging-namespace-root-create", 1),
            ("staging-candidate-partial-root-create", 1),
            ("staging-file-materialization", 512),
            ("staging-manifest-materialization", 1),
            ("staging-final-rename", 1),
        ))
        self.assertTrue(str(module.STAGING_ROOT).startswith("/var/lib/rozkalns-dashboard-release-candidates/"))
        self.assertFalse(str(module.STAGING_ROOT).startswith("/opt/dashboard_RPi5"))

    def test_contract_keeps_retry_cleanup_rollback_excluded(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        exclusions = set(contract["explicit_exclusions"])
        for required in ("automatic retry", "automatic cleanup", "automatic rollback", "service-owned candidate input"):
            self.assertIn(required, exclusions)

    def test_no_generic_privileged_execution_surface(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "subprocess", "os.system(", "shell=True", "Popen(", "execv(",
            "/usr/bin/node", "production-release-controller.mjs",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn('"candidate_javascript_executed_as_root": False', source)
        self.assertIn('"production_release_materializations": 0', source)
        self.assertIn('"current_pointer_swaps": 0', source)
        self.assertIn('"apply_lock_mutations": 0', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
