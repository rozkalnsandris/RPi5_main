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
MODULE_PATH = ROOT / "ops/lib/deploy_executor/weather_private_gcs_runtime_materialization.py"
LOCK_PATH = ROOT / "ops/lib/deploy_executor/weather_private_gcs_runtime_lock.json"

spec = importlib.util.spec_from_file_location(
    "weather_private_gcs_runtime_materialization",
    MODULE_PATH,
)
if spec is None or spec.loader is None:
    raise RuntimeError("unable to load WeatherNext private GCS runtime module")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def wheel_bytes(path: str, payload: bytes = b"VALUE = 1\n") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(path, payload)
    return buffer.getvalue()


def mini_lock(wheels: dict[str, bytes]) -> dict:
    package_specs = [
        ("google-auth", "2.59.1", "google_auth-2.59.1-py3-none-any.whl"),
        ("obstore", "0.11.1", "obstore-0.11.1-py3-none-any.whl"),
        ("requests", "2.34.2", "requests-2.34.2-py3-none-any.whl"),
        ("xarray", "2026.9.0", "xarray-2026.9.0-py3-none-any.whl"),
        ("zarr", "3.4.0", "zarr-3.4.0-py3-none-any.whl"),
    ]
    packages = [
        {
            "name": name,
            "version": version,
            "filename": filename,
            "sha256": sha256_bytes(wheels[filename]),
        }
        for name, version, filename in package_specs
    ]
    packages.sort(key=lambda item: item["name"])
    return {
        "schema": "rozkalns-weather.weathernext-private-gcs-runtime-lock.v1",
        "operation_id": module.OPERATION_ID,
        "weather_source_sha": module.WEATHER_SOURCE_SHA,
        "weather_extra": module.WEATHER_EXTRA,
        "upstream_requirements": list(module.UPSTREAM_REQUIREMENTS),
        "resolved_roots": {
            "google-auth": "2.59.1",
            "obstore": "0.11.1",
            "requests": "2.34.2",
            "xarray": "2026.9.0",
            "zarr": "3.4.0",
        },
        "target": {
            "os": module.TARGET_OS,
            "architecture": module.TARGET_ARCH,
            "python_version": module.TARGET_PYTHON_VERSION,
            "python_abi": module.TARGET_PYTHON_ABI,
            "pip_platform": module.TARGET_PIP_PLATFORM,
            "accepted_abi": list(module.ACCEPTED_ABI),
            "accepted_wheel_platforms": list(module.ACCEPTED_WHEEL_PLATFORMS),
        },
        "package_count": len(packages),
        "closure_sha256": module.closure_digest(packages),
        "packages": packages,
        "provenance": {"registry": "fixture"},
        "live_network_install_allowed": False,
        "live_package_manager_install_allowed": False,
        "credential_material_in_lock": False,
        "private_google_identity_in_lock": False,
    }


def make_artifact(
    path: Path,
    lock: dict,
    source_sha: str,
    wheels: dict[str, bytes],
) -> tuple[bytes, module.RuntimeArtifactReceipt]:
    metadata = {
        "schema": "rozkalns-weather.weathernext-private-gcs-runtime-artifact.v1",
        "source_sha": source_sha,
        "closure_sha256": lock["closure_sha256"],
        "target_os": module.TARGET_OS,
        "target_architecture": module.TARGET_ARCH,
        "target_python_version": module.TARGET_PYTHON_VERSION,
        "target_python_abi": module.TARGET_PYTHON_ABI,
        "target_platform": module.TARGET_PIP_PLATFORM,
        "package_count": lock["package_count"],
    }
    with tarfile.open(path, "w") as archive:
        entries = [
            (
                module.ARCHIVE_METADATA_NAME,
                json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode(),
            )
        ]
        entries.extend(
            (f"wheelhouse/{package['filename']}", wheels[package["filename"]])
            for package in lock["packages"]
        )
        for name, data in entries:
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


class WeatherNextPrivateGCSRuntimeTests(unittest.TestCase):
    def test_real_lock_is_exact_hashed_and_has_no_bigquery(self):
        lock = module.load_runtime_lock(LOCK_PATH)
        self.assertEqual(lock["package_count"], 25)
        self.assertEqual(
            lock["closure_sha256"],
            "4ef3d22c8ebc76901c3840d0304124ab390afaf3978883a4ad377a6da4991148",
        )
        self.assertEqual(
            lock["resolved_roots"],
            {
                "google-auth": "2.59.1",
                "obstore": "0.11.1",
                "requests": "2.34.2",
                "xarray": "2026.9.0",
                "zarr": "3.4.0",
            },
        )
        self.assertEqual(lock["target"]["pip_platform"], "manylinux_2_28_aarch64")
        names = {item["name"] for item in lock["packages"]}
        self.assertNotIn("google-cloud-bigquery", names)
        self.assertTrue(
            {"google-auth", "obstore", "requests", "xarray", "zarr"}.issubset(names)
        )
        for package in lock["packages"]:
            self.assertRegex(package["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(package["filename"].endswith(".whl"))
        self.assertFalse(lock["live_network_install_allowed"])
        self.assertFalse(lock["live_package_manager_install_allowed"])

    def test_authority_separation_is_fail_closed(self):
        lock = module.load_runtime_lock(LOCK_PATH)
        receipt = module.RuntimeArtifactReceipt(
            source_sha="1" * 40,
            closure_sha256=lock["closure_sha256"],
            artifact_sha256="2" * 64,
            artifact_size_bytes=1024,
            artifact_format=module.ARTIFACT_FORMAT,
            target_os=module.TARGET_OS,
            target_architecture=module.TARGET_ARCH,
            target_python_version=module.TARGET_PYTHON_VERSION,
            target_python_abi=module.TARGET_PYTHON_ABI,
            target_platform=module.TARGET_PIP_PLATFORM,
        )
        with self.assertRaisesRegex(
            module.WeatherNextGCSRuntimeMaterializationError,
            "public Weather authority",
        ):
            module.build_materialization_plan(
                module.PUBLIC_RUNTIME_OPERATION_ID,
                receipt,
                expected_source_sha=receipt.source_sha,
            )
        with self.assertRaisesRegex(
            module.WeatherNextGCSRuntimeMaterializationError,
            "BigQuery authority",
        ):
            module.build_materialization_plan(
                module.BIGQUERY_CONTRACT_ID,
                receipt,
                expected_source_sha=receipt.source_sha,
            )
        plan = module.build_materialization_plan(
            module.PRIVATE_CONTRACT_ID,
            receipt,
            expected_source_sha=receipt.source_sha,
        )
        self.assertFalse(plan["network_access"])
        self.assertFalse(plan["package_manager"])
        self.assertFalse(plan["credential_binding"])
        self.assertFalse(plan["google_gcs_access"])
        self.assertFalse(plan["bigquery_access"])
        self.assertFalse(plan["sqlite_write"])

    def test_receipt_rejects_digest_platform_and_source_drift(self):
        lock = module.load_runtime_lock(LOCK_PATH)
        base = module.RuntimeArtifactReceipt(
            source_sha="1" * 40,
            closure_sha256=lock["closure_sha256"],
            artifact_sha256="2" * 64,
            artifact_size_bytes=1024,
            artifact_format=module.ARTIFACT_FORMAT,
            target_os=module.TARGET_OS,
            target_architecture=module.TARGET_ARCH,
            target_python_version=module.TARGET_PYTHON_VERSION,
            target_python_abi=module.TARGET_PYTHON_ABI,
            target_platform=module.TARGET_PIP_PLATFORM,
        )
        module.validate_artifact_receipt(
            base,
            expected_source_sha=base.source_sha,
            lock=lock,
        )
        bad = (
            replace(base, source_sha="3" * 40),
            replace(base, closure_sha256="3" * 64),
            replace(base, artifact_sha256="bad"),
            replace(base, target_architecture="x86_64"),
            replace(base, target_python_version="3.12"),
            replace(base, target_python_abi="cp312"),
            replace(base, target_platform="manylinux2014_x86_64"),
        )
        for receipt in bad:
            with self.subTest(receipt=receipt):
                with self.assertRaises(module.WeatherNextGCSRuntimeMaterializationError):
                    module.validate_artifact_receipt(
                        receipt,
                        expected_source_sha=base.source_sha,
                        lock=lock,
                    )

    def test_source_has_no_generic_execution_secret_or_google_request_surface(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        for token in (
            "subprocess",
            "os.environ",
            "Popen(",
            "shell=True",
            "pip install",
            "apt ",
            "GOOGLE_CLOUD_PROJECT",
            "HOME_LAT",
            "HOME_LON",
            ".env",
            "storage.googleapis.com",
        ):
            self.assertNotIn(token, source)

    def test_materializer_unpacks_only_reviewed_offline_gcs_wheelhouse(self):
        source_sha = "1" * 40
        wheels = {
            "google_auth-2.59.1-py3-none-any.whl": wheel_bytes("google/auth/__init__.py"),
            "obstore-0.11.1-py3-none-any.whl": wheel_bytes("obstore/__init__.py"),
            "requests-2.34.2-py3-none-any.whl": wheel_bytes("requests/__init__.py"),
            "xarray-2026.9.0-py3-none-any.whl": wheel_bytes("xarray/__init__.py"),
            "zarr-3.4.0-py3-none-any.whl": wheel_bytes("zarr/__init__.py"),
        }
        lock = mini_lock(wheels)
        module.validate_runtime_lock(lock)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lock_path = root / "lock.json"
            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            cache = root / "artifacts"
            cache.mkdir()
            runtime = root / "runtime" / "current"
            provisional = cache / "provisional.tar"
            blob, receipt = make_artifact(provisional, lock, source_sha, wheels)
            artifact = cache / f"{receipt.artifact_sha256}.tar"
            artifact.write_bytes(blob)
            provisional.unlink()
            previous_umask = os.umask(0o077)
            try:
                with (
                    mock.patch.object(module, "LOCK_PATH", lock_path),
                    mock.patch.object(module, "ARTIFACT_CACHE_ROOT", cache),
                    mock.patch.object(module, "RUNTIME_BASE", runtime),
                ):
                    result = module.materialize_reviewed_runtime(
                        module.PRIVATE_CONTRACT_ID,
                        receipt,
                        expected_source_sha=source_sha,
                    )
            finally:
                os.umask(previous_umask)
            self.assertEqual(result["status"], "gcs_runtime_materialized")
            self.assertFalse(result["network_access_performed"])
            self.assertFalse(result["google_gcs_access_performed"])
            self.assertFalse(result["bigquery_access_performed"])
            self.assertTrue((runtime / "site-packages/obstore/__init__.py").is_file())
            self.assertTrue((runtime / "site-packages/xarray/__init__.py").is_file())
            self.assertTrue((runtime / "site-packages/zarr/__init__.py").is_file())
            for directory in (runtime, runtime / "site-packages"):
                self.assertEqual(
                    stat.S_IMODE(directory.stat().st_mode),
                    module.FIXED_DIRECTORY_MODE,
                )
            marker = json.loads((runtime / module.RUNTIME_MARKER_NAME).read_text())
            self.assertFalse(marker["credential_binding"])
            self.assertFalse(marker["google_gcs_access"])
            self.assertFalse(marker["bigquery_access"])
            self.assertFalse(marker["sqlite_write"])

    def test_materializer_fails_closed_on_prior_partial_without_cleanup(self):
        source_sha = "1" * 40
        wheels = {
            "google_auth-2.59.1-py3-none-any.whl": wheel_bytes("google/auth/__init__.py"),
            "obstore-0.11.1-py3-none-any.whl": wheel_bytes("obstore/__init__.py"),
            "requests-2.34.2-py3-none-any.whl": wheel_bytes("requests/__init__.py"),
            "xarray-2026.9.0-py3-none-any.whl": wheel_bytes("xarray/__init__.py"),
            "zarr-3.4.0-py3-none-any.whl": wheel_bytes("zarr/__init__.py"),
        }
        lock = mini_lock(wheels)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lock_path = root / "lock.json"
            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            cache = root / "artifacts"
            cache.mkdir()
            runtime = root / "runtime" / "current"
            provisional = cache / "provisional.tar"
            blob, receipt = make_artifact(provisional, lock, source_sha, wheels)
            artifact = cache / f"{receipt.artifact_sha256}.tar"
            artifact.write_bytes(blob)
            provisional.unlink()
            staging = runtime.parent / f".{runtime.name}.{receipt.artifact_sha256}.partial"
            staging.mkdir(parents=True)
            with (
                mock.patch.object(module, "LOCK_PATH", lock_path),
                mock.patch.object(module, "ARTIFACT_CACHE_ROOT", cache),
                mock.patch.object(module, "RUNTIME_BASE", runtime),
            ):
                with self.assertRaisesRegex(
                    module.WeatherNextGCSRuntimeMaterializationError,
                    "prior partial",
                ):
                    module.materialize_reviewed_runtime(
                        module.PRIVATE_CONTRACT_ID,
                        receipt,
                        expected_source_sha=source_sha,
                    )
            self.assertTrue(staging.exists())


if __name__ == "__main__":
    unittest.main()
