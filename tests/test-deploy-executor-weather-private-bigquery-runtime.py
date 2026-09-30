#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import stat
import sys
import tarfile
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops/lib/deploy_executor/weather_private_bigquery_runtime_materialization.py"
LOCK_PATH = ROOT / "ops/lib/deploy_executor/weather_private_bigquery_runtime_lock.json"

spec = importlib.util.spec_from_file_location("weather_private_bigquery_runtime_materialization", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("unable to load WeatherNext private runtime module")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def wheel_bytes(filename: str = "google/cloud/bigquery/__init__.py", payload: bytes = b"VALUE = 1\n") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(filename, payload)
    return buffer.getvalue()


def mini_lock(wheel: bytes) -> dict:
    packages = [{"name":"google-cloud-bigquery","version":"3.42.1","filename":"google_cloud_bigquery-3.42.1-py3-none-any.whl","sha256":sha256_bytes(wheel)}]
    return {
        "schema":"rozkalns-weather.weathernext-private-runtime-lock.v1",
        "operation_id":module.OPERATION_ID,
        "upstream_requirement":"google-cloud-bigquery>=3.36,<4",
        "resolved_root":"google-cloud-bigquery==3.42.1",
        "target":{"os":module.TARGET_OS,"architecture":module.TARGET_ARCH,"python_version":module.TARGET_PYTHON_VERSION,"python_abi":module.TARGET_PYTHON_ABI,"pip_platform":module.TARGET_PIP_PLATFORM,"accepted_abi":["cp313","abi3","none"]},
        "package_count":1,
        "closure_sha256":module.closure_digest(packages),
        "packages":packages,
        "provenance":{"registry":"fixture"},
        "live_network_install_allowed":False,
        "live_package_manager_install_allowed":False,
        "credential_material_in_lock":False,
        "private_google_identity_in_lock":False,
    }


def make_artifact(path: Path, lock: dict, source_sha: str, wheel: bytes) -> tuple[bytes, module.RuntimeArtifactReceipt]:
    metadata = {
        "schema":"rozkalns-weather.weathernext-private-runtime-artifact.v1",
        "source_sha":source_sha,
        "closure_sha256":lock["closure_sha256"],
        "target_os":module.TARGET_OS,
        "target_architecture":module.TARGET_ARCH,
        "target_python_version":module.TARGET_PYTHON_VERSION,
        "target_python_abi":module.TARGET_PYTHON_ABI,
        "target_platform":module.TARGET_PIP_PLATFORM,
        "package_count":lock["package_count"],
    }
    with tarfile.open(path, "w") as archive:
        for name, data in ((module.ARCHIVE_METADATA_NAME, json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()), (f"wheelhouse/{lock['packages'][0]['filename']}", wheel)):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            info.mtime = 0
            info.uid = info.gid = 0
            archive.addfile(info, io.BytesIO(data))
    blob = path.read_bytes()
    receipt = module.RuntimeArtifactReceipt(
        source_sha=source_sha,
        closure_sha256=lock["closure_sha256"],
        artifact_sha256=sha256_bytes(blob),
        artifact_size_bytes=len(blob),
        artifact_format=module.ARTIFACT_FORMAT,
        target_os=module.TARGET_OS,
        target_architecture=module.TARGET_ARCH,
        target_python_version=module.TARGET_PYTHON_VERSION,
        target_python_abi=module.TARGET_PYTHON_ABI,
        target_platform=module.TARGET_PIP_PLATFORM,
    )
    return blob, receipt


class WeatherNextPrivateRuntimeTests(unittest.TestCase):
    def test_real_lock_is_complete_exact_and_hashed(self) -> None:
        lock = module.load_runtime_lock(LOCK_PATH)
        self.assertEqual(lock["package_count"], 26)
        self.assertEqual(lock["closure_sha256"], "379b3964f9f424ed35ddbb8bdd6e8f1ebb9e85863132bbe5f8a0444c88c8ea38")
        self.assertEqual(lock["resolved_root"], "google-cloud-bigquery==3.42.1")
        self.assertEqual(lock["upstream_requirement"], "google-cloud-bigquery>=3.36,<4")
        for package in lock["packages"]:
            self.assertRegex(package["version"], r"^[0-9][0-9A-Za-z.+-]*$")
            self.assertRegex(package["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(package["filename"].endswith(".whl"))
        self.assertFalse(lock["live_network_install_allowed"])
        self.assertFalse(lock["live_package_manager_install_allowed"])

    def test_public_authority_cannot_dispatch_private_materialization(self) -> None:
        receipt = module.RuntimeArtifactReceipt(source_sha="1"*40,closure_sha256=module.load_runtime_lock(LOCK_PATH)["closure_sha256"],artifact_sha256="2"*64,artifact_size_bytes=1024,artifact_format=module.ARTIFACT_FORMAT,target_os=module.TARGET_OS,target_architecture=module.TARGET_ARCH,target_python_version=module.TARGET_PYTHON_VERSION,target_python_abi=module.TARGET_PYTHON_ABI,target_platform=module.TARGET_PIP_PLATFORM)
        with self.assertRaisesRegex(module.WeatherNextRuntimeMaterializationError, "public Weather authority"):
            module.build_materialization_plan(module.PUBLIC_RUNTIME_OPERATION_ID, receipt, expected_source_sha=receipt.source_sha)

    def test_receipt_rejects_digest_platform_python_and_source_mismatch(self) -> None:
        lock = module.load_runtime_lock(LOCK_PATH)
        base = module.RuntimeArtifactReceipt(source_sha="1"*40,closure_sha256=lock["closure_sha256"],artifact_sha256="2"*64,artifact_size_bytes=1024,artifact_format=module.ARTIFACT_FORMAT,target_os=module.TARGET_OS,target_architecture=module.TARGET_ARCH,target_python_version=module.TARGET_PYTHON_VERSION,target_python_abi=module.TARGET_PYTHON_ABI,target_platform=module.TARGET_PIP_PLATFORM)
        module.validate_artifact_receipt(base, expected_source_sha=base.source_sha, lock=lock)
        bad_values = (replace(base,source_sha="3"*40),replace(base,closure_sha256="3"*64),replace(base,artifact_sha256="not-a-digest"),replace(base,target_architecture="x86_64"),replace(base,target_python_version="3.12"),replace(base,target_python_abi="cp312"),replace(base,target_platform="manylinux2014_x86_64"))
        for receipt in bad_values:
            with self.subTest(receipt=receipt):
                with self.assertRaises(module.WeatherNextRuntimeMaterializationError):
                    module.validate_artifact_receipt(receipt, expected_source_sha=base.source_sha, lock=lock)

    def test_runtime_state_is_presence_and_identity_only(self) -> None:
        lock = module.load_runtime_lock(LOCK_PATH)
        receipt = module.RuntimeArtifactReceipt(source_sha="1"*40,closure_sha256=lock["closure_sha256"],artifact_sha256="2"*64,artifact_size_bytes=1024,artifact_format=module.ARTIFACT_FORMAT,target_os=module.TARGET_OS,target_architecture=module.TARGET_ARCH,target_python_version=module.TARGET_PYTHON_VERSION,target_python_abi=module.TARGET_PYTHON_ABI,target_platform=module.TARGET_PIP_PLATFORM)
        self.assertEqual(module.classify_runtime_identity(module.ObservedRuntimeIdentity(present=False), receipt=receipt), "runtime_materialization_required")
        self.assertEqual(module.classify_runtime_identity(module.ObservedRuntimeIdentity(present=True,source_sha=receipt.source_sha,closure_sha256=receipt.closure_sha256,artifact_sha256="3"*64,target_python_abi=receipt.target_python_abi,target_platform=receipt.target_platform), receipt=receipt), "runtime_identity_mismatch")
        self.assertEqual(module.classify_runtime_identity(module.ObservedRuntimeIdentity(present=True,source_sha=receipt.source_sha,closure_sha256=receipt.closure_sha256,artifact_sha256=receipt.artifact_sha256,target_python_abi=receipt.target_python_abi,target_platform=receipt.target_platform), receipt=receipt), "runtime_materialization_source_ready")

    def test_capability_grants_no_downstream_google_or_sqlite_authority(self) -> None:
        summary = module.source_capability_summary()
        self.assertEqual(summary["mutation_class"], "weathernext_private_runtime_materialization")
        self.assertTrue(summary["offline_artifact_required"])
        for key in ("network_install_authority","package_manager_authority","public_runtime_authority_reusable","credential_binding_authorized","project_binding_authorized","analytics_hub_link_authorized","read_only_bigquery_authorized","sqlite_write_authorized","host_wiring_enabled"):
            self.assertFalse(summary[key], key)

    def test_runtime_source_has_no_generic_execution_or_secret_surface(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        for token in ("subprocess","os.environ","Popen(","shell=True","pip install","apt ","GOOGLE_CLOUD_PROJECT","HOME_LAT","HOME_LON",".env"):
            self.assertNotIn(token, source)
        self.assertNotIn("credential_path", source)
        self.assertNotIn("dataset_id", source)
        self.assertNotIn("project_id", source)

    def test_materializer_unpacks_only_reviewed_offline_wheelhouse(self) -> None:
        source_sha = "1"*40
        wheel = wheel_bytes()
        lock = mini_lock(wheel)
        module.validate_runtime_lock(lock)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lock_path = root/"lock.json"
            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            cache = root/"artifacts"
            cache.mkdir()
            runtime = root/"runtime"/"current"
            provisional = cache/"provisional.tar"
            blob, receipt = make_artifact(provisional, lock, source_sha, wheel)
            artifact = cache/f"{receipt.artifact_sha256}.tar"
            artifact.write_bytes(blob)
            provisional.unlink()
            previous_umask = os.umask(0o077)
            try:
                with (mock.patch.object(module,"LOCK_PATH",lock_path),mock.patch.object(module,"ARTIFACT_CACHE_ROOT",cache),mock.patch.object(module,"RUNTIME_BASE",runtime)):
                    result = module.materialize_reviewed_runtime(module.PRIVATE_CONTRACT_ID, receipt, expected_source_sha=source_sha)
            finally:
                os.umask(previous_umask)
            self.assertEqual(result["status"], "runtime_materialized")
            self.assertFalse(result["network_access_performed"])
            self.assertFalse(result["package_manager_performed"])
            self.assertTrue((runtime/"site-packages/google/cloud/bigquery/__init__.py").is_file())
            for directory in (
                runtime,
                runtime/"site-packages",
                runtime/"site-packages/google",
                runtime/"site-packages/google/cloud",
                runtime/"site-packages/google/cloud/bigquery",
            ):
                self.assertEqual(
                    stat.S_IMODE(directory.stat().st_mode),
                    module.FIXED_DIRECTORY_MODE,
                    str(directory),
                )
            marker = json.loads((runtime/module.RUNTIME_MARKER_NAME).read_text())
            self.assertFalse(marker["credential_binding"])
            self.assertFalse(marker["bigquery_access"])
            self.assertFalse(marker["sqlite_write"])

    def test_materializer_fails_closed_on_prior_partial_without_cleanup(self) -> None:
        source_sha = "1"*40
        wheel = wheel_bytes()
        lock = mini_lock(wheel)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lock_path = root/"lock.json"
            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            cache = root/"artifacts"
            cache.mkdir()
            runtime = root/"runtime"/"current"
            provisional = cache/"provisional.tar"
            blob, receipt = make_artifact(provisional, lock, source_sha, wheel)
            artifact = cache/f"{receipt.artifact_sha256}.tar"
            artifact.write_bytes(blob)
            provisional.unlink()
            staging = runtime.parent/f".{runtime.name}.{receipt.artifact_sha256}.partial"
            staging.mkdir(parents=True)
            with (mock.patch.object(module,"LOCK_PATH",lock_path),mock.patch.object(module,"ARTIFACT_CACHE_ROOT",cache),mock.patch.object(module,"RUNTIME_BASE",runtime)):
                with self.assertRaisesRegex(module.WeatherNextRuntimeMaterializationError, "prior partial"):
                    module.materialize_reviewed_runtime(module.PRIVATE_CONTRACT_ID, receipt, expected_source_sha=source_sha)
            self.assertTrue(staging.exists(), "fail-closed source must not auto-clean prior partial state")


if __name__ == "__main__":
    unittest.main()
