#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC = ROOT / "scripts/diagnose-weather-v9-predecessor-bootstrap-preflight.py"
CONTRACT = ROOT / "ops/recovery/weather_v9-predecessor-bootstrap-preflight-diagnostic.contract.json"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


diag = load(DIAGNOSTIC, "weather_v9_predecessor_preflight_diagnostic_test")


class Registration:
    source_sha = "5" * 40


class PassProbe:
    def __init__(self):
        self.calls = []
        self.diagnostic_source_sha = "6" * 40
        self.registration = Registration()

    def _call(self, name):
        self.calls.append(name)

    def source_identity(self): self._call("source_identity")
    def bootstrap_capability(self): self._call("bootstrap_capability")
    def predecessor_contract(self): self._call("predecessor_contract")
    def durable_baseline(self): self._call("durable_baseline")
    def execution_provenance(self): self._call("execution_provenance")
    def artifact_identity(self): self._call("artifact_identity")
    def postcondition(self): self._call("postcondition")


class FailingProbe(PassProbe):
    def __init__(self, method, exc):
        super().__init__()
        self.method = method
        self.exc = exc

    def _call(self, name):
        self.calls.append(name)
        if name == self.method:
            raise self.exc


class Tests(unittest.TestCase):
    def test_pass_is_bounded_and_read_only(self):
        probe = PassProbe()
        value = diag.diagnose(probe)
        self.assertEqual(value["result"], "PASS")
        self.assertEqual(value["diagnostic_source_sha"], "6" * 40)
        self.assertEqual(value["execution_source_sha"], "5" * 40)
        self.assertEqual(value["predecessor_source_sha"], diag.PREDECESSOR_SHA)
        self.assertIs(value["host_mutation_started"], False)
        self.assertEqual(probe.calls, [
            "source_identity", "bootstrap_capability", "predecessor_contract",
            "durable_baseline", "execution_provenance", "artifact_identity", "postcondition",
        ])

    def test_allowlisted_failure_stage_and_code_are_preserved(self):
        for stage, codes in diag.FAILURE_CODES.items():
            if stage == "INTERNAL":
                continue
            code = sorted(codes)[0]
            probe = FailingProbe(
                "source_identity",
                diag.SafeDiagnosticFailure(stage, code),
            )
            value = diag.diagnose(probe)
            self.assertEqual((value["failure_stage"], value["failure_code"]), (stage, code))
            self.assertIs(value["host_mutation_started"], False)

    def test_unknown_failures_collapse_to_internal_without_text_leak(self):
        secret = "synthetic-secret /protected/arbitrary/path"
        probe = FailingProbe("source_identity", RuntimeError(secret))
        value = diag.diagnose(probe)
        encoded = json.dumps(value, sort_keys=True)
        self.assertEqual((value["failure_stage"], value["failure_code"]), ("INTERNAL", "UNCLASSIFIED"))
        self.assertNotIn("synthetic-secret", encoded)
        self.assertNotIn("/protected/", encoded)
        malicious = diag._failure("DURABLE_BASELINE", secret)
        self.assertEqual((malicious["failure_stage"], malicious["failure_code"]), ("INTERNAL", "UNCLASSIFIED"))

    def test_contract_matches_fixed_enum_and_denies_mutation(self):
        contract = json.loads(CONTRACT.read_text())
        expected = {stage: sorted(codes) for stage, codes in diag.FAILURE_CODES.items()}
        self.assertEqual(contract["issue"], 636)
        self.assertEqual(contract["failure_codes"], expected)
        self.assertTrue(contract["root_read_only"])
        for field in (
            "writes_allowed", "systemd_mutation", "replay_mutation", "weather_runtime_mutation",
            "database_mutation", "corpus_mutation", "permission_mutation",
            "automatic_retry", "automatic_cleanup", "automatic_rollback", "source_merge_authorizes_live",
        ):
            self.assertIs(contract[field], False)

    def test_source_has_no_mutation_or_generic_root_command_surface(self):
        source = DIAGNOSTIC.read_text()
        for forbidden in (
            "os.replace", ".mkdir(", ".unlink(", "os.chmod", "os.chown",
            "systemctl", "--apply", "shell=True", "/usr/bin/sudo", "StateStore(",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("sys.dont_write_bytecode = True", source)
        self.assertIn('"INTERNAL", "UNCLASSIFIED"', source)


if __name__ == "__main__":
    unittest.main()
