#!/usr/bin/env python3
"""Source-only Weather PUBLIC rebind plan and fail-closed evidence tests."""
import importlib.util
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "scripts/weather_public_rebind_contract_v1.py"
spec = importlib.util.spec_from_file_location("weather_rebind_contract", P)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
CONTRACT = mod.contract()


def valid_evidence():
    b = CONTRACT["baseline"]
    return {
        "exact_final_main": "f" * 40,
        "checkout_exact_clean_main_origin": True,
        "installed_identity_sha": b["identity_source_sha"],
        "installed_registry_sha256": b["registry_sha256_from_readonly_host"],
        "installed_compose_sha256": b["compose_sha256_from_readonly_host"],
        "root_owned_files_mode_0444": True,
        "candidate_source_hashes_match": True,
        "non_weather_registry_targets_identical": True,
        "weather_target_exact": True,
        "target_lock_available": True,
        "no_blocking_stop_error": True,
        "weather_container_count": 1,
        "weather_running_healthy": True,
        "weather_publish_class": "wildcard",
        "weather_volume_preserved": True,
        "receipt_digest": "sha256:" + "1" * 64,
        "override_digest": "sha256:" + "1" * 64,
        "running_image_digest": "sha256:" + "1" * 64,
        "image_labels_pass": True,
        "protected_env_metadata_only": True,
    }


class WeatherRebindTests(unittest.TestCase):
    def test_source_is_hash_pinned_and_contract_bound(self):
        self.assertEqual(mod.source_errors(CONTRACT), [])
        self.assertEqual(CONTRACT["target_alias"], "rozkalns-weather-public-rpi5")
        self.assertTrue(CONTRACT["desired"]["non_weather_targets_must_be_unchanged"])
        baseline = CONTRACT["baseline"]
        self.assertEqual(baseline["registry_source_revision"],
                         "fe69b6e325fa9edec04e8963b5010f946ac4d83c")
        self.assertTrue(baseline["registry_and_identity_sources_differ"])
        self.assertNotEqual(baseline["registry_source_revision"], baseline["identity_source_sha"])
        self.assertEqual(baseline["registry_sha256_from_readonly_host"],
                         "88c3acbf304ab9676a6a767e5f3055351f20fd88ca9bf1bf4a2cb1210ef3617f")
        self.assertEqual(CONTRACT["desired"]["registry_delta_from_installed"],
                         ["weather.compose.file_sha256"])
        self.assertEqual(baseline["protected_env_file"], {
            "owner": "root", "group": "rozkalns-simple-deployer",
            "mode": "0640", "metadata_only": True,
        })

    def test_preflight_is_pure_and_safe_only_with_full_evidence(self):
        self.assertEqual(mod.preflight(CONTRACT, valid_evidence()),
                         {"result": "PASS", "blockers": [], "mutation_performed": False})
        for key, val in valid_evidence().items():
            case = valid_evidence()
            case[key] = False if type(val) is bool else (0 if type(val) is int else "unknown")
            with self.subTest(key=key):
                self.assertEqual(mod.preflight(CONTRACT, case)["result"], "BLOCKED")
        for name in ("missing", "extra"):
            case = valid_evidence()
            if name == "missing":
                case.pop("receipt_digest")
            else:
                case["raw_env"] = "forbidden"
            self.assertEqual(mod.preflight(CONTRACT, case)["result"], "BLOCKED")

    def test_exact_three_files_and_single_container_action(self):
        seq = CONTRACT["phases"]
        self.assertEqual([x["name"] for x in seq], [
            "SOURCE_PREPARE", "PREFLIGHT", "STAGE_THREE_FILES",
            "REPLACE_THREE_FILES", "WEATHER_FORCE_RECREATE",
            "LOCAL_VERIFY", "PHASE7_VERIFY",
        ])
        self.assertEqual(seq[3]["order"], [
            "/etc/rozkalns-simple-deployer/compose/rozkalns-weather-public.yml",
            "/etc/rozkalns-simple-deployer/targets.json",
            "/etc/rozkalns-simple-deployer/identity.json",
        ])
        self.assertEqual(seq[4]["argv"], [
            "/usr/bin/docker", "compose", "--project-name", "rozkalns-weather-public",
            "--file", "/etc/rozkalns-simple-deployer/compose/rozkalns-weather-public.yml",
            "--file", "/var/lib/rozkalns-simple-deployer/overrides/rozkalns-weather-public-rpi5.yaml",
            "up", "--detach", "--no-deps", "--force-recreate",
            "--pull", "never", "--wait", "--wait-timeout", "180", "weather",
        ])
        self.assertNotIn("down", seq[4]["argv"])
        self.assertNotIn("--volumes", seq[4]["argv"])

    def test_owner_gates_and_error_recovery(self):
        auth = CONTRACT["authority"]
        self.assertIs(auth["this_contract_authorizes_host"], False)
        self.assertIs(auth["this_contract_authorizes_merge"], False)
        self.assertTrue(auth["live_requires_separate_exact_merged_main_sha_and_host_target"])
        failure = CONTRACT["failure"]
        for key in ("auto_retry", "auto_rollback", "auto_cleanup"):
            self.assertIs(failure[key], False)
        self.assertTrue(failure["manual_recovery_requires_new_owner_authorization"])

    def test_phase7_is_required_after_local_health(self):
        keys = CONTRACT["postverify_required"]
        report = {key: True for key in keys}
        self.assertEqual(mod.postverify(CONTRACT, report)["result"], "PASS")
        for key in keys:
            case = {**report, key: False}
            self.assertEqual(mod.postverify(CONTRACT, case)["result"], "DRIFT")
        self.assertEqual(mod.postverify(CONTRACT, {**report, "credential": True})["result"], "BLOCKED")

    def test_source_classifier_cannot_execute_host_actions(self):
        source = P.read_text()
        for forbidden in ("subprocess", "os.system", "os.replace", "docker inspect",
                          "socket", "requests", "urllib", "os.environ"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
