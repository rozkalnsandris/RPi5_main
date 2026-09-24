#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import sys
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_private_bigquery_runtime_materialization as materialization
from deploy_executor import weather_private_bigquery_runtime_mode_recovery as recovery

DISPATCH_PATH = ROOT / "ops/lib/deploy_executor/weather_private_privileged_dispatch.py"
WORKFLOW_PATH = ROOT / ".github/workflows/weathernext-private-runtime-mode-recovery-source.yml"
CONTRACT_PATH = ROOT / "ops/deploy/weather-private-runtime-mode-recovery.json"


def incident_receipt() -> materialization.RuntimeArtifactReceipt:
    lock = materialization.load_runtime_lock()
    return materialization.RuntimeArtifactReceipt(
        source_sha=recovery.INCIDENT_SOURCE_SHA,
        closure_sha256=lock["closure_sha256"],
        artifact_sha256="2" * 64,
        artifact_size_bytes=1024,
        artifact_format=materialization.ARTIFACT_FORMAT,
        target_os=materialization.TARGET_OS,
        target_architecture=materialization.TARGET_ARCH,
        target_python_version=materialization.TARGET_PYTHON_VERSION,
        target_python_abi=materialization.TARGET_PYTHON_ABI,
        target_platform=materialization.TARGET_PIP_PLATFORM,
    )


def incident_actions() -> recovery.RuntimeActionsEvidence:
    return recovery.RuntimeActionsEvidence(
        source_sha=recovery.INCIDENT_SOURCE_SHA,
        run_id=123,
        artifact_id=456,
        artifact_name=f"weathernext-private-runtime-{recovery.INCIDENT_SOURCE_SHA}",
        artifact_digest="sha256:" + "3" * 64,
    )


def simple_wheel() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("alpha/__init__.py", b"x = 1\n")
        archive.writestr("alpha/data/value.txt", b"value\n")
        archive.writestr("sample-1.0.data/purelib/beta/mod.py", b"y = 2\n")
    return buffer.getvalue()


class WeatherNextPrivateRuntimeModeRecoveryTests(unittest.TestCase):
    def test_source_contract_is_distinct_and_tightly_bounded(self) -> None:
        summary = recovery.source_readiness()
        self.assertEqual(summary["implementation_issue"], 717)
        self.assertEqual(summary["operation_id"], "rpi5.weathernext-private-runtime-mode-recovery.v1")
        self.assertEqual(summary["target_alias"], "rpi5-weathernext-private-runtime-mode-recovery")
        self.assertEqual(summary["incident_source_sha"], recovery.INCIDENT_SOURCE_SHA)
        self.assertEqual(
            summary["mutation_budget"],
            (("filesystem.weathernext-private-runtime-directory-mode-reconciliation", 1),),
        )
        for key in (
            "artifact_republish_authority",
            "runtime_rematerialization_authority",
            "credential_acquisition_authority",
            "google_action_allowed",
            "bigquery_action_allowed",
            "sqlite_write_allowed",
            "docker_action_allowed",
            "systemd_action_allowed",
            "package_manager_authority",
            "network_control_authority",
            "source_merge_authorizes_live",
            "production_mutation_started",
        ):
            self.assertFalse(summary[key], key)

    def test_manifest_is_derived_from_reviewed_wheel_targets(self) -> None:
        manifest = recovery._manifest_from_wheels(
            {"sample.whl": simple_wheel()},
            {"packages": [{"filename": "sample.whl"}]},
        )
        self.assertEqual(set(manifest.directories), {"alpha", "alpha/data", "beta"})
        files = {item.relative_path: item for item in manifest.files}
        self.assertEqual(
            set(files),
            {"alpha/__init__.py", "alpha/data/value.txt", "beta/mod.py"},
        )
        self.assertEqual(
            files["alpha/__init__.py"].sha256,
            hashlib.sha256(b"x = 1\n").hexdigest(),
        )

    def test_manifest_rejects_symlink(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            info = zipfile.ZipInfo("bad-link")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, b"target")
        with self.assertRaisesRegex(recovery.WeatherNextPrivateRuntimeModeRecoveryError, "symlinks"):
            recovery._manifest_from_wheels(
                {"sample.whl": buffer.getvalue()},
                {"packages": [{"filename": "sample.whl"}]},
            )

    def test_mode_classifier_accepts_only_uniform_incident_or_exact(self) -> None:
        self.assertEqual(recovery._classify_modes(0o700, (0o700, 0o700)), "INCIDENT")
        self.assertEqual(recovery._classify_modes(0o755, (0o755, 0o755)), "EXACT")
        self.assertEqual(recovery._classify_modes(0o700, (0o700, 0o755)), "CONFLICT")

    def _runtime_fixture(
        self,
        temp: str,
        *,
        mode: int = 0o700,
        unexpected: bool = False,
        symlink: bool = False,
        drift_bytes: bool = False,
    ) -> tuple[Path, recovery.ExpectedRuntimeManifest]:
        runtime = Path(temp) / "runtime"
        site = runtime / materialization.RUNTIME_SITE_PACKAGES_NAME
        nested = site / "pkg" / "data"
        nested.mkdir(parents=True)
        payload = b"reviewed\n"
        file_path = nested / "value.txt"
        file_path.write_bytes(b"drifted\n" if drift_bytes else payload)
        os.chmod(file_path, 0o644)
        for path in (runtime, site, site / "pkg", nested):
            os.chmod(path, mode)
        if unexpected:
            extra = site / "unexpected"
            extra.mkdir()
            os.chmod(extra, mode)
        if symlink:
            (site / "link").symlink_to("pkg")
        receipt = incident_receipt()
        marker = runtime / materialization.RUNTIME_MARKER_NAME
        marker.write_text(
            json.dumps(
                {
                    "schema": "rozkalns-weather.weathernext-private-runtime-installed.v1",
                    "operation_id": materialization.OPERATION_ID,
                    "source_sha": receipt.source_sha,
                    "closure_sha256": receipt.closure_sha256,
                    "artifact_sha256": receipt.artifact_sha256,
                    "target_python_abi": materialization.TARGET_PYTHON_ABI,
                    "target_platform": materialization.TARGET_PIP_PLATFORM,
                    "package_count": len(materialization.load_runtime_lock()["packages"]),
                    "credential_binding": False,
                    "project_binding": False,
                    "analytics_hub_link": False,
                    "bigquery_access": False,
                    "sqlite_write": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        os.chmod(marker, 0o644)
        manifest = recovery.ExpectedRuntimeManifest(
            directories=("pkg", "pkg/data"),
            files=(
                recovery.ExpectedRuntimeFile(
                    "pkg/data/value.txt",
                    len(payload),
                    hashlib.sha256(payload).hexdigest(),
                ),
            ),
        )
        return runtime, manifest

    def test_runtime_tree_accepts_exact_incident_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime, manifest = self._runtime_fixture(temp)
            with (
                mock.patch.object(recovery, "RUNTIME_BASE", runtime),
                mock.patch.object(recovery, "ROOT_UID", os.getuid()),
                mock.patch.object(recovery, "ROOT_GID", os.getgid()),
            ):
                paths, modes = recovery._validate_runtime_tree(incident_receipt(), manifest)
        self.assertEqual(len(paths), 4)
        self.assertEqual(set(modes), {0o700})

    def test_runtime_tree_rejects_unexpected_symlink_and_content_drift(self) -> None:
        for variant in ("unexpected", "symlink", "drift"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temp:
                runtime, manifest = self._runtime_fixture(
                    temp,
                    unexpected=variant == "unexpected",
                    symlink=variant == "symlink",
                    drift_bytes=variant == "drift",
                )
                with (
                    mock.patch.object(recovery, "RUNTIME_BASE", runtime),
                    mock.patch.object(recovery, "ROOT_UID", os.getuid()),
                    mock.patch.object(recovery, "ROOT_GID", os.getgid()),
                ):
                    with self.assertRaises(recovery.WeatherNextPrivateRuntimeModeRecoveryError):
                        recovery._validate_runtime_tree(incident_receipt(), manifest)

    def test_incident_directory_chmod_uses_fixed_fd_and_exact_preimage(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "directory"
            path.mkdir()
            os.chmod(path, 0o700)
            with (
                mock.patch.object(recovery, "ROOT_UID", os.getuid()),
                mock.patch.object(recovery, "ROOT_GID", os.getgid()),
            ):
                recovery._chmod_incident_directory_exact(path)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755)
                with self.assertRaisesRegex(
                    recovery.WeatherNextPrivateRuntimeModeRecoveryError,
                    "changed before mutation",
                ):
                    recovery._chmod_incident_directory_exact(path)

    def test_build_plan_is_noop_for_exact_and_one_category_for_incident(self) -> None:
        receipt = incident_receipt()
        actions = incident_actions()
        manifest = recovery.ExpectedRuntimeManifest(
            directories=("pkg",),
            files=(recovery.ExpectedRuntimeFile("pkg/value.txt", 1, hashlib.sha256(b"x").hexdigest()),),
        )
        paths = (Path("/fixed/runtime"), Path("/fixed/cache"))
        current_sha = "4" * 40
        for state, expected in (
            ("EXACT", ()),
            ("INCIDENT", (recovery.MUTATION_BUDGET[0][0],)),
        ):
            with self.subTest(state=state), mock.patch.object(
                recovery,
                "_validated_incident_state",
                return_value=(receipt, actions, manifest, paths, state),
            ):
                plan = recovery.build_recovery_plan(
                    current_sha,
                    recovery.FixedPublicGitHubReadClient(sender=object()),
                )
                self.assertEqual(plan.mutation_categories, expected)

    def test_registry_and_live_authority_are_exact_recovery_only(self) -> None:
        registry = recovery._fixed_registry()
        self.assertFalse(registry.execution_enabled)
        self.assertEqual(len(registry.operations), 1)
        operation = registry.operations[0]
        self.assertEqual(operation.operation_id, recovery.OPERATION_ID)
        self.assertEqual(operation.target_alias, recovery.TARGET_ALIAS)
        self.assertEqual(
            tuple((m.category, m.max_operations) for m in operation.mutation_budget),
            recovery.MUTATION_BUDGET,
        )

        class Accepted:
            payload = {
                "queue_repository": "rozkalnsandris/ops-workflows",
                "source_repository": "rozkalnsandris/RPi5_main",
                "target_alias": recovery.TARGET_ALIAS,
                "operation_id": recovery.OPERATION_ID,
                "expected_baseline": {"kind": "resolver", "value": recovery.BASELINE_RESOLVER_ID},
                "mutation_budget": [
                    {"category": category, "max_operations": maximum}
                    for category, maximum in recovery.MUTATION_BUDGET
                ],
                "rollback_policy": "NONE",
                "exclusions": list(recovery.REQUIRED_EXCLUSIONS),
            }

        recovery._require_live_authority(Accepted())
        bad = Accepted()
        bad.payload = dict(Accepted.payload)
        bad.payload["mutation_budget"] = []
        with self.assertRaisesRegex(
            recovery.WeatherNextPrivateRuntimeModeRecoveryError,
            "mutation_budget",
        ):
            recovery._require_live_authority(bad)

    def test_no_generic_recursive_chmod_or_dynamic_execution_surface(self) -> None:
        source = (
            ROOT / "ops/lib/deploy_executor/weather_private_bigquery_runtime_mode_recovery.py"
        ).read_text(encoding="utf-8")
        forbidden = (
            "chmod -R",
            "os.walk(",
            ".rglob(",
            "subprocess",
            "Popen(",
            "shell=True",
            "os.environ",
            "requests.",
            "urllib",
            "curl ",
            "GITHUB_TOKEN",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "pip install",
            "apt ",
        )
        for token in forbidden:
            self.assertNotIn(token, source)
        self.assertIn("os.scandir(", source)
        self.assertIn("os.fchmod(", source)
        self.assertIn("O_NOFOLLOW", source)

    def test_dispatch_workflow_and_machine_contract_are_recovery_scoped(self) -> None:
        dispatch = DISPATCH_PATH.read_text(encoding="utf-8")
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertIn("RUNTIME_MODE_RECOVERY_OPERATION_ID", dispatch)
        self.assertIn("run_privileged_runtime_mode_recovery", dispatch)
        self.assertIn("test-deploy-executor-weather-private-runtime-mode-recovery.py", workflow)
        self.assertEqual(contract["implementation_issue"], 717)
        self.assertEqual(contract["operation_id"], recovery.OPERATION_ID)
        self.assertEqual(contract["target_alias"], recovery.TARGET_ALIAS)
        self.assertEqual(
            contract["mutation_budget"],
            [{"category": recovery.MUTATION_BUDGET[0][0], "max_operations": 1}],
        )
        self.assertTrue(contract["exact_existing_state_is_noop"])
        self.assertFalse(contract["source_merge_authorizes_live"])
        self.assertFalse(contract["runtime_rematerialization_authority"])

    def test_replay_consume_precedes_apply_and_success_marking_in_source(self) -> None:
        source = (
            ROOT / "ops/lib/deploy_executor/weather_private_bigquery_runtime_mode_recovery.py"
        ).read_text(encoding="utf-8")
        consume = source.index("replay.consume(accepted.request_id)")
        apply = source.index("apply_recovery_plan(preconsume_plan, public_client)")
        succeeded = source.index("replay.mark_succeeded(accepted.request_id)")
        self.assertLess(consume, apply)
        self.assertLess(apply, succeeded)


if __name__ == "__main__":
    unittest.main()
