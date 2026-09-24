#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import tempfile
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_private_bigquery_runtime_materialization as materialization
from deploy_executor import weather_private_bigquery_runtime_mode_recovery as recovery


def receipt() -> materialization.RuntimeArtifactReceipt:
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


def actions() -> recovery.RuntimeActionsEvidence:
    return recovery.RuntimeActionsEvidence(
        source_sha=recovery.INCIDENT_SOURCE_SHA,
        run_id=123,
        artifact_id=456,
        artifact_name=f"weathernext-private-runtime-{recovery.INCIDENT_SOURCE_SHA}",
        artifact_digest="sha256:" + "3" * 64,
    )


class WeatherNextRuntimeModeRecoverySafetyTests(unittest.TestCase):
    def test_root_owned_directory_contract_rejects_ownership_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "owned"
            path.mkdir()
            os.chmod(path, 0o700)
            with (
                mock.patch.object(recovery, "ROOT_UID", os.getuid() + 1),
                mock.patch.object(recovery, "ROOT_GID", os.getgid()),
            ):
                with self.assertRaisesRegex(
                    recovery.WeatherNextPrivateRuntimeModeRecoveryError,
                    "metadata drifted",
                ):
                    recovery._require_real_root_directory(
                        path,
                        allowed_modes=frozenset({0o700, 0o755}),
                    )

    def test_any_fixed_partial_state_is_rejected_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp) / "weather-private-runtime"
            parent.mkdir()
            os.chmod(parent, 0o755)
            runtime = parent / "runtime"
            cache = parent / "artifacts"
            partial = parent / f".{runtime.name}.{receipt().artifact_sha256}.partial"
            partial.mkdir()
            with (
                mock.patch.object(recovery, "RUNTIME_BASE", runtime),
                mock.patch.object(recovery, "ARTIFACT_CACHE_ROOT", cache),
                mock.patch.object(recovery, "ROOT_UID", os.getuid()),
                mock.patch.object(recovery, "ROOT_GID", os.getgid()),
            ):
                with self.assertRaisesRegex(
                    recovery.WeatherNextPrivateRuntimeModeRecoveryError,
                    "partial state",
                ):
                    recovery._require_parent_and_no_partials(receipt())

    def test_incident_plan_recovers_only_fixed_directories_and_preserves_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "runtime"
            nested = root / "site-packages" / "pkg"
            nested.mkdir(parents=True)
            sentinel = nested / "value.txt"
            sentinel.write_bytes(b"reviewed-bytes\n")
            os.chmod(sentinel, 0o644)
            for directory in (root, root / "site-packages", nested):
                os.chmod(directory, 0o700)

            manifest = recovery.ExpectedRuntimeManifest(
                directories=("pkg",),
                files=(
                    recovery.ExpectedRuntimeFile(
                        "pkg/value.txt",
                        len(b"reviewed-bytes\n"),
                        hashlib.sha256(b"reviewed-bytes\n").hexdigest(),
                    ),
                ),
            )
            incident = recovery.RuntimeModeRecoveryPlan(
                current_source_sha="4" * 40,
                receipt=receipt(),
                actions_evidence=actions(),
                manifest=manifest,
                prior_state="INCIDENT",
                directory_paths=(nested, root / "site-packages", root),
                mutation_categories=(recovery.MUTATION_BUDGET[0][0],),
            )
            exact = recovery.RuntimeModeRecoveryPlan(
                current_source_sha=incident.current_source_sha,
                receipt=incident.receipt,
                actions_evidence=incident.actions_evidence,
                manifest=manifest,
                prior_state="EXACT",
                directory_paths=incident.directory_paths,
                mutation_categories=(),
            )

            with (
                mock.patch.object(recovery, "ROOT_UID", os.getuid()),
                mock.patch.object(recovery, "ROOT_GID", os.getgid()),
                mock.patch.object(recovery.os, "geteuid", return_value=0),
                mock.patch.object(
                    recovery,
                    "build_recovery_plan",
                    side_effect=(incident, exact),
                ),
            ):
                result = recovery.apply_recovery_plan(
                    incident,
                    recovery.FixedPublicGitHubReadClient(sender=object()),
                )

            self.assertEqual(result["status"], "RUNTIME_MODES_EXACT")
            for directory in incident.directory_paths:
                self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o755)
            self.assertEqual(sentinel.read_bytes(), b"reviewed-bytes\n")
            self.assertEqual(stat.S_IMODE(sentinel.stat().st_mode), 0o644)


if __name__ == "__main__":
    unittest.main()
