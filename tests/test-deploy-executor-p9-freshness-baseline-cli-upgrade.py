#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import runpy
import stat
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "scripts" / "install-deploy-executor-p9-freshness-baseline-cli-upgrade.py"


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


class P9FreshnessBaselineCliUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ns = runpy.run_path(str(OPERATOR))
        cls.source = OPERATOR.read_text(encoding="utf-8")

    def test_exact_single_target_contract(self) -> None:
        target = self.ns["TARGET"]
        self.assertEqual(target.source_path, "ops/bin/rozkalns-deploy-p9-control-baseline")
        self.assertEqual(
            target.target_path,
            Path("/usr/local/sbin/rozkalns-deploy-p9-control-baseline"),
        )
        self.assertEqual(target.old_blob_sha, "0afad9d93dd74570aeed31ccfdb8c5c7419ddcd8")
        self.assertEqual(target.new_blob_sha, "8dc38e4d224373925483a45b782f04e0aa27a8bd")
        self.assertEqual(target.mode, 0o755)
        self.assertNotIn("TARGETS", self.ns)

    def test_fail_closed_write_boundary_and_verification(self) -> None:
        source = self.source
        self.assertEqual(source.count("_preflight(args.expected_sha)"), 2)
        self.assertIn('if not hasattr(os, "O_NOFOLLOW"):', source)
        self.assertIn("os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW", source)
        inode_check = source.index("(path_now.st_dev, path_now.st_ino)")
        first_write = source.index("os.ftruncate(fd, 0)")
        self.assertLess(inode_check, first_write)
        self.assertIn("installed != reviewed_bytes", source)
        self.assertIn("_git_blob_sha(installed) != TARGET.new_blob_sha", source)
        self.assertIn("_target_metadata(after) != (0, 0, TARGET.mode)", source)

    def test_source_exposes_no_second_runtime_target_or_alternate_path(self) -> None:
        source = self.source
        self.assertEqual(
            source.count('Path("/usr/local/sbin/rozkalns-deploy-p9-control-baseline")'),
            1,
        )
        for forbidden in (
            "/usr/local/lib/rozkalns-deploy-executor/",
            "/etc/rozkalns-deploy-executor-p9/",
            "/etc/systemd/",
            "/var/lib/rozkalns-deploy-executor",
        ):
            self.assertNotIn(forbidden, source)
        for marker in (
            'print("TARGETS_REPLACED=1")',
            'print("SOURCE_AUTH_TOUCHED=NO")',
            'print("CONFIG_REGISTRY_MUTATION=NO")',
            'print("SYSTEMD_MUTATION=NO")',
            'print("CREDENTIAL_READ=NO")',
            'print("D1_REQUEST=NO")',
            'print("BASELINE_COLLECTION=NO")',
            'print("LIVE_AUTH_MUTATION=NO")',
            'print("P9_EXECUTION=NO")',
            'print("P10_EXECUTION=NO")',
            'print("ROLLBACK_PATH=NO")',
            'print("RETRY_PATH=NO")',
            'print("CLEANUP_PATH=NO")',
            'print("ALTERNATE_MUTATION_PATH=NO")',
        ):
            self.assertIn(marker, source)

    def test_replace_helper_changes_only_fixed_target_not_neighbor(self) -> None:
        ns = self.ns
        TargetSpec = ns["TargetSpec"]
        replace = ns["_replace_exact_target"]
        original_target = ns["TARGET"]
        original_metadata = ns["_target_metadata"]

        old_bytes = b"reviewed-old-baseline-cli\n"
        new_bytes = b"reviewed-repaired-baseline-cli\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target_path = root / "rozkalns-deploy-p9-control-baseline"
            neighbor_path = root / "neighbor-runtime-file"
            target_path.write_bytes(old_bytes)
            neighbor_bytes = b"must-remain-unchanged\n"
            neighbor_path.write_bytes(neighbor_bytes)
            target_path.chmod(0o755)

            ns["TARGET"] = TargetSpec(
                source_path="ops/bin/rozkalns-deploy-p9-control-baseline",
                target_path=target_path,
                old_blob_sha=git_blob_sha(old_bytes),
                new_blob_sha=git_blob_sha(new_bytes),
                mode=0o755,
            )
            ns["_target_metadata"] = lambda st: (0, 0, stat.S_IMODE(st.st_mode))
            try:
                replace(new_bytes)
            finally:
                ns["TARGET"] = original_target
                ns["_target_metadata"] = original_metadata

            self.assertEqual(target_path.read_bytes(), new_bytes)
            self.assertEqual(stat.S_IMODE(target_path.stat().st_mode), 0o755)
            self.assertEqual(neighbor_path.read_bytes(), neighbor_bytes)
            self.assertEqual(
                sorted(path.name for path in root.iterdir()),
                ["neighbor-runtime-file", "rozkalns-deploy-p9-control-baseline"],
            )


if __name__ == "__main__":
    unittest.main()
