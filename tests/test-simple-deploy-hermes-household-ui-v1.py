#!/usr/bin/env python3
"""Source-only integration checks; no protected files, Compose or host access."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def read_json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


class HouseholdConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.contract = read_json("ops/contracts/simple-deploy-hermes-household-ui-v1.json")
        self.adapter = ROOT / self.contract["compose"]["source"]

    def test_adapter_adds_only_fixed_public_settings_to_legacy_model(self):
        legacy = ROOT / self.contract["legacy_adapter"]["source"]
        self.assertEqual(hashlib.sha256(legacy.read_bytes()).hexdigest(),
                         "644dc72da5dc13ee532dd29693db31358451669bb44de4df4b62c41736903f1c")
        addition = ("      HERMES_HOUSEHOLD_ID: home\n"
                    "      HERMES_PUBLIC_ORIGIN: https://deals.rozkalns.net\n")
        model = self.adapter.read_text(encoding="utf-8")
        self.assertEqual(model.count(addition), 1)
        self.assertEqual(model.replace(addition, ""), legacy.read_text(encoding="utf-8"))
        self.assertIn("      HERMES_UI_ASSET_MODE: inline-w3\n" + addition, model)
        self.assertNotIn("${", model)
        # Exact byte delta preserves API-only services, protected env path,
        # dependency isolation, network, mounts and health semantics.

    def test_current_registry_host_contract_and_bytes_agree(self):
        target = next(t for t in read_json("ops/deploy/simple-deploy-targets-v1.json")["targets"]
                      if t["target_alias"] == "hermes-deals")
        host = read_json("ops/contracts/simple-deploy-host-v1.json")
        # Locate the host's reviewed target without depending on unrelated settings.
        def dictionaries(value):
            if isinstance(value, dict):
                yield value
                for child in value.values():
                    yield from dictionaries(child)
            elif isinstance(value, list):
                for child in value:
                    yield from dictionaries(child)
        reviewed = next(v for v in dictionaries(host)
                        if v.get("target_alias") == "hermes-deals" and "compose_source" in v)
        digest = hashlib.sha256(self.adapter.read_bytes()).hexdigest()
        self.assertEqual(target["compose"], {
            "file": self.adapter.name, "file_sha256": digest,
            "project": "hermes-deals", "service": "api",
        })
        self.assertEqual(reviewed["compose_source"], self.contract["compose"]["source"])
        self.assertEqual(reviewed["compose_sha256"], digest)
        self.assertEqual(self.contract["compose"]["sha256"], digest)
        self.assertEqual(reviewed["consumer_contract_revision"], self.contract["consumer"]["revision"])

    def test_origin_matches_tracked_ingress_and_private_projection_stays_two_key(self):
        ingress = read_json("ops/contracts/ingress-registry-v1.json")
        def services(value):
            if isinstance(value, dict):
                if value.get("service_id") == "hermes-deals":
                    yield value
                for child in value.values():
                    yield from services(child)
            elif isinstance(value, list):
                for child in value:
                    yield from services(child)
        service, = services(ingress)
        self.assertEqual(self.contract["public_environment"], {
            "HERMES_HOUSEHOLD_ID": "home",
            "HERMES_PUBLIC_ORIGIN": "https://" + service["hostname"],
        })
        self.assertTrue(service["access_required"])
        private = read_json("ops/contracts/simple-deploy-hermes-compat-v1.json")["private_runtime_config"]
        self.assertEqual(self.contract["private_environment"]["path"], private["path"])
        self.assertEqual(self.contract["private_environment"]["keys"], private["required_keys"])
        self.assertEqual(private["required_keys"], ["DATABASE_URL", "HTTP_USER_AGENT"])
        self.assertFalse(self.contract["private_environment"]["projection_changed"])

    def test_legacy_adoption_still_binds_legacy_bytes_and_registry(self):
        adoption = read_json("ops/contracts/simple-deploy-hermes-adoption-v1.json")["desired"]
        self.assertEqual(adoption["hermes_compose_source"], self.contract["legacy_adapter"]["source"])
        self.assertEqual(adoption["hermes_compose_sha256"], self.contract["legacy_adapter"]["sha256"])
        baseline = ROOT / adoption["registry_source"]
        self.assertEqual(hashlib.sha256(baseline.read_bytes()).hexdigest(), adoption["registry_sha256"])
        legacy_target = next(t for t in json.loads(baseline.read_text())["targets"]
                             if t["target_alias"] == "hermes-deals")
        self.assertEqual(legacy_target["compose"]["file"], "hermes-deals-api.yml")
        self.assertEqual(legacy_target["compose"]["file_sha256"], adoption["hermes_compose_sha256"])

    def test_source_registration_does_not_enable_materialization_or_activation(self):
        self.assertFalse(self.contract["activation_eligible"])
        self.assertFalse(self.contract["runtime_installation_performed"])
        self.assertFalse(self.contract["merge_authorizes_live"])
        v4 = read_json("ops/contracts/simple-deploy-hermes-prerequisite-materialization-v4.json")
        self.assertFalse(v4["activation_eligible"])
        self.assertFalse(v4["apply_available"])
        self.assertEqual(v4["status"], "SOURCE_ONLY_NO_APPLY_CONSUMER_ACCESS_UNPROVEN")


if __name__ == "__main__":
    unittest.main()
