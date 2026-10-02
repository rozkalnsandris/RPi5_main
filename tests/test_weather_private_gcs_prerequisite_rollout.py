from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_private_gcs_auth_binding as auth_binding
from deploy_executor import weather_private_gcs_auth_binding_runtime as auth_runtime
from deploy_executor import weather_private_gcs_host_installer as gcs_installer
from deploy_executor import weather_private_gcs_host_installer_runtime as gcs_installer_runtime
from deploy_executor import weather_private_gcs_host_runtime as gcs_host
from deploy_executor import weather_private_gcs_runtime_transport as gcs_transport
from deploy_executor.weather_private_application_staging import (
    OPERATION_ID as APPLICATION_STAGE_OPERATION_ID,
)
from deploy_executor.weather_private_gcs_runtime_materialization import (
    OPERATION_ID as GCS_RUNTIME_OPERATION_ID,
)

ROLLOUT_MANIFEST = ROOT / "ops/deploy/weather-private-gcs-prerequisite-rollout.json"
DISPATCH_SOURCE = ROOT / "ops/lib/deploy_executor/weather_private_privileged_dispatch.py"
AUTH_SOURCE = ROOT / "ops/lib/deploy_executor/weather_private_gcs_auth_binding.py"
TRANSPORT_SOURCE = ROOT / "ops/lib/deploy_executor/weather_private_gcs_runtime_transport.py"
INSTALLER_SOURCE = ROOT / "ops/lib/deploy_executor/weather_private_gcs_host_installer.py"
HOST_BINDINGS_SOURCE = ROOT / "ops/lib/deploy_executor/weather_private_gcs_host_bindings.py"


class GCSPrerequisiteRolloutTests(unittest.TestCase):
    def test_manifest_has_exact_prerequisite_sequence_without_first_access(self) -> None:
        value = json.loads(ROLLOUT_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(value["implementation_issue"], 843)
        self.assertFalse(value["execution_enabled"])
        self.assertFalse(value["source_merge_authorizes_live"])
        self.assertEqual(
            [row["operation_id"] for row in value["sequence"][:4]],
            [
                gcs_host.INSTALL_OPERATION_ID,
                APPLICATION_STAGE_OPERATION_ID,
                GCS_RUNTIME_OPERATION_ID,
                auth_binding.OPERATION_ID,
            ],
        )
        self.assertEqual(
            value["sequence"][4]["operation_id"],
            "sanitized-postcondition-verification",
        )
        manifest_text = ROLLOUT_MANIFEST.read_text(encoding="utf-8")
        self.assertNotIn('"read_only_private_gcs"', manifest_text)
        self.assertFalse(value["exclusions"]["google_gcs_request"])
        self.assertFalse(value["exclusions"]["bigquery_action"])
        self.assertEqual(
            value["next_gate_after_merge"],
            "COMPOSITE_STRICT_LIVE_GCS_PREREQUISITE_ROLLOUT",
        )

    def test_gcs_host_installer_uses_only_gcs_host_paths(self) -> None:
        source = INSTALLER_SOURCE.read_text(encoding="utf-8")
        self.assertIn("weather_private_gcs_host_runtime", source)
        self.assertIn("weather_private_gcs_host_bindings.py", source)
        self.assertIn("weather-private-gcs-host-runtime.json", source)
        self.assertNotIn("weather_private_bigquery_host_runtime", source)
        self.assertNotIn("weather_private_bigquery_host_bindings", source)
        self.assertNotIn("weather-private-bigquery-host-runtime.json", source)
        self.assertIn(
            "git.weathernext-private-gcs-host-checkout-fetch",
            source,
        )
        self.assertIn(
            "filesystem.weathernext-private-gcs-host-activation-marker-write",
            source,
        )

    def test_gcs_runtime_transport_is_separate_from_bigquery_runtime(self) -> None:
        source = TRANSPORT_SOURCE.read_text(encoding="utf-8")
        self.assertIn("weathernext-private-gcs-runtime-source.yml", source)
        self.assertIn(
            "/var/lib/rpi5-deploy/weather-private-gcs-runtime/incoming",
            source,
        )
        self.assertIn("weathernext-private-gcs-runtime-", source)
        self.assertIn(
            "filesystem.weathernext-private-gcs-runtime-materialization",
            source,
        )
        self.assertNotIn("weather_private_bigquery_runtime_materialization", source)
        self.assertNotIn("/var/lib/rpi5-deploy/weather-private-runtime/incoming", source)
        self.assertNotIn('f"weathernext-private-runtime-', source)

    def test_auth_binding_reads_protected_source_only_after_consume(self) -> None:
        source = AUTH_SOURCE.read_text(encoding="utf-8")
        consume = source.index("replay.consume(evidence.request_id)")
        protected = source.index(
            "basename, credential = _source_credential_after_consume()"
        )
        self.assertLess(consume, protected)
        self.assertIn(
            'SOURCE_BINDING_ROOT = Path("/var/lib/rpi5-deploy/weather-private-bindings")',
            source,
        )
        self.assertIn(
            'BINDING_ROOT.parent / ".weather-private-gcs-bindings.partial"',
            source,
        )
        self.assertNotIn("google.auth", source)
        self.assertNotIn("google.cloud", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("obstore", source)

    def test_auth_binding_contract_has_no_caller_credential_selector(self) -> None:
        ready = auth_binding.source_readiness()
        self.assertEqual(
            ready["operation_id"],
            "rpi5.weathernext-private-gcs-auth-binding.v1",
        )
        self.assertFalse(ready["credential_path_caller_controlled"])
        self.assertFalse(ready["project_dataset_caller_controlled"])
        self.assertFalse(ready["ambient_adc_allowed"])
        self.assertFalse(ready["google_request_allowed"])
        self.assertFalse(ready["source_merge_authorizes_live"])
        self.assertEqual(
            auth_binding.MUTATION_BUDGET,
            (
                ("filesystem.weathernext-private-gcs-auth-binding-partial-root-create", 1),
                ("filesystem.weathernext-private-gcs-auth-credential-copy", 1),
                ("filesystem.weathernext-private-gcs-auth-private-binding-write", 1),
                ("filesystem.weathernext-private-gcs-auth-ready-marker-write", 1),
                ("filesystem.weathernext-private-gcs-auth-binding-publish", 1),
            ),
        )

    def test_all_new_privileged_registries_remain_execution_disabled(self) -> None:
        install_registry = gcs_installer_runtime._fixed_registry()
        runtime_registry = gcs_transport._fixed_registry()
        auth_registry = auth_runtime._fixed_registry()
        for registry in (install_registry, runtime_registry, auth_registry):
            self.assertFalse(registry.execution_enabled)

    def test_dispatch_allowlist_routes_only_named_gcs_prerequisite_operations(self) -> None:
        source = DISPATCH_SOURCE.read_text(encoding="utf-8")
        self.assertIn("GCS_INSTALL_OPERATION_ID", source)
        self.assertIn("GCS_RUNTIME_MATERIALIZATION_OPERATION_ID", source)
        self.assertIn("GCS_AUTH_BINDING_OPERATION_ID", source)
        self.assertIn("run_privileged_gcs_install", source)
        self.assertIn("run_privileged_gcs_runtime_materialization", source)
        self.assertIn("run_privileged_gcs_auth_binding", source)
        self.assertIn("APPLICATION_STAGE_OPERATION_ID", source)
        self.assertNotIn("read_only_private_gcs", source)

    def test_application_staging_is_reused_not_duplicated(self) -> None:
        value = json.loads(ROLLOUT_MANIFEST.read_text(encoding="utf-8"))
        stage = value["sequence"][1]
        self.assertEqual(stage["operation_id"], APPLICATION_STAGE_OPERATION_ID)
        self.assertEqual(stage["implementation"], "reuse_existing")

    def test_first_access_host_bindings_still_fail_closed_on_prerequisite_mutation(self) -> None:
        source = HOST_BINDINGS_SOURCE.read_text(encoding="utf-8")
        self.assertIn(
            "Weather application staging requires its separate exact LIVE gate",
            source,
        )
        self.assertIn(
            "WeatherNext GCS runtime materialization requires its separate exact LIVE gate",
            source,
        )
        self.assertIn(
            "WeatherNext GCS auth binding requires its separate protected LIVE gate",
            source,
        )
        self.assertNotIn("run_privileged_gcs_install", source)
        self.assertNotIn("run_privileged_gcs_auth_binding", source)

    def test_source_readiness_points_to_composite_live_not_gcs_request(self) -> None:
        ready = gcs_host.source_readiness()
        self.assertEqual(
            ready["source_status"],
            "SOURCE_READY_GCS_PREREQUISITE_LIVE_GATE",
        )
        self.assertTrue(ready["gcs_prerequisite_rollout_source_implemented"])
        self.assertEqual(
            ready["next_gate"],
            "COMPOSITE_STRICT_LIVE_GCS_PREREQUISITE_ROLLOUT",
        )
        self.assertFalse(ready["read_only_gcs_execution_enabled"])
        self.assertFalse(ready["source_merge_authorizes_live"])


if __name__ == "__main__":
    unittest.main()
