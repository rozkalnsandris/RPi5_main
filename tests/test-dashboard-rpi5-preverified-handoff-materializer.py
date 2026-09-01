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
SCRIPT = ROOT / "scripts" / "dashboard-rpi5-preverified-handoff-materializer.py"
loader = importlib.machinery.SourceFileLoader("dashboard_handoff_materializer_tested", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
module = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = module
loader.exec_module(module)


class PatchedCandidate:
    def __init__(self, files: list[tuple[str, bytes]]) -> None:
        self.files = sorted(files)
        self.original = {
            "EXPECTED_FILE_COUNT": module.EXPECTED_FILE_COUNT,
            "EXPECTED_TOTAL_BYTES": module.EXPECTED_TOTAL_BYTES,
            "EXPECTED_CANDIDATE_SHA256": module.EXPECTED_CANDIDATE_SHA256,
            "HANDOFF_MUTATION_BUDGET": module.HANDOFF_MUTATION_BUDGET,
        }
        entries = [
            {"path": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for path, data in self.files
        ]
        core = {
            "schema": module.MANIFEST_SCHEMA,
            "sourceSha": module.REVIEWED_SOURCE_SHA,
            "releasePath": f"/opt/dashboard_RPi5/releases/{module.REVIEWED_SOURCE_SHA}",
            "nodeMajor": 24,
            "hashAlgorithm": "sha256",
            "fileCount": len(entries),
            "totalBytes": sum(entry["bytes"] for entry in entries),
            "files": entries,
        }
        self.digest = hashlib.sha256(json.dumps(core, separators=(",", ":")).encode()).hexdigest()
        self.raw = json.dumps({**core, "candidateSha256": self.digest}, separators=(",", ":")).encode()

    def __enter__(self):
        module.EXPECTED_FILE_COUNT = len(self.files)
        module.EXPECTED_TOTAL_BYTES = sum(len(data) for _, data in self.files)
        module.EXPECTED_CANDIDATE_SHA256 = self.digest
        module.HANDOFF_MUTATION_BUDGET = (
            ("handoff-candidate-partial-root-create", 1),
            ("handoff-source-root-create", 1),
            ("handoff-file-materialization", len(self.files)),
            ("handoff-manifest-materialization", 1),
            ("handoff-final-no-replace-rename", 1),
        )
        return self

    def __exit__(self, exc_type, exc, tb):
        for name, value in self.original.items():
            setattr(module, name, value)


def write_ingress(root: Path, files: list[tuple[str, bytes]], raw_manifest: bytes) -> None:
    root.mkdir(parents=True, mode=0o755)
    source = root / module.SOURCE_NAME
    source.mkdir(mode=0o755)
    for rel, data in sorted(files):
        path = source / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        os.chmod(path, module.INGRESS_FILE_MODE)
    manifest = root / module.MANIFEST_NAME
    manifest.write_bytes(raw_manifest)
    os.chmod(manifest, module.INGRESS_FILE_MODE)
    directories = [p for p in source.rglob("*") if p.is_dir()]
    for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
        os.chmod(directory, module.INGRESS_DIRECTORY_MODE)
    os.chmod(source, module.INGRESS_DIRECTORY_MODE)
    os.chmod(root, module.INGRESS_DIRECTORY_MODE)


class SourceContractTests(unittest.TestCase):
    def test_exact_reviewed_binding_and_fixed_paths(self) -> None:
        self.assertEqual(module.REVIEWED_SOURCE_SHA, "066b9a24008dd57439f9e66eae198416c4dfc590")
        self.assertEqual(module.REVIEWED_SOURCE_TREE_SHA, "62756ba22fc8d47e44988c086c08dcf37779cfb3")
        self.assertEqual(module.REVIEWED_PARENT_SHA, "5f7739348f56398d0ba301c9320e1de0062838fc")
        self.assertEqual(module.REVIEWED_PRODUCER_BLOB_SHA, "bea0f30602d119ae53b81e70ce2d4c283d369ce8")
        self.assertEqual(module.EXPECTED_CANDIDATE_SHA256, "d12a49de01891e3a4cc188fa16c173c5eb44c786f013d3a6ebfefe95dcaa47b9")
        self.assertEqual(module.EXPECTED_FILE_COUNT, 72)
        self.assertEqual(module.EXPECTED_TOTAL_BYTES, 6773246)
        expected_ingress = Path("/home") / module.INGRESS_OWNER / ".cache" / "rozkalns-dashboard-preverified-ingress" / module.REVIEWED_SOURCE_SHA
        self.assertEqual(module.INGRESS_ROOT, expected_ingress)
        self.assertEqual(str(module.HANDOFF_ROOT), f"/var/lib/rozkalns-deploy-executor/dashboard-candidate-input/{module.REVIEWED_SOURCE_SHA}")
        self.assertEqual(module.INGRESS_DIRECTORY_MODE, 0o555)
        self.assertEqual(module.INGRESS_FILE_MODE, 0o444)
        self.assertEqual(module.HANDOFF_DIRECTORY_MODE, 0o555)
        self.assertEqual(module.HANDOFF_FILE_MODE, 0o444)
        self.assertEqual(module.HANDOFF_MUTATION_BUDGET[-1], ("handoff-final-no-replace-rename", 1))

    def test_cli_has_no_dynamic_authority_and_root_source_ignores_prep_root(self) -> None:
        args = module._parse_args(["--apply", "--ack", module.ACK])
        self.assertTrue(args.apply)
        self.assertEqual(args.ack, module.ACK)
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "--source", "--path", "--manifest", "--candidate", "--digest", "--command", "--script", "--argv", "--environment",
            "20260901T210735Z", "p10-dashboard-candidate-066b9a24008dd57439f9e66eae198416c4dfc590-",
            "subprocess", "os.system(", "shell=True", "Popen(", "execv(", "/usr/bin/node", "npm ", "pnpm ", "git ", "curl ", "wget ",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("/home/" + module.INGRESS_OWNER + "/", source)

    def test_production_and_normal_stager_targets_are_outside_mutation_scope(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("/var/lib/rozkalns-dashboard-release-candidates", source)
        self.assertNotIn("/opt/dashboard_RPi5/current", source)
        self.assertNotIn(".dashboard-release-controller.lock", source)
        self.assertIn('"normal_candidate_stager_invocations": 0', source)
        self.assertIn('"production_release_materializations": 0', source)
        self.assertIn('"candidate_javascript_executed_as_root": False', source)


class ManifestAdversarialTests(unittest.TestCase):
    def test_manifest_accepts_only_exact_count_total_digest_and_source(self) -> None:
        files = [("a", b"abc"), ("nested/b", b"defgh")]
        with PatchedCandidate(files) as candidate:
            parsed = module._parse_manifest(candidate.raw)
            self.assertEqual(parsed.candidate_sha256, candidate.digest)
            self.assertEqual(len(parsed.entries), 2)

            value = json.loads(candidate.raw)
            value["sourceSha"] = "1" * 40
            with self.assertRaisesRegex(module.HandoffMaterializerError, "source/schema mismatch"):
                module._parse_manifest(json.dumps(value, separators=(",", ":")).encode())

            value = json.loads(candidate.raw)
            value["candidateSha256"] = "0" * 64
            with self.assertRaisesRegex(module.HandoffMaterializerError, "self-digest mismatch|reviewed preverification"):
                module._parse_manifest(json.dumps(value, separators=(",", ":")).encode())

            old_count = module.EXPECTED_FILE_COUNT
            module.EXPECTED_FILE_COUNT = 3
            try:
                with self.assertRaisesRegex(module.HandoffMaterializerError, "file count"):
                    module._parse_manifest(candidate.raw)
            finally:
                module.EXPECTED_FILE_COUNT = old_count

    def test_path_traversal_and_reserved_components_are_rejected(self) -> None:
        for path in ("../escape", "/absolute", "a/../b", "a//b", "a\\b", "node_modules/x", "candidate-manifest.json"):
            with self.subTest(path=path):
                with self.assertRaises(module.HandoffMaterializerError):
                    module._safe_parts(path)


class DescriptorSafetyTests(unittest.TestCase):
    def test_symlink_and_special_file_are_rejected(self) -> None:
        uid, gid = os.getuid(), os.getgid()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            root.mkdir()
            os.chmod(root, module.INGRESS_DIRECTORY_MODE)
            (root / "ok").write_bytes(b"x")
            os.chmod(root / "ok", module.INGRESS_FILE_MODE)
            os.symlink("ok", root / "link")
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                with self.assertRaisesRegex(module.HandoffMaterializerError, "symlink forbidden"):
                    module._collect_ingress_tree(fd, uid=uid, gid=gid)
            finally:
                os.close(fd)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            root.mkdir()
            os.chmod(root, module.INGRESS_DIRECTORY_MODE)
            os.mkfifo(root / "pipe")
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                with self.assertRaisesRegex(module.HandoffMaterializerError, "special file forbidden"):
                    module._collect_ingress_tree(fd, uid=uid, gid=gid)
            finally:
                os.close(fd)

    def test_ingress_metadata_is_enforced(self) -> None:
        uid, gid = os.getuid(), os.getgid()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            root.mkdir()
            (root / "a").write_bytes(b"x")
            os.chmod(root / "a", 0o644)
            os.chmod(root, module.INGRESS_DIRECTORY_MODE)
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                with self.assertRaisesRegex(module.HandoffMaterializerError, "metadata mismatch"):
                    module._collect_ingress_tree(fd, uid=uid, gid=gid)
            finally:
                os.close(fd)


class FullMaterializationTests(unittest.TestCase):
    def _patched_paths(self, sandbox: Path):
        original = {
            "INGRESS_ROOT": module.INGRESS_ROOT,
            "INGRESS_SOURCE": module.INGRESS_SOURCE,
            "INGRESS_MANIFEST": module.INGRESS_MANIFEST,
            "HANDOFF_BASE": module.HANDOFF_BASE,
            "HANDOFF_ROOT": module.HANDOFF_ROOT,
            "HANDOFF_SOURCE": module.HANDOFF_SOURCE,
            "HANDOFF_MANIFEST": module.HANDOFF_MANIFEST,
        }
        ingress = sandbox / "ingress" / module.REVIEWED_SOURCE_SHA
        handoff_base = sandbox / "handoff"
        handoff_base.mkdir(mode=module.HANDOFF_BASE_MODE)
        module.INGRESS_ROOT = ingress
        module.INGRESS_SOURCE = ingress / module.SOURCE_NAME
        module.INGRESS_MANIFEST = ingress / module.MANIFEST_NAME
        module.HANDOFF_BASE = handoff_base
        module.HANDOFF_ROOT = handoff_base / module.REVIEWED_SOURCE_SHA
        module.HANDOFF_SOURCE = module.HANDOFF_ROOT / module.SOURCE_NAME
        module.HANDOFF_MANIFEST = module.HANDOFF_ROOT / module.MANIFEST_NAME
        return original, ingress, handoff_base

    def test_exact_tree_materializes_to_fixed_handoff_with_final_metadata(self) -> None:
        uid, gid = os.getuid(), os.getgid()
        files = [("apps/web/dist/index.html", b"hello"), ("tools/asset.txt", b"asset")]
        with PatchedCandidate(files) as candidate, tempfile.TemporaryDirectory() as tmp:
            original, ingress, handoff_base = self._patched_paths(Path(tmp))
            try:
                write_ingress(ingress, files, candidate.raw)
                manifest = module._load_and_verify_ingress(uid=uid, gid=gid)
                receipt = module._materialize_handoff(manifest, ingress_uid=uid, ingress_gid=gid, handoff_uid=uid, handoff_gid=gid, build_uid=uid, build_gid=gid)
                self.assertEqual(receipt["status"], "MATERIALIZED")
                self.assertFalse((handoff_base / module.PARTIAL_NAME).exists())
                self.assertEqual((module.HANDOFF_SOURCE / "apps/web/dist/index.html").read_bytes(), b"hello")
                self.assertEqual(module.HANDOFF_MANIFEST.read_bytes(), candidate.raw)
                self.assertEqual(stat.S_IMODE(module.HANDOFF_ROOT.stat().st_mode), module.HANDOFF_DIRECTORY_MODE)
                self.assertEqual(stat.S_IMODE(module.HANDOFF_SOURCE.stat().st_mode), module.HANDOFF_DIRECTORY_MODE)
                self.assertEqual(stat.S_IMODE(module.HANDOFF_MANIFEST.stat().st_mode), module.HANDOFF_FILE_MODE)
                self.assertEqual(module.HANDOFF_ROOT.stat().st_uid, uid)
                self.assertEqual(module.HANDOFF_ROOT.stat().st_gid, gid)
            finally:
                for name, value in original.items():
                    setattr(module, name, value)

    def test_target_or_partial_preexistence_fails_before_mutation(self) -> None:
        uid, gid = os.getuid(), os.getgid()
        files = [("a", b"x")]
        with PatchedCandidate(files) as candidate:
            for occupied_name in (module.REVIEWED_SOURCE_SHA, module.PARTIAL_NAME):
                with self.subTest(occupied_name=occupied_name), tempfile.TemporaryDirectory() as tmp:
                    original, ingress, handoff_base = self._patched_paths(Path(tmp))
                    try:
                        write_ingress(ingress, files, candidate.raw)
                        manifest = module._load_and_verify_ingress(uid=uid, gid=gid)
                        (handoff_base / occupied_name).mkdir()
                        with self.assertRaisesRegex(module.HandoffMaterializerError, "already exists"):
                            module._materialize_handoff(manifest, ingress_uid=uid, ingress_gid=gid, handoff_uid=uid, handoff_gid=gid, build_uid=uid, build_gid=gid)
                        self.assertFalse((handoff_base / module.PARTIAL_NAME).exists() and occupied_name != module.PARTIAL_NAME)
                    finally:
                        for name, value in original.items():
                            setattr(module, name, value)

    def test_post_preverification_digest_drift_preserves_partial_and_never_publishes(self) -> None:
        uid, gid = os.getuid(), os.getgid()
        files = [("a", b"hello"), ("b", b"world")]
        with PatchedCandidate(files) as candidate, tempfile.TemporaryDirectory() as tmp:
            original, ingress, handoff_base = self._patched_paths(Path(tmp))
            try:
                write_ingress(ingress, files, candidate.raw)
                manifest = module._load_and_verify_ingress(uid=uid, gid=gid)
                drift = ingress / module.SOURCE_NAME / "a"
                os.chmod(drift, 0o644)
                drift.write_bytes(b"HELLO")
                os.chmod(drift, module.INGRESS_FILE_MODE)
                with self.assertRaisesRegex(module.HandoffMaterializerError, "digest drift"):
                    module._materialize_handoff(manifest, ingress_uid=uid, ingress_gid=gid, handoff_uid=uid, handoff_gid=gid, build_uid=uid, build_gid=gid)
                self.assertTrue((handoff_base / module.PARTIAL_NAME).is_dir())
                self.assertFalse((handoff_base / module.REVIEWED_SOURCE_SHA).exists())
            finally:
                for name, value in original.items():
                    setattr(module, name, value)


class MachineAndHumanContractTests(unittest.TestCase):
    def test_machine_contract_matches_source_and_downstream_stager(self) -> None:
        contract = json.loads((ROOT / "ops" / "deploy" / "dashboard-preverified-handoff-materializer-v1.json").read_text(encoding="utf-8"))
        self.assertFalse(contract["execution_enabled"])
        self.assertEqual(contract["capability"], module.CAPABILITY)
        self.assertEqual(contract["reviewed_source_sha"], module.REVIEWED_SOURCE_SHA)
        self.assertEqual(contract["preverification_binding"]["candidate_sha256"], module.EXPECTED_CANDIDATE_SHA256)
        self.assertEqual(contract["preverification_binding"]["file_count"], 72)
        self.assertEqual(contract["preverification_binding"]["total_bytes"], 6773246)
        ingress_contract = contract["unprivileged_ingress"]
        self.assertEqual(ingress_contract["root_template"].format(owner=ingress_contract["owner"]), str(module.INGRESS_ROOT))
        self.assertTrue(ingress_contract["owner_component_is_fixed"])
        self.assertFalse(ingress_contract["caller_selectable"])
        self.assertFalse(ingress_contract["timestamp_pid_prep_root_allowed_as_privileged_input"])
        self.assertEqual(contract["service_owned_handoff"]["root"], str(module.HANDOFF_ROOT))
        self.assertEqual(contract["service_owned_handoff"]["directory_mode"], "0555")
        self.assertEqual(contract["service_owned_handoff"]["file_mode"], "0444")
        self.assertEqual(contract["service_owned_handoff"]["publish"], "renameat2-RENAME_NOREPLACE")
        self.assertEqual(contract["failure_policy"]["deletion_budget"], 0)
        self.assertTrue(contract["failure_policy"]["preserve_partial_after_post_mutation_failure"])
        self.assertFalse(contract["source_state"]["live_authority"])
        self.assertFalse(contract["source_state"]["merge_authorizes_handoff_materialization"])
        registry = json.loads((ROOT / "ops" / "deploy" / "executor-operations.json").read_text(encoding="utf-8"))
        self.assertFalse(registry["execution_enabled"])
        stager = json.loads((ROOT / "ops" / "deploy" / "dashboard-candidate-stager-v1.json").read_text(encoding="utf-8"))
        self.assertFalse(stager["execution_enabled"])
        self.assertEqual(stager["preverified_input"]["root"], str(module.HANDOFF_ROOT))

    def test_gate_sequence_and_human_contract_are_explicit(self) -> None:
        contract = json.loads((ROOT / "ops" / "deploy" / "dashboard-preverified-handoff-materializer-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(
            contract["post_merge_gate_sequence"],
            [
                "unprivileged-preverification-pass",
                "separate-handoff-materialization-live-root-gate",
                "read-only-handoff-proof",
                "separate-candidate-stager-live-root-gate",
                "read-only-candidate-staging-proof",
                "trusted-controller-plan-only-gate",
                "ready-reconciliation",
                "later-apply-live-auth",
            ],
        )
        doc = (ROOT / "docs" / "OWNER_AUTHORIZED_PULL_DEPLOY_EXECUTOR_P10_DASHBOARD_HANDOFF_MATERIALIZER.md").read_text(encoding="utf-8")
        for required in (
            "separate handoff-materialization LIVE/root gate",
            "read-only handoff proof",
            "separate candidate-stager LIVE/root gate",
            "trusted-controller PLAN-only gate",
            "READY reconciliation",
            "APPLY LIVE-AUTH",
            "execution_enabled=false",
            "grants **no** host/root/LIVE authority",
        ):
            self.assertIn(required, doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
