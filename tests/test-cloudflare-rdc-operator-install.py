#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import unittest
from unittest import mock

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "install-cloudflare-rdc-operator.py"

spec = importlib.util.spec_from_file_location("cloudflare_rdc_operator_install", SOURCE)
assert spec and spec.loader
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

EXPECTED = "a" * 40


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], bytes | None]] = []

    def __call__(self, argv, *, input=None, stdout=None, stderr=None, check=False):
        args = list(argv)
        self.calls.append((args, input))
        output = b""
        rc = 0

        if args[:4] == ["/usr/bin/git", "-C", str(installer.ROOT), "rev-parse"]:
            if args[-1] == "--show-toplevel":
                output = (str(installer.ROOT) + "\n").encode()
            elif args[-1] == "HEAD":
                output = (EXPECTED + "\n").encode()
        elif args[:4] == ["/usr/bin/git", "-C", str(installer.ROOT), "branch"]:
            output = b"main\n"
        elif args[:4] == ["/usr/bin/git", "-C", str(installer.ROOT), "status"]:
            output = b""
        elif args[:4] == ["/usr/bin/git", "-C", str(installer.ROOT), "remote"]:
            output = b"https://github.com/rozkalnsandris/RPi5_main.git\n"
        elif args[:4] == ["/usr/bin/git", "-C", str(installer.ROOT), "ls-files"]:
            output = b"scripts/cloudflare_rdc_operator.py\n"
        elif args[:3] == [installer.SUDO, "-n", "/usr/bin/test"]:
            rc = 1
        elif args[:3] == [installer.SUDO, "-n", "/usr/bin/stat"]:
            target = args[-1]
            if target == str(installer.INSTALLED):
                output = b"root:root 500\n"
            elif target == str(installer.RELEASE_DIR):
                output = b"root:root 700\n"
            elif target == str(installer.RELEASE_METADATA):
                output = b"root:root 400\n"
        elif args[:3] == [installer.SUDO, "-n", "/usr/bin/sha256sum"]:
            target = args[-1]
            source = installer.SOURCE.read_bytes()
            if target == str(installer.INSTALLED):
                digest = hashlib.sha256(source).hexdigest()
            else:
                metadata = installer.build_release_metadata(EXPECTED, source)
                digest = hashlib.sha256(metadata).hexdigest()
            output = f"{digest}  {target}\n".encode()

        return subprocess.CompletedProcess(args, rc, stdout=output, stderr=b"")


class InstallerTests(unittest.TestCase):
    def test_installer_refuses_repository_python_as_root(self) -> None:
        with mock.patch.object(installer.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(
                installer.InstallError, "installer_must_not_run_as_root"
            ):
                installer.verify_exact_checkout(EXPECTED, runner=FakeRunner())

    def test_preflight_requires_exact_clean_main_and_absent_targets(self) -> None:
        runner = FakeRunner()
        with mock.patch.object(installer.os, "geteuid", return_value=1000):
            source, metadata = installer.preflight_install(
                EXPECTED, runner=runner
            )
        self.assertEqual(source, installer.SOURCE.read_bytes())
        self.assertEqual(
            metadata,
            installer.build_release_metadata(EXPECTED, source),
        )
        tested_paths = {
            call[0][-1]
            for call in runner.calls
            if call[0][:3] == [installer.SUDO, "-n", "/usr/bin/test"]
        }
        self.assertEqual(
            tested_paths,
            {
                str(installer.INSTALLED),
                str(installer.RELEASE_DIR),
                str(installer.RELEASE_METADATA),
            },
        )

    def test_apply_uses_only_reviewed_install_paths_and_no_sudoers(self) -> None:
        runner = FakeRunner()
        with mock.patch.object(installer.os, "geteuid", return_value=1000):
            installer.apply_install(EXPECTED, runner=runner)

        flattened = "\n".join(" ".join(call[0]) for call in runner.calls)
        self.assertIn(str(installer.INSTALLED), flattened)
        self.assertIn(str(installer.RELEASE_DIR), flattened)
        self.assertIn(str(installer.RELEASE_METADATA), flattened)
        self.assertNotIn("/etc/sudoers", flattened)
        self.assertNotIn("/etc/sudoers.d", flattened)

        install_calls = [
            call[0]
            for call in runner.calls
            if installer.INSTALL in call[0]
        ]
        self.assertEqual(len(install_calls), 2)
        self.assertTrue(
            any(str(installer.RELEASE_DIR) in call for call in install_calls)
        )
        self.assertTrue(
            any(str(installer.INSTALLED) in call for call in install_calls)
        )

    def test_release_metadata_binds_exact_main_and_operator_hash(self) -> None:
        source = b"operator-bytes"
        decoded = installer.json.loads(
            installer.build_release_metadata(EXPECTED, source)
        )
        self.assertEqual(decoded["source_sha"], EXPECTED)
        self.assertEqual(
            decoded["operator_sha256"], hashlib.sha256(source).hexdigest()
        )


if __name__ == "__main__":
    unittest.main()
