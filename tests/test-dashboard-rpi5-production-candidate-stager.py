from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dashboard-rpi5-production-candidate-stager.py"
CONTRACT = ROOT / "ops" / "deploy" / "dashboard-candidate-stager-v1.json"
loader = importlib.machinery.SourceFileLoader("dashboard_candidate_stager_tested", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
module = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = module
loader.exec_module(module)

EXPECTED_PROVENANCE = {
    "verification_phase": "unprivileged-preverification-before-LIVE",
    "repository": "rozkalnsandris/dashboard_RPi5",
    "source_sha": "066b9a24008dd57439f9e66eae198416c4dfc590",
    "source_tree_sha": "62756ba22fc8d47e44988c086c08dcf37779cfb3",
    "parent_sha": "5f7739348f56398d0ba301c9320e1de0062838fc",
    "producer_path": "tools/production-candidate-manifest.mjs",
    "producer_blob_sha": "bea0f30602d119ae53b81e70ce2d4c283d369ce8",
    "handoff_owner": "rozkalns-deploy-executor",
    "candidate_javascript_runs_as_root": False,
    "root_stager_consumes_git_repository": False,
}


def assert_reviewed_provenance(value: object) -> None:
    if type(value) is not dict or value != EXPECTED_PROVENANCE:
        raise AssertionError("reviewed Dashboard provenance drift")



def manifest_for(files: list[tuple[str, bytes]], *, source_sha: str | None = None) -> tuple[bytes, str]:
    source = source_sha or module.REVIEWED_SOURCE_SHA
    entries = [
        {"path": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for path, data in sorted(files)
    ]
    core = {
        "schema": module.MANIFEST_SCHEMA,
        "sourceSha": source,
        "releasePath": f"/opt/dashboard_RPi5/releases/{source}",
        "nodeMajor": 24,
        "hashAlgorithm": "sha256",
        "fileCount": len(entries),
        "totalBytes": sum(entry["bytes"] for entry in entries),
        "files": entries,
    }
    digest = hashlib.sha256(json.dumps(core, separators=(",", ":")).encode()).hexdigest()
    raw = json.dumps({**core, "candidateSha256": digest}, separators=(",", ":")).encode()
    return raw, digest


def write_input_tree(root: Path, files: list[tuple[str, bytes]]) -> None:
    root.mkdir(mode=module.INPUT_DIRECTORY_MODE)
    os.chmod(root, module.INPUT_DIRECTORY_MODE)
    for rel, data in files:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        for parent in list(path.parents):
            if parent == root.parent:
                break
            if parent == root or root in parent.parents:
                os.chmod(parent, module.INPUT_DIRECTORY_MODE)
        path.write_bytes(data)
        os.chmod(path, module.INPUT_FILE_MODE)


class CandidateStagerContractTests(unittest.TestCase):
    def test_machine_contract_matches_source_and_stays_execution_disabled(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertFalse(contract["execution_enabled"])
        self.assertEqual(contract["operation_id"], module.OPERATION_ID)
        self.assertEqual(contract["reviewed_source_sha"], module.REVIEWED_SOURCE_SHA)
        self.assertEqual(contract["preverified_input"]["root"], str(module.INPUT_ROOT))
        self.assertEqual(contract["staging_output"]["root"], str(module.STAGING_ROOT))
        self.assertFalse(contract["source_state"]["registry_execution_enabled_must_remain"])
        self.assertFalse(contract["source_state"]["live_authority"])
        self.assertFalse(contract["source_state"]["merge_authorizes_staging"])


    def test_exact_reviewed_provenance_binding(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        assert_reviewed_provenance(contract["provenance"])
        self.assertEqual(contract["provenance"]["source_sha"], module.REVIEWED_SOURCE_SHA)
        self.assertFalse(contract["provenance"]["candidate_javascript_runs_as_root"])
        self.assertFalse(contract["provenance"]["root_stager_consumes_git_repository"])

    def test_provenance_drift_is_rejected(self) -> None:
        drifts = {
            "verification_phase": "root",
            "repository": "other/repository",
            "source_sha": "1" * 40,
            "source_tree_sha": "2" * 40,
            "parent_sha": "3" * 40,
            "producer_path": "tools/other.mjs",
            "producer_blob_sha": "4" * 40,
            "handoff_owner": "root",
            "candidate_javascript_runs_as_root": True,
            "root_stager_consumes_git_repository": True,
        }
        for field, drift_value in drifts.items():
            with self.subTest(field=field):
                drifted = dict(EXPECTED_PROVENANCE)
                drifted[field] = drift_value
                with self.assertRaisesRegex(AssertionError, "provenance drift"):
                    assert_reviewed_provenance(drifted)

    def test_fixed_identity_paths_and_budget(self) -> None:
        self.assertEqual(module.OPERATION_ID, "dashboard-rpi5.production-release.v1")
        self.assertEqual(module.REVIEWED_SOURCE_SHA, "066b9a24008dd57439f9e66eae198416c4dfc590")
        self.assertEqual(str(module.INPUT_ROOT), f"/var/lib/rozkalns-deploy-executor/dashboard-candidate-input/{module.REVIEWED_SOURCE_SHA}")
        self.assertEqual(str(module.STAGING_ROOT), f"/var/lib/rozkalns-dashboard-release-candidates/{module.REVIEWED_SOURCE_SHA}")
        self.assertEqual(str(module.STAGING_SOURCE), f"{module.STAGING_ROOT}/source")
        self.assertEqual(str(module.STAGING_MANIFEST), f"{module.STAGING_ROOT}/candidate-manifest.json")
        self.assertEqual(
            module.STAGING_MUTATION_BUDGET,
            (
                ("staging-namespace-root-create", 1),
                ("staging-candidate-partial-root-create", 1),
                ("staging-file-materialization", 512),
                ("staging-manifest-materialization", 1),
                ("staging-final-rename", 1),
            ),
        )

    def test_cli_has_no_path_source_command_or_environment_authority(self) -> None:
        args = module._parse_args(["--expected-candidate", "a" * 64, "--apply", "--ack", module.ACK])
        self.assertEqual(args.expected_candidate, "a" * 64)
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "--candidate-root", "--manifest", "--source", "--path", "--command", "--script", "--environment",
            "subprocess", "os.system(", "shell=True", "Popen(", "execv(", "spawn",
        ):
            self.assertNotIn(forbidden, source)

    def test_production_root_current_and_apply_lock_are_not_staging_targets(self) -> None:
        for path in (module.STAGING_BASE, module.STAGING_ROOT, module.STAGING_SOURCE, module.STAGING_MANIFEST):
            self.assertTrue(str(path).startswith("/var/lib/rozkalns-dashboard-release-candidates"))
            self.assertFalse(str(path).startswith("/opt/dashboard_RPi5"))
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("/opt/dashboard_RPi5/current", source)
        self.assertNotIn(".dashboard-release-controller.lock", source)
        self.assertIn('"production_release_materializations": 0', source)
        self.assertIn('"current_pointer_swaps": 0', source)
        self.assertIn('"apply_lock_mutations": 0', source)

    def test_candidate_javascript_is_never_executed(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("/usr/bin/node", source)
        self.assertNotIn("node ", source)
        self.assertNotIn("production-release-controller.mjs", source)
        self.assertIn('"candidate_javascript_executed_as_root": False', source)


class ManifestAdversarialTests(unittest.TestCase):
    def test_exact_source_and_digest_binding(self) -> None:
        raw, digest = manifest_for([("apps/web/dist/index.html", b"ok")])
        parsed = module._parse_manifest(raw, expected_digest=digest)
        self.assertEqual(parsed.source_sha, module.REVIEWED_SOURCE_SHA)
        self.assertEqual(parsed.candidate_sha256, digest)
        with self.assertRaisesRegex(module.CandidateStagerError, "LIVE binding"):
            module._parse_manifest(raw, expected_digest="0" * 64)

        drift_source = "1" * 40
        raw_drift, drift_digest = manifest_for([("apps/web/dist/index.html", b"ok")], source_sha=drift_source)
        with self.assertRaisesRegex(module.CandidateStagerError, "source/schema mismatch"):
            module._parse_manifest(raw_drift, expected_digest=drift_digest)

    def test_path_escape_and_metadata_drift_are_rejected(self) -> None:
        raw, digest = manifest_for([("../escape", b"x")])
        with self.assertRaisesRegex(module.CandidateStagerError, "escapes reviewed root"):
            module._parse_manifest(raw, expected_digest=digest)

        raw, digest = manifest_for([("apps/web/dist/index.html", b"ok")])
        value = json.loads(raw)
        value["files"][0]["bytes"] += 1
        core = {key: value[key] for key in (
            "schema", "sourceSha", "releasePath", "nodeMajor", "hashAlgorithm", "fileCount", "totalBytes", "files"
        )}
        value["candidateSha256"] = hashlib.sha256(json.dumps(core, separators=(",", ":")).encode()).hexdigest()
        with self.assertRaisesRegex(module.CandidateStagerError, "aggregate size mismatch"):
            module._parse_manifest(json.dumps(value, separators=(",", ":")).encode(), expected_digest=value["candidateSha256"])


class DescriptorSafetyTests(unittest.TestCase):
    def test_symlink_and_special_file_are_rejected(self) -> None:
        uid, gid = os.getuid(), os.getgid()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            root.mkdir()
            os.chmod(root, module.INPUT_DIRECTORY_MODE)
            (root / "ok").write_bytes(b"x")
            os.chmod(root / "ok", module.INPUT_FILE_MODE)
            os.symlink("ok", root / "link")
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                with self.assertRaisesRegex(module.CandidateStagerError, "symlink forbidden"):
                    module._collect_input_tree(fd, uid=uid, gid=gid)
            finally:
                os.close(fd)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            root.mkdir()
            os.chmod(root, module.INPUT_DIRECTORY_MODE)
            os.mkfifo(root / "pipe")
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                with self.assertRaisesRegex(module.CandidateStagerError, "special file forbidden"):
                    module._collect_input_tree(fd, uid=uid, gid=gid)
            finally:
                os.close(fd)

    def test_exact_tree_and_file_metadata_are_enforced(self) -> None:
        uid, gid = os.getuid(), os.getgid()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            files = [("apps/web/dist/index.html", b"ok")]
            write_input_tree(root, files)
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                self.assertEqual(module._collect_input_tree(fd, uid=uid, gid=gid), ["apps/web/dist/index.html"])
            finally:
                os.close(fd)
            os.chmod(root / "apps/web/dist/index.html", 0o644)
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                with self.assertRaisesRegex(module.CandidateStagerError, "metadata mismatch"):
                    module._collect_input_tree(fd, uid=uid, gid=gid)
            finally:
                os.close(fd)

    def test_copy_rehashes_same_descriptor_before_publish(self) -> None:
        uid, gid = os.getuid(), os.getgid()
        old_root_uid, old_root_gid = module.ROOT_UID, module.ROOT_GID
        module.ROOT_UID, module.ROOT_GID = uid, gid
        try:
            with tempfile.TemporaryDirectory() as tmp:
                input_root = Path(tmp) / "input"
                output_root = Path(tmp) / "output"
                write_input_tree(input_root, [("apps/web/dist/index.html", b"hello")])
                output_root.mkdir()
                os.chmod(output_root, module.OUTPUT_DIRECTORY_MODE)
                entry = module.CandidateEntry("apps/web/dist/index.html", 5, hashlib.sha256(b"hello").hexdigest())
                in_fd = os.open(input_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                out_fd = os.open(output_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    module._copy_verified_file(in_fd, out_fd, entry, uid=uid, gid=gid)
                finally:
                    os.close(in_fd)
                    os.close(out_fd)
                self.assertEqual((output_root / entry.path).read_bytes(), b"hello")
                self.assertEqual(stat.S_IMODE((output_root / entry.path).stat().st_mode), module.OUTPUT_FILE_MODE)
        finally:
            module.ROOT_UID, module.ROOT_GID = old_root_uid, old_root_gid


class FullMaterializationTests(unittest.TestCase):
    def test_preverified_tree_is_published_only_to_fixed_staging_namespace(self) -> None:
        uid, gid = os.getuid(), os.getgid()
        original = {
            "INPUT_ROOT": module.INPUT_ROOT,
            "INPUT_SOURCE": module.INPUT_SOURCE,
            "INPUT_MANIFEST": module.INPUT_MANIFEST,
            "STAGING_BASE": module.STAGING_BASE,
            "STAGING_ROOT": module.STAGING_ROOT,
            "STAGING_SOURCE": module.STAGING_SOURCE,
            "STAGING_MANIFEST": module.STAGING_MANIFEST,
            "ROOT_UID": module.ROOT_UID,
            "ROOT_GID": module.ROOT_GID,
        }
        try:
            with tempfile.TemporaryDirectory() as tmp:
                sandbox = Path(tmp)
                os.chmod(sandbox, module.OUTPUT_DIRECTORY_MODE)
                input_root = sandbox / "input" / module.REVIEWED_SOURCE_SHA
                input_root.parent.mkdir(mode=0o755)
                input_root.mkdir(mode=module.INPUT_DIRECTORY_MODE)
                source_root = input_root / module.SOURCE_NAME
                files = [
                    ("apps/web/dist/index.html", b"hello"),
                    ("tools/asset.txt", b"asset"),
                ]
                write_input_tree(source_root, files)
                raw, digest = manifest_for(files)
                manifest_path = input_root / module.MANIFEST_NAME
                manifest_path.write_bytes(raw)
                os.chmod(manifest_path, module.INPUT_FILE_MODE)
                os.chmod(input_root, module.INPUT_DIRECTORY_MODE)

                staging_base = sandbox / "staging"
                module.INPUT_ROOT = input_root
                module.INPUT_SOURCE = source_root
                module.INPUT_MANIFEST = manifest_path
                module.STAGING_BASE = staging_base
                module.STAGING_ROOT = staging_base / module.REVIEWED_SOURCE_SHA
                module.STAGING_SOURCE = module.STAGING_ROOT / module.SOURCE_NAME
                module.STAGING_MANIFEST = module.STAGING_ROOT / module.MANIFEST_NAME
                module.ROOT_UID = uid
                module.ROOT_GID = gid

                manifest = module._load_and_verify_input(expected_digest=digest, uid=uid, gid=gid)
                receipt = module._stage_verified_input(manifest, uid=uid, gid=gid)

                self.assertEqual(receipt["status"], "STAGED")
                self.assertEqual(receipt["source_sha"], module.REVIEWED_SOURCE_SHA)
                self.assertEqual(receipt["candidate_sha256"], digest)
                self.assertEqual((module.STAGING_SOURCE / "apps/web/dist/index.html").read_bytes(), b"hello")
                self.assertEqual(module.STAGING_MANIFEST.read_bytes(), raw)
                self.assertFalse((staging_base / module.PARTIAL_NAME).exists())
                self.assertEqual(stat.S_IMODE(module.STAGING_ROOT.stat().st_mode), module.OUTPUT_DIRECTORY_MODE)
                self.assertEqual(stat.S_IMODE(module.STAGING_MANIFEST.stat().st_mode), module.OUTPUT_FILE_MODE)
                self.assertEqual(receipt["production_release_materializations"], 0)
                self.assertEqual(receipt["current_pointer_swaps"], 0)
                self.assertEqual(receipt["apply_lock_mutations"], 0)
        finally:
            for name, value in original.items():
                setattr(module, name, value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
