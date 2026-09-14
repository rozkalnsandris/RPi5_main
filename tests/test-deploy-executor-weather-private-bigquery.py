from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.weather_private_bigquery_contract import (
    ANALYTICS_HUB_LINK_CREATE,
    BIGQUERY_DEPENDENCY,
    CONTRACT_ID,
    EXPECTED_TABLES,
    FirstAccessScope,
    GOOGLE_AUTH_BINDING,
    GOOGLE_PROJECT_BINDING,
    INITIAL_LOCATION_ID,
    MAX_BYTES_BILLED_PER_QUERY,
    PRIVATE_RUNTIME_MATERIALIZATION,
    PRODUCTION_SQLITE_SNAPSHOT_WRITE,
    PUBLIC_RUNTIME_OPERATION_ID,
    READ_ONLY_PRIVATE_BIGQUERY,
    REQUIRED_SURFACES,
    PrivateRuntimeReadiness,
    WeatherNextPrivateContractError,
    classify_runtime_readiness,
    plan_later_owner_gate,
    source_contract_summary,
    validate_first_access_scope,
)
from deploy_executor.weather_public_runtime_adapter import REQUIRED_EXCLUSIONS

SOURCE = ROOT / "ops" / "lib" / "deploy_executor" / "weather_private_bigquery_contract.py"


class WeatherNextPrivateBigQueryContractTests(unittest.TestCase):
    def test_source_contract_is_private_source_only_and_jit_bound(self):
        contract = source_contract_summary()
        self.assertEqual(contract["contract_id"], CONTRACT_ID)
        self.assertTrue(contract["jit_weather_source_sha_required"])
        self.assertFalse(contract["execution_enabled"])
        self.assertFalse(contract["public_runtime_authority_reusable"])
        self.assertFalse(contract["google_control_plane_mutation_authorized"])
        self.assertFalse(contract["credential_mutation_authorized"])
        self.assertFalse(contract["read_only_bigquery_authorized"])
        self.assertFalse(contract["sqlite_write_authorized"])
        self.assertEqual(contract["runtime_dependency"], BIGQUERY_DEPENDENCY)
        self.assertEqual(contract["runtime_strategy"], "isolated-reviewed-python-closure")

    def test_initial_scope_accepts_only_bounded_station_canary(self):
        scope = validate_first_access_scope(FirstAccessScope(max_bytes_billed_per_query=64 * 1024 * 1024))
        self.assertEqual(scope["location_id"], INITIAL_LOCATION_ID)
        self.assertEqual(scope["forecast_hours"], 6)
        self.assertEqual(scope["required_surfaces"], REQUIRED_SURFACES)
        self.assertEqual(scope["table_names"], EXPECTED_TABLES)
        self.assertTrue(scope["dry_run_required"])
        self.assertFalse(scope["home_scope_enabled"])
        self.assertFalse(scope["sqlite_write_enabled"])
        self.assertLessEqual(scope["max_bytes_billed_per_query"], MAX_BYTES_BILLED_PER_QUERY)

    def test_scope_rejects_any_material_widening(self):
        cases = (
            (FirstAccessScope(location_id="home"), "station_10416"),
            (FirstAccessScope(forecast_hours=24), "exactly 6h"),
            (FirstAccessScope(dry_run_required=False), "dry-run"),
            (FirstAccessScope(max_bytes_billed_per_query=MAX_BYTES_BILLED_PER_QUERY + 1), "1 GiB"),
            (FirstAccessScope(max_bytes_billed_per_query=0), "positive"),
            (FirstAccessScope(home_scope_enabled=True), "home scope"),
            (FirstAccessScope(sqlite_write_enabled=True), "SQLite"),
            (FirstAccessScope(required_surfaces=("0p05_station",)), "product surfaces"),
            (FirstAccessScope(model_version_contract="2.0.0"), "model-version"),
            (FirstAccessScope(table_names=("wrong_table",)), "table identity"),
        )
        for scope, pattern in cases:
            with self.subTest(pattern=pattern):
                with self.assertRaisesRegex(WeatherNextPrivateContractError, pattern):
                    validate_first_access_scope(scope)

    def test_runtime_readiness_keeps_prerequisites_distinct(self):
        cases = (
            (PrivateRuntimeReadiness(False, False, False, False), "private_runtime_required"),
            (PrivateRuntimeReadiness(True, False, False, False), "credential_binding_required"),
            (PrivateRuntimeReadiness(True, True, False, False), "google_project_binding_required"),
            (PrivateRuntimeReadiness(True, True, True, False), "analytics_hub_link_required"),
            (PrivateRuntimeReadiness(True, True, True, True, False), "permission_denied"),
            (PrivateRuntimeReadiness(True, True, True, True, None), "read_only_access_probe_required"),
            (PrivateRuntimeReadiness(True, True, True, True, True), "ready_for_read_only_first_access"),
        )
        for evidence, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(classify_runtime_readiness(evidence), expected)

    def test_public_weather_authority_cannot_reach_private_classes(self):
        self.assertIn("Google Cloud, BigQuery or WeatherNext private access", REQUIRED_EXCLUSIONS)
        for mutation_class in (
            PRIVATE_RUNTIME_MATERIALIZATION,
            GOOGLE_AUTH_BINDING,
            GOOGLE_PROJECT_BINDING,
            ANALYTICS_HUB_LINK_CREATE,
            READ_ONLY_PRIVATE_BIGQUERY,
        ):
            with self.subTest(mutation_class=mutation_class):
                with self.assertRaisesRegex(WeatherNextPrivateContractError, "public Weather authority"):
                    plan_later_owner_gate(PUBLIC_RUNTIME_OPERATION_ID, mutation_class)

    def test_private_contract_describes_but_never_grants_later_mutations(self):
        for mutation_class in (
            PRIVATE_RUNTIME_MATERIALIZATION,
            GOOGLE_AUTH_BINDING,
            GOOGLE_PROJECT_BINDING,
            ANALYTICS_HUB_LINK_CREATE,
            READ_ONLY_PRIVATE_BIGQUERY,
        ):
            planned = plan_later_owner_gate(CONTRACT_ID, mutation_class)
            self.assertEqual(planned["mutation_class"], mutation_class)
            self.assertTrue(planned["requires_explicit_owner_gate"])
            self.assertTrue(planned["source_contract_only"])
            self.assertFalse(planned["execution_enabled"])

        sqlite = plan_later_owner_gate(CONTRACT_ID, PRODUCTION_SQLITE_SNAPSHOT_WRITE)
        self.assertTrue(sqlite["separate_from_first_access"])
        self.assertFalse(sqlite["execution_enabled"])

    def test_contract_summary_contains_no_private_identity_or_credential_values(self):
        encoded = json.dumps(source_contract_summary(), sort_keys=True)
        for forbidden in (
            "HOME_LAT",
            "HOME_LON",
            "service_account_key",
            "private_key",
            "access_token",
            "refresh_token",
            "project_id_value",
            "dataset_id_value",
        ):
            self.assertNotIn(forbidden, encoded)

    def test_source_has_no_network_shell_or_package_execution_bridge(self):
        source = SOURCE.read_text(encoding="utf-8").lower()
        for forbidden in (
            "import subprocess",
            "os.system",
            "shell=true",
            "bash -c",
            "sh -c",
            "eval(",
            "requests",
            "urllib",
            "socket.",
            "google.cloud",
            "google.auth",
            "apt install",
            "pip install",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
