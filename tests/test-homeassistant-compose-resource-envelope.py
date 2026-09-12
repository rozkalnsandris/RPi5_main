#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/bin/homeassistant-compose-resource-envelope"
CONTRACT = ROOT / "ops/contracts/homeassistant-container-resource-envelope.json"

loader = importlib.machinery.SourceFileLoader("ha_envelope", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)

DESIRED = {"mem_limit": "768m", "mem_reservation": "350m", "memswap_limit": "1g"}
BASE = """services:
  grafana:
    mem_limit: 100m
  homeassistant:
    image: example/home-assistant
    mem_limit: 500m
    mem_reservation: 350m
    environment:
      PRIVATE_VALUE: preserve-this-byte-for-byte
  mosquitto:
    mem_limit: 50m
"""


class HomeAssistantEnvelopeTests(unittest.TestCase):
    def test_contract_is_exact_and_safe(self):
        data = m.load_contract(CONTRACT)
        self.assertEqual(data["resource_keys"], DESIRED)
        self.assertTrue(data["safety"]["requires_exact_input_sha256"])
        self.assertTrue(data["safety"]["requires_compose_config_validation"])

    def test_render_changes_only_allowlisted_resource_lines(self):
        candidate, changes = m.render_candidate(BASE, DESIRED)
        self.assertEqual([x["key"] for x in changes], ["mem_limit", "memswap_limit"])
        self.assertIn("    mem_limit: 768m\n", candidate)
        self.assertIn("    memswap_limit: 1g\n", candidate)
        self.assertIn("    mem_reservation: 350m\n", candidate)
        self.assertIn("      PRIVATE_VALUE: preserve-this-byte-for-byte\n", candidate)
        self.assertIn("  grafana:\n    mem_limit: 100m\n", candidate)
        self.assertIn("  mosquitto:\n    mem_limit: 50m\n", candidate)

    def test_render_is_idempotent(self):
        candidate, _ = m.render_candidate(BASE, DESIRED)
        candidate2, changes2 = m.render_candidate(candidate, DESIRED)
        self.assertEqual(candidate2, candidate)
        self.assertEqual(changes2, [])

    def test_missing_service_fails_closed(self):
        with self.assertRaisesRegex(m.EnvelopeError, "homeassistant_service_count:0"):
            m.render_candidate("services:\n  grafana:\n    image: example\n", DESIRED)

    def test_duplicate_service_fails_closed(self):
        text = "services:\n  homeassistant:\n    image: a\n  homeassistant:\n    image: b\n"
        with self.assertRaisesRegex(m.EnvelopeError, "homeassistant_service_count:2"):
            m.render_candidate(text, DESIRED)

    def test_duplicate_resource_key_fails_closed(self):
        text = "services:\n  homeassistant:\n    mem_limit: 500m\n    mem_limit: 600m\n"
        with self.assertRaisesRegex(m.EnvelopeError, "duplicate_resource_key:mem_limit"):
            m.render_candidate(text, DESIRED)

    def test_exact_sha_guard_rejects_drift(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "override.yml"
            p.write_text(BASE, encoding="utf-8")
            good = hashlib.sha256(BASE.encode()).hexdigest()
            self.assertEqual(m.verify_expected_sha(p, good), good)
            p.write_text(BASE + "# drift\n", encoding="utf-8")
            with self.assertRaisesRegex(m.EnvelopeError, "input_sha256_drift"):
                m.verify_expected_sha(p, good)

    def test_compose_validation_uses_candidate_once_and_suppresses_output(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            target = td / "override.yml"
            other = td / "base.yml"
            candidate = td / "candidate.yml"
            target.write_text(BASE, encoding="utf-8")
            other.write_text("services: {}\n", encoding="utf-8")
            candidate.write_text(BASE.replace("500m", "768m"), encoding="utf-8")
            fake = td / "fake-docker"
            args_log = td / "args.json"
            fake.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "json.dump(sys.argv[1:], open(os.environ['ARGS_LOG'], 'w'))\n"
                "print('must-not-leak')\n"
                "print('must-not-leak-stderr', file=sys.stderr)\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            old = os.environ.get("ARGS_LOG")
            os.environ["ARGS_LOG"] = str(args_log)
            try:
                m.validate_compose_candidate(target, candidate, [other, target], td, str(fake))
            finally:
                if old is None:
                    os.environ.pop("ARGS_LOG", None)
                else:
                    os.environ["ARGS_LOG"] = old
            argv = json.loads(args_log.read_text())
            self.assertIn(str(candidate), argv)
            self.assertNotIn(str(target), argv)
            self.assertEqual(argv.count(str(candidate)), 1)
            self.assertEqual(argv[-2:], ["config", "--quiet"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
