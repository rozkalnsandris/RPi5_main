from __future__ import annotations

import json
import os
from pathlib import Path
import runpy
import stat
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "scripts" / "install-deploy-executor-p9-hermes-source-auth-upgrade.py"
MANIFEST = ROOT / "ops" / "deploy" / "p9-hermes-source-auth-runtime-upgrade.json"
SOURCE_AUTH = ROOT / "ops" / "lib" / "deploy_executor" / "p9_source_auth.py"
OLD_BLOB = "4cb441873df8245387f06ee55d637a9f7b11cdc8"
NEW_BLOB = "130fc36a22bb4ace500b022c3defcccbf0893012"


class P9HermesSourceAuthRuntimeUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = runpy.run_path(str(OPERATOR))
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_contract_is_exact_one_target_old_to_new_transition(self):
        target = self.ns["TARGET"]
        self.assertEqual(target.source_path, "ops/lib/deploy_executor/p9_source_auth.py")
        self.assertEqual(
            str(target.target_path),
            "/usr/local/lib/rozkalns-deploy-executor/deploy_executor/p9_source_auth.py",
        )
        self.assertEqual(target.old_blob_sha, OLD_BLOB)
        self.assertEqual(target.new_blob_sha, NEW_BLOB)
        self.assertEqual((target.uid, target.gid, target.mode), (0, 0, 0o644))
        self.assertEqual(self.ns["_git_blob_sha"](SOURCE_AUTH.read_bytes()), NEW_BLOB)

    def test_manifest_binds_operator_and_atomic_replacement_policy(self):
        manifest = self.manifest
        self.assertEqual(manifest["target"]["old_blob"], OLD_BLOB)
        self.assertEqual(manifest["target"]["new_blob"], NEW_BLOB)
        self.assertEqual(manifest["operator"]["mutation_target_count"], 1)
        self.assertEqual(
            self.ns["_git_blob_sha"](OPERATOR.read_bytes()),
            manifest["operator"]["source_blob"],
        )
        replacement = manifest["replacement"]
        self.assertTrue(replacement["temp_same_directory"])
        self.assertTrue(replacement["temp_fsync_before_replace"])
        self.assertTrue(replacement["atomic_namespace_replace"])
        self.assertTrue(replacement["parent_directory_fsync_after_replace"])
        self.assertFalse(replacement["in_place_truncate_write"])

    def test_source_contract_preserves_fail_closed_boundary(self):
        source = OPERATOR.read_text(encoding="utf-8")
        self.assertEqual(source.count("reviewed = _preflight(source_sha)"), 2)
        self.assertIn('"-c"', source)
        self.assertIn('safe.directory={ROOT}', source)
        self.assertIn("os.O_NOFOLLOW", source)
        self.assertIn("os.O_EXCL", source)
        self.assertIn("os.fsync(temp_fd)", source)
        self.assertIn("os.replace(", source)
        self.assertIn("src_dir_fd=parent_fd", source)
        self.assertIn("dst_dir_fd=parent_fd", source)
        self.assertIn("os.fsync(parent_fd)", source)
        self.assertNotIn("os.ftruncate", source)
        self.assertNotIn("os.unlink", source)
        self.assertNotIn("os.remove", source)
        self.assertIn('"automatic_retry": False', source)
        self.assertIn('"automatic_rollback": False', source)
        self.assertIn('"automatic_cleanup": False', source)
        self.assertLess(source.index('state["mutation_started"] = True'), source.index("os.open(TEMP_NAME"))
        self.assertLess(source.index("os.fsync(temp_fd)"), source.index("os.replace("))
        self.assertLess(source.index("_require_target_old(parent_fd, target_fd)", source.index("Revalidate")), source.index("os.replace("))

    def test_atomic_helper_replaces_only_exact_old_blob(self):
        TargetSpec = self.ns["TargetSpec"]
        replace = self.ns["_replace_exact_target"]
        blob = self.ns["_git_blob_sha"]
        old = b"reviewed-old-source-auth\n"
        new = b"reviewed-new-hermes-source-auth\n"
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            target_path = parent / "p9_source_auth.py"
            target_path.write_bytes(old)
            target_path.chmod(0o644)
            spec = TargetSpec(
                source_path="ignored",
                target_path=target_path,
                old_blob_sha=blob(old),
                new_blob_sha=blob(new),
                uid=os.getuid(),
                gid=os.getgid(),
                mode=0o644,
            )
            globals_dict = replace.__globals__
            original_target = globals_dict["TARGET"]
            original_open_parent = globals_dict["_open_parent_fd"]
            globals_dict["TARGET"] = spec
            flags = os.O_RDONLY | os.O_CLOEXEC
            if hasattr(os, "O_DIRECTORY"):
                flags |= os.O_DIRECTORY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            globals_dict["_open_parent_fd"] = lambda: os.open(parent, flags)
            try:
                state = {"mutation_started": False, "target_replaced": False}
                replace(new, state)
            finally:
                globals_dict["TARGET"] = original_target
                globals_dict["_open_parent_fd"] = original_open_parent

            self.assertEqual(target_path.read_bytes(), new)
            st = target_path.stat()
            self.assertTrue(stat.S_ISREG(st.st_mode))
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o644)
            self.assertEqual(st.st_nlink, 1)
            self.assertEqual(state, {"mutation_started": True, "target_replaced": True})
            self.assertFalse((parent / self.ns["TEMP_NAME"]).exists())

    def test_wrong_old_blob_fails_before_mutation(self):
        TargetSpec = self.ns["TargetSpec"]
        replace = self.ns["_replace_exact_target"]
        UpgradeError = self.ns["UpgradeError"]
        blob = self.ns["_git_blob_sha"]
        expected_old = b"expected-old\n"
        observed_wrong = b"wrong-old\n"
        new = b"new-reviewed\n"
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            target_path = parent / "p9_source_auth.py"
            target_path.write_bytes(observed_wrong)
            target_path.chmod(0o644)
            spec = TargetSpec("ignored", target_path, blob(expected_old), blob(new), os.getuid(), os.getgid(), 0o644)
            globals_dict = replace.__globals__
            original_target = globals_dict["TARGET"]
            original_open_parent = globals_dict["_open_parent_fd"]
            globals_dict["TARGET"] = spec
            flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            globals_dict["_open_parent_fd"] = lambda: os.open(parent, flags)
            state = {"mutation_started": False, "target_replaced": False}
            try:
                with self.assertRaises(UpgradeError):
                    replace(new, state)
            finally:
                globals_dict["TARGET"] = original_target
                globals_dict["_open_parent_fd"] = original_open_parent
            self.assertEqual(state, {"mutation_started": False, "target_replaced": False})
            self.assertEqual(target_path.read_bytes(), observed_wrong)
            self.assertFalse((parent / self.ns["TEMP_NAME"]).exists())

    def test_post_mutation_replace_error_preserves_fail_closed_temp(self):
        TargetSpec = self.ns["TargetSpec"]
        replace = self.ns["_replace_exact_target"]
        blob = self.ns["_git_blob_sha"]
        old = b"reviewed-old\n"
        new = b"reviewed-new\n"
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            target_path = parent / "p9_source_auth.py"
            target_path.write_bytes(old)
            target_path.chmod(0o644)
            spec = TargetSpec("ignored", target_path, blob(old), blob(new), os.getuid(), os.getgid(), 0o644)
            globals_dict = replace.__globals__
            original_target = globals_dict["TARGET"]
            original_open_parent = globals_dict["_open_parent_fd"]
            original_replace = os.replace
            globals_dict["TARGET"] = spec
            flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            globals_dict["_open_parent_fd"] = lambda: os.open(parent, flags)
            os.replace = lambda *args, **kwargs: (_ for _ in ()).throw(OSError("synthetic replace failure"))
            state = {"mutation_started": False, "target_replaced": False}
            try:
                with self.assertRaises(OSError):
                    replace(new, state)
            finally:
                os.replace = original_replace
                globals_dict["TARGET"] = original_target
                globals_dict["_open_parent_fd"] = original_open_parent
            self.assertEqual(state, {"mutation_started": True, "target_replaced": False})
            self.assertEqual(target_path.read_bytes(), old)
            temp_path = parent / self.ns["TEMP_NAME"]
            self.assertTrue(temp_path.exists())
            self.assertEqual(temp_path.read_bytes(), new)

    def test_default_cli_mode_is_preflight_only(self):
        args = self.ns["_parse_args"](["a" * 40])
        self.assertFalse(args.apply)
        self.assertEqual(args.expected_sha, "a" * 40)


if __name__ == "__main__":
    unittest.main()
