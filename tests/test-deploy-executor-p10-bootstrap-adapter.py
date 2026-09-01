#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.adapters import AdapterError, PreparedOperation
from deploy_executor import dashboard_bootstrap as bootstrap
from deploy_executor import dashboard_bootstrap_contract as contract
from deploy_executor import dashboard_bootstrap_fs as fs

SOURCE_SHA = "5f7739348f56398d0ba301c9320e1de0062838fc"
HISTORICAL_SHA = "400296591ec14c062e4c3c9fdbc95c38109ba0fd"


def git_blob(data: bytes) -> str:
    digest = hashlib.sha1()
    digest.update(f"blob {len(data)}\0".encode("ascii"))
    digest.update(data)
    return digest.hexdigest()


def make_manifest(source_sha: str, files: dict[str, bytes]) -> dict:
    entries = [
        {"path": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for path, data in sorted(files.items())
    ]
    core = {
        "schema": contract.MANIFEST_SCHEMA,
        "sourceSha": source_sha,
        "releasePath": f"/opt/dashboard_RPi5/releases/{source_sha}",
        "nodeMajor": 24,
        "hashAlgorithm": "sha256",
        "fileCount": len(entries),
        "totalBytes": sum(entry["bytes"] for entry in entries),
        "files": entries,
    }
    return {
        **core,
        "candidateSha256": hashlib.sha256(
            json.dumps(core, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def write_release(root: Path, source_sha: str, files: dict[str, bytes]) -> dict:
    release = root / "releases" / source_sha
    release.mkdir(parents=True, mode=0o755)
    for directory in (root, root / "releases", release):
        os.chmod(directory, 0o755)
    for relative, data in files.items():
        path = release / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        current = path.parent
        while current != release.parent:
            os.chmod(current, 0o755)
            if current == release:
                break
            current = current.parent
        path.write_bytes(data)
        os.chmod(path, 0o644)
    manifest = make_manifest(source_sha, files)
    marker = release / contract.MANIFEST_MARKER
    marker.write_text(json.dumps(manifest, separators=(",", ":")) + "\n", encoding="utf-8")
    os.chmod(marker, 0o600)
    return manifest


class SourceContractTests(unittest.TestCase):
    def test_exact_identities_and_dormant_adapter(self):
        self.assertEqual(contract.SOURCE_SHA, SOURCE_SHA)
        self.assertEqual(contract.HISTORICAL_CONTROLLER_BLOB, "c501bea57c0d5c35e7961ae1f1e5593a02268661")
        self.assertEqual(contract.HARDENED_CONTROLLER_BLOB, "c0566adb76e044632a4556dbefeb0f46839b4996")
        prepared = PreparedOperation(
            operation_id=contract.OPERATION_ID,
            adapter_id=contract.ADAPTER_ID,
            execution_enabled=False,
            source_repository=contract.SOURCE_REPOSITORY,
            source_sha=contract.SOURCE_SHA,
            target_alias=contract.TARGET_ALIAS,
            rollback_policy=contract.ROLLBACK_POLICY,
            mutation_budget=contract.MUTATION_BUDGET,
            exclusions=tuple(sorted(contract.REQUIRED_EXCLUSIONS)),
            dependencies=tuple(sorted(contract.REQUIRED_DEPENDENCIES)),
            normalized_queue_json="{}",
            preflight_checks=(),
            postcondition_checks=(),
            required_github_evidence=(),
        )
        adapter = contract.DashboardHardenedControllerBootstrapAdapter()
        result = adapter.preflight(prepared)
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["privileged_dispatch_ready"])
        with self.assertRaisesRegex(AdapterError, "separate LIVE/root gate"):
            adapter.apply(prepared)

    def test_no_generic_execution_or_path_authority(self):
        for relative in (
            "ops/lib/deploy_executor/dashboard_bootstrap_contract.py",
            "ops/lib/deploy_executor/dashboard_bootstrap_fs.py",
            "ops/lib/deploy_executor/dashboard_bootstrap.py",
            "ops/bin/rozkalns-dashboard-controller-bootstrap",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            for forbidden in ("subprocess", "os.system", "shell=True", "bash -c", "sh -c", "eval(", "socket.", "requests", "urllib"):
                self.assertNotIn(forbidden, text, relative)
        wrapper = (ROOT / "ops/bin/rozkalns-dashboard-controller-bootstrap").read_text(encoding="utf-8")
        for required in ("--expected-current", "--expected-candidate", "--apply", "--ack"):
            self.assertIn(required, wrapper)
        for forbidden in ("--candidate-root", "--manifest", "--root", "--command", "--argv"):
            self.assertNotIn(forbidden, wrapper)

    def test_strict_manifest_handles_historical_sha_and_duplicate_keys(self):
        manifest = make_manifest(HISTORICAL_SHA, {contract.CONTROLLER_RELATIVE_PATH: b"historical"})
        parsed = fs.parse_manifest(manifest, source_sha=HISTORICAL_SHA, expected_digest=None)
        self.assertEqual(parsed.source_sha, HISTORICAL_SHA)
        with self.assertRaisesRegex(contract.DashboardBootstrapError, "duplicate JSON key"):
            fs.strict_json(b'{"a":1,"a":2}')


@unittest.skipUnless(os.name == "posix" and Path("/proc/self/fd").exists(), "requires Linux descriptors")
class FilesystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        production = base / "production"
        staging = base / "staging"
        candidate = staging / "source"
        production.mkdir(mode=0o755)
        (production / "releases").mkdir(mode=0o755)
        candidate.mkdir(parents=True, mode=0o755)
        self.paths = contract.BootstrapPaths(production, staging, candidate, staging / "candidate-manifest.json")
        self.historical = b"historical-controller-v1\n"
        self.hardened = b"hardened-controller-v1\n"
        self.historical_blob = git_blob(self.historical)
        self.hardened_blob = git_blob(self.hardened)
        write_release(production, HISTORICAL_SHA, {contract.CONTROLLER_RELATIVE_PATH: self.historical})
        os.symlink(f"releases/{HISTORICAL_SHA}", production / "current")
        controller = candidate / contract.CONTROLLER_RELATIVE_PATH
        controller.parent.mkdir(parents=True, mode=0o755)
        controller.write_bytes(self.hardened)
        os.chmod(controller, 0o644)
        self.manifest = make_manifest(SOURCE_SHA, {contract.CONTROLLER_RELATIVE_PATH: self.hardened})
        self.paths.manifest_path.write_text(json.dumps(self.manifest, separators=(",", ":")) + "\n", encoding="utf-8")
        self.patch = mock.patch.multiple(
            contract,
            ROOT_UID=os.geteuid(),
            ROOT_GID=os.getegid(),
            HISTORICAL_CONTROLLER_BLOB=self.historical_blob,
            HARDENED_CONTROLLER_BLOB=self.hardened_blob,
        )
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def apply(self):
        return bootstrap.apply_bootstrap(
            expected_current=HISTORICAL_SHA,
            expected_candidate_sha256=self.manifest["candidateSha256"],
            acknowledgement=contract.BOOTSTRAP_ACK,
            paths=self.paths,
        )

    def test_success_retains_previous_release_and_does_not_apply_p10(self):
        receipt = self.apply()
        self.assertEqual(receipt.status, "BOOTSTRAP_APPLIED")
        self.assertFalse(receipt.p10_apply_executed)
        self.assertEqual(os.readlink(self.paths.production_root / "current"), f"releases/{SOURCE_SHA}")
        self.assertTrue((self.paths.production_root / "releases" / HISTORICAL_SHA).is_dir())
        self.assertFalse((self.paths.production_root / contract.APPLY_LOCK_NAME).exists())
        target = self.paths.production_root / "releases" / SOURCE_SHA / contract.CONTROLLER_RELATIVE_PATH
        self.assertEqual(git_blob(target.read_bytes()), self.hardened_blob)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o644)

    def test_candidate_symlink_fails_before_lock(self):
        controller = self.paths.candidate_root / contract.CONTROLLER_RELATIVE_PATH
        data = controller.read_bytes()
        controller.unlink()
        alternate = self.paths.staging_root / "alternate"
        alternate.write_bytes(data)
        controller.symlink_to(alternate)
        with self.assertRaises(Exception):
            self.apply()
        self.assertFalse((self.paths.production_root / contract.APPLY_LOCK_NAME).exists())
        self.assertFalse((self.paths.production_root / "releases" / SOURCE_SHA).exists())

    def test_pre_mutation_failure_removes_lock(self):
        with mock.patch.object(fs, "materialize", side_effect=contract.DashboardBootstrapError("pre-mutation")):
            with self.assertRaisesRegex(contract.DashboardBootstrapError, "pre-mutation"):
                self.apply()
        self.assertFalse((self.paths.production_root / contract.APPLY_LOCK_NAME).exists())

    def test_post_mutation_failure_preserves_lock_and_release(self):
        with mock.patch.object(fs, "swap_current", side_effect=contract.DashboardBootstrapError("pointer")):
            with self.assertRaisesRegex(contract.DashboardBootstrapError, "failed after release mutation started"):
                self.apply()
        self.assertTrue((self.paths.production_root / contract.APPLY_LOCK_NAME).exists())
        self.assertTrue((self.paths.production_root / "releases" / SOURCE_SHA).exists())
        self.assertEqual(os.readlink(self.paths.production_root / "current"), f"releases/{HISTORICAL_SHA}")

    def test_success_closes_bootstrap_channel(self):
        self.apply()
        with self.assertRaisesRegex(contract.DashboardBootstrapError, "already satisfied"):
            bootstrap.apply_bootstrap(
                expected_current=SOURCE_SHA,
                expected_candidate_sha256=self.manifest["candidateSha256"],
                acknowledgement=contract.BOOTSTRAP_ACK,
                paths=self.paths,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
