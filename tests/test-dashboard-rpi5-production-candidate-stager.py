from __future__ import annotations

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

    def test_input_base_metadata_is_verified_before_candidate_root(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('base = _open_abs_dir(INPUT_BASE, "candidate input base")', source)
        self.assertIn('label="candidate input base"', source)
        self.assertIn("mode=INPUT_BASE_MODE", source)

    def test_no_generic_privileged_execution_surface(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "subprocess", "os.system(", "shell=True", "Popen(", "execv(",
            "/usr/bin/node", "production-release-controller.mjs",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn('"candidate_javascript_executed_as_root": False', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
