from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ops/deploy/weather-private-gcs-prerequisite-rollout.json"
DISPATCH = ROOT / "ops/lib/deploy_executor/weather_private_privileged_dispatch.py"
DOC = ROOT / "docs/WEATHERNEXT_PRIVATE_GCS_PREREQUISITE_ROLLOUT.md"


class GCSSimpleCanaryBoundaryTests(unittest.TestCase):
    def test_manifest_collapses_old_prerequisites_to_one_canary_boundary(self) -> None:
        value = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(
            value["schema"],
            "rozkalns-weather.weathernext-private-gcs-simple-canary.v1",
        )
        self.assertEqual(value["implementation_issue"], 843)
        self.assertFalse(value["execution_enabled"])
        self.assertFalse(value["source_merge_authorizes_live"])

        shape = value["execution_shape"]
        self.assertEqual(shape["container"], "ephemeral")
        self.assertTrue(shape["remove_after_exit"])
        self.assertTrue(shape["exact_weather_image_required"])
        self.assertEqual(
            shape["credential_mount"]["target"],
            "/run/secrets/weathernext-google.json",
        )
        self.assertTrue(shape["credential_mount"]["read_only"])
        self.assertFalse(shape["credential_mount"]["caller_selectable_target"])
        self.assertFalse(shape["database_mount"])
        self.assertFalse(shape["application_stage"])
        self.assertFalse(shape["gcs_host_install"])
        self.assertFalse(shape["separate_gcs_runtime_materialization"])
        self.assertFalse(shape["credential_copy"])
        self.assertFalse(shape["gcs_auth_binding_creation"])

        scope = value["canary_scope"]
        self.assertEqual(scope["location_id"], "station_05480")
        self.assertEqual(scope["forecast_hours"], 6)
        self.assertFalse(scope["production_write"])
        self.assertFalse(scope["automatic_retry"])
        self.assertFalse(scope["alternate_dataset_fallback"])

        self.assertEqual(
            value["next_gate_after_merge"],
            "OWNER_AUTHORIZED_EPHEMERAL_GCS_CANARY",
        )

    def test_old_gcs_prerequisite_operations_are_not_dispatchable(self) -> None:
        source = DISPATCH.read_text(encoding="utf-8")
        forbidden = (
            "GCS_INSTALL_OPERATION_ID",
            "GCS_RUNTIME_MATERIALIZATION_OPERATION_ID",
            "GCS_AUTH_BINDING_OPERATION_ID",
            "run_privileged_gcs_install",
            "run_privileged_gcs_runtime_materialization",
            "run_privileged_gcs_auth_binding",
            "WeatherNextPrivateGCSHostInstallerError",
            "WeatherNextPrivateGCSRuntimeTransportError",
            "WeatherNextPrivateGCSAuthBindingError",
        )
        for token in forbidden:
            self.assertNotIn(token, source)

    def test_doc_has_only_one_secret_mount_and_no_old_live_chain(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("/run/secrets/weathernext-google.json", text)
        self.assertIn("one ephemeral docker run --rm", text)
        self.assertIn("no database mount", text.lower())
        self.assertIn("retired", text.lower())
        self.assertNotIn("COMPOSITE STRICT LIVE prerequisite rollout", text)
        self.assertNotIn("/var/lib/rpi5-deploy/weather-private-gcs-bindings", text)


if __name__ == "__main__":
    unittest.main()
