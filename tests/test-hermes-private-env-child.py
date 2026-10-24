#!/usr/bin/env python3
"""Synthetic filesystem/identity tests only; no production paths, sudo or Docker."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("child_operator", ROOT / "scripts/create-hermes-private-env.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# Approved synthetic marker; never use real configuration in this suite.
RAW = "".join(f"{key}={value}\n" for key, value in (
    ("POSTGRES_USER", "synthetic"),
    ("POSTGRES_PASSWORD", "ci-placeholder-not-a-secret"),
    ("POSTGRES_DB", "synthetic"),
    ("HTTP_USER_AGENT", "synthetic-test"),
    ("IGNORED", "irrelevant"),
)).encode()


class ChildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.base = Path(self.tmp.name)
        self.parent = self.base / "parent"
        self.parent.mkdir(mode=0o750)
        self.fd = os.open(self.parent, os.O_RDONLY | os.O_DIRECTORY)
        self.uid, self.gid = os.getuid(), os.getgid()
        self.receipt = {"mutation_attempted": False, "published": False,
                        "protected_read_started": False}

    def tearDown(self):
        os.close(self.fd)
        self.tmp.cleanup()

    def publish(self, revalidate=lambda: None):
        m.publish(self.fd, m.project(RAW), self.gid, revalidate, self.receipt,
                  root_uid=self.uid)

    def source(self, raw=RAW):
        p = self.parent / ".env"
        p.write_bytes(raw)
        p.chmod(0o600)
        return p

    def test_projection_is_exact_two_keys(self):
        projected = m.project(RAW)
        self.assertEqual(projected, (
            "DATABASE_URL='postgresql+psycopg://synthetic:ci-placeholder-not-a-secret@db:5432/synthetic'\n"
            "HTTP_USER_AGENT='synthetic-test'\n").encode())
        self.assertNotIn(b"IGNORED", projected)
        self.assertNotIn(b"HERMES_", projected)

    def test_invalid_projection_refused(self):
        for raw in (b"", RAW + b"POSTGRES_DB=duplicate\n",
                    RAW.replace(b"synthetic-test", b"bad'value"),
                    RAW.replace(b"synthetic-test", b'"line\\nline"'),
                    RAW.replace(b"POSTGRES_USER=synthetic", b"POSTGRES_USER=user@host"),
                    RAW.replace(b"POSTGRES_DB=synthetic", b"POSTGRES_DB=db%2fother")):
            with self.subTest(raw_kind=len(raw)), self.assertRaises(Exception):
                m.project(raw)

    def test_creation_preserves_parent_and_neighbor(self):
        neighbor = self.parent / "neighbor"
        neighbor.write_bytes(b"synthetic-neighbor")
        before = m.identity(os.fstat(self.fd))
        self.publish()
        self.assertEqual((self.parent / m.CHILD).read_bytes(), m.project(RAW))
        self.assertEqual(stat.S_IMODE((self.parent / m.CHILD).stat().st_mode), 0o640)
        self.assertEqual((self.parent / m.CHILD).stat().st_nlink, 1)
        self.assertEqual(m.identity(os.fstat(self.fd)), before)
        self.assertEqual(neighbor.read_bytes(), b"synthetic-neighbor")
        self.assertFalse((self.parent / m.STAGE).exists())
        self.assertTrue(self.receipt["published"])

    def test_existing_child_stage_or_legacy_stage_refuses_before_mutation(self):
        for name in (m.CHILD, m.STAGE, m.LEGACY_STAGE):
            with self.subTest(name=name):
                p = self.parent / name
                p.write_bytes(b"existing")
                with self.assertRaises(m.Stop):
                    self.publish()
                self.assertEqual(p.read_bytes(), b"existing")
                self.assertFalse(self.receipt["mutation_attempted"])
                p.unlink()

    def test_dangling_destination_symlink_not_treated_as_absent(self):
        (self.parent / m.CHILD).symlink_to(self.parent / "missing")
        with self.assertRaises(m.Stop):
            self.publish()
        self.assertFalse(self.receipt["mutation_attempted"])

    def test_atomic_collision_preserves_both_artifacts(self):
        def concurrent_target():
            (self.parent / m.CHILD).write_bytes(b"winner")
        with self.assertRaises(m.Stop):
            self.publish(concurrent_target)
        self.assertEqual((self.parent / m.CHILD).read_bytes(), b"winner")
        self.assertEqual((self.parent / m.STAGE).read_bytes(), m.project(RAW))
        self.assertTrue(self.receipt["mutation_attempted"])
        self.assertFalse(self.receipt["published"])

    def test_partial_write_failure_keeps_private_stage_without_retry(self):
        real_write = os.write
        calls = []
        def broken(fd, data):
            calls.append(1)
            if len(calls) == 1:
                return real_write(fd, data[:3])
            raise OSError("synthetic failure")
        with patch.object(m.os, "write", side_effect=broken), self.assertRaises(OSError):
            self.publish()
        self.assertEqual((self.parent / m.STAGE).read_bytes(), m.project(RAW)[:3])
        self.assertEqual(stat.S_IMODE((self.parent / m.STAGE).stat().st_mode), 0o600)
        self.assertFalse((self.parent / m.CHILD).exists())
        self.assertEqual(len(calls), 2)

    def test_identity_drift_keeps_stage_root_private(self):
        with self.assertRaises(m.Stop):
            self.publish(lambda: m.require(False))
        self.assertEqual(stat.S_IMODE((self.parent / m.STAGE).stat().st_mode), 0o600)
        self.assertFalse((self.parent / m.CHILD).exists())

    def test_post_publication_failure_reports_published_without_cleanup(self):
        original = m.os.fsync
        def fail_directory(fd):
            if fd == self.fd:
                raise OSError("synthetic sync failure")
            original(fd)
        with patch.object(m.os, "fsync", side_effect=fail_directory), self.assertRaises(OSError):
            self.publish()
        self.assertTrue(self.receipt["published"])
        self.assertTrue((self.parent / m.CHILD).exists())

    def test_source_bounded_regular_single_link_private(self):
        p = self.source()
        data, fingerprint = m.read_source(self.fd, self.uid, self.gid, self.receipt)
        self.assertEqual(data, m.project(RAW))
        self.assertEqual(fingerprint, m.fingerprint(p.stat()))
        p.chmod(0o644)
        with self.assertRaises(m.Stop):
            m.read_source(self.fd, self.uid, self.gid, {})
        p.chmod(0o600)
        os.link(p, self.parent / "extra")
        with self.assertRaises(m.Stop):
            m.read_source(self.fd, self.uid, self.gid, {})

    def test_source_symlink_fifo_and_oversize_refused(self):
        p = self.parent / ".env"
        for kind in ("symlink", "fifo", "oversize"):
            if kind == "symlink":
                p.symlink_to(self.parent / "missing")
            elif kind == "fifo":
                os.mkfifo(p, 0o600)
            else:
                self.source(b"x" * (m.MAX_BYTES + 1))
            with self.subTest(kind=kind), self.assertRaises(m.Stop):
                m.read_source(self.fd, self.uid, self.gid, {})
            p.unlink()

    def test_source_change_during_read_is_rejected(self):
        p = self.source()
        original_read = os.read
        def changed(fd, size):
            value = original_read(fd, size)
            p.write_bytes(RAW + b"# drift\n")
            return value
        with patch.object(m.os, "read", side_effect=changed), self.assertRaises(m.Stop):
            m.read_source(self.fd, self.uid, self.gid, {})

    def test_symlink_ancestor_and_writable_ancestor_rejected(self):
        # Use a synthetic root, so CI workspace ancestor permissions are irrelevant.
        base_fd = os.open(self.base, os.O_RDONLY | os.O_DIRECTORY)
        original_open = os.open
        def rooted(path, flags, *args, **kwargs):
            if path == "/":
                return os.dup(base_fd)
            return original_open(path, flags, *args, **kwargs)
        try:
            with patch.object(m.os, "open", side_effect=rooted):
                with m.directory(Path("/parent"), {self.uid}) as fd:
                    self.assertEqual(m.identity(os.fstat(fd)), m.identity(os.fstat(self.fd)))
                (self.base / "link").symlink_to(self.parent, target_is_directory=True)
                with self.assertRaises(OSError), m.directory(Path("/link"), {self.uid}):
                    pass
                self.parent.chmod(0o770)
                with self.assertRaises(m.Stop), m.directory(Path("/parent"), {self.uid}):
                    pass
        finally:
            os.close(base_fd)

    def test_acl_rejected(self):
        with patch.object(m.os, "listxattr", return_value=["system.posix_acl_access"]):
            with self.assertRaises(m.Stop):
                m.parent_check(self.fd, self.gid, root_uid=self.uid)

    def test_metadata_default_does_not_read_or_publish(self):
        self.source()
        @contextlib.contextmanager
        def local_directory(path, owners):
            yield self.fd
        account = SimpleNamespace(pw_uid=self.uid or 1234, pw_gid=self.gid, pw_dir=str(self.base))
        with patch.object(m.os, "geteuid", return_value=0), \
             patch.object(m, "source_check"), \
             patch.object(m, "runtime_identity", return_value=(1234, self.gid, 4321)), \
             patch.object(m.pwd, "getpwnam", return_value=account), \
             patch.object(m, "directory", side_effect=local_directory), \
             patch.object(m, "parent_check"), \
             patch.object(m, "file_check"), \
             patch.object(m, "read_source") as read, \
             patch.object(m, "publish") as publish:
            m.execute("a" * 40, False, self.receipt)
        read.assert_not_called()
        publish.assert_not_called()
        self.assertEqual(self.receipt["status"], "ABSENT_METADATA_ONLY")
        self.assertFalse(self.receipt["protected_read_started"])

    def test_apply_orchestration_reads_once_and_preserves_parent(self):
        if self.uid == 0:
            self.skipTest("synthetic source account must be non-root")
        self.source()
        @contextlib.contextmanager
        def local_directory(path, owners):
            yield self.fd
        account = SimpleNamespace(pw_uid=self.uid, pw_gid=self.gid, pw_dir=str(self.base))
        real_parent = m.parent_check
        real_publish = m.publish
        original = m.identity(os.fstat(self.fd))
        with patch.object(m.os, "geteuid", return_value=0), \
             patch.object(m, "source_check"), \
             patch.object(m, "runtime_identity", return_value=(1234, self.gid, 4321)), \
             patch.object(m.pwd, "getpwnam", return_value=account), \
             patch.object(m, "directory", side_effect=local_directory), \
             patch.object(m, "parent_check", side_effect=lambda fd, gid: real_parent(fd, gid, root_uid=self.uid)), \
             patch.object(m, "publish", side_effect=lambda fd, data, gid, validate, receipt: real_publish(fd, data, gid, validate, receipt, root_uid=self.uid)), \
             patch.object(m, "dac_readable") as dac, \
             patch.object(m, "read_source", wraps=m.read_source) as read:
            m.execute("a" * 40, True, self.receipt)
        read.assert_called_once()
        dac.assert_called_once_with(1234, self.gid, 4321)
        self.assertEqual(self.receipt["status"], "CHILD_CREATED")
        self.assertEqual(self.receipt["consumer_dac"], "DAC_READABLE")
        self.assertEqual(m.identity(os.fstat(self.fd)), original)
        self.assertEqual((self.parent / m.CHILD).read_bytes(), m.project(RAW))

    def test_dac_child_failure_is_not_readability(self):
        with patch.object(m.os, "fork", return_value=123), \
             patch.object(m.os, "waitpid", return_value=(123, 256)):
            with self.assertRaises(m.Stop):
                m.dac_readable(1234, 2345, 3456)

    def test_parent_wrong_mode_owner_or_group_refused(self):
        for mode, uid, gid in ((0o700, self.uid, self.gid),
                               (0o750, self.uid + 1, self.gid),
                               (0o750, self.uid, self.gid + 1)):
            self.parent.chmod(mode)
            with self.subTest(mode=mode, uid=uid, gid=gid), self.assertRaises(m.Stop):
                m.parent_check(self.fd, gid, root_uid=uid)

    def test_sanitized_error_preserves_progress(self):
        def failure(sha, apply, receipt):
            receipt["mutation_attempted"] = True
            raise OSError("PRIVATE-SYNTHETIC-CONTENT")
        out = io.StringIO()
        with patch.object(m, "execute", side_effect=failure), \
             patch.object(m.resource, "setrlimit"), contextlib.redirect_stdout(out):
            self.assertEqual(m.main(["--expected-source-sha", "a" * 40, "--apply"]), 2)
        self.assertNotIn("PRIVATE-SYNTHETIC-CONTENT", out.getvalue())
        result = json.loads(out.getvalue())
        self.assertTrue(result["mutation_attempted"])
        self.assertFalse(result["activation_eligible"])
        self.assertEqual(result["compose_runtime_access"], "NOT_PROVEN")

    def test_runtime_identity_rejects_wrong_unit_and_extra_members(self):
        account = SimpleNamespace(pw_uid=1234, pw_gid=2345)
        group = SimpleNamespace(gr_gid=2345)
        docker = SimpleNamespace(gr_gid=3456)
        body = ("LoadState=loaded\nUser=rozkalns-simple-deployer\n"
                "Group=rozkalns-simple-deployer\nSupplementaryGroups=docker\nDynamicUser=no\n")
        with patch.object(m.pwd, "getpwnam", return_value=account), \
             patch.object(m.grp, "getgrnam", side_effect=lambda n: docker if n == "docker" else group), \
             patch.object(m.v4, "_exclusive_runtime_group", return_value=True) as exclusive, \
             patch.object(m.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=body.encode())) as run:
            self.assertEqual(m.runtime_identity(), (1234, 2345, 3456))
            run.return_value.stdout = body.replace("User=rozkalns-simple-deployer", "User=root").encode()
            with self.assertRaises(m.Stop):
                m.runtime_identity()
            exclusive.return_value = False
            with self.assertRaises(m.Stop):
                m.runtime_identity()

    def test_source_contract_and_make_wiring(self):
        self.assertEqual(json.loads((ROOT / m.CONTRACT).read_text()), m.contract())
        make = (ROOT / "Makefile").read_text()
        self.assertEqual(make.count("python3 ./tests/test-hermes-private-env-child.py"), 1)
        with patch.object(m.v4, "_require_frozen_source") as frozen, \
             patch.object(m.v3, "_git_stdout_readonly", return_value=b"drift"):
            with self.assertRaises(m.Stop):
                m.source_check("a" * 40)
            frozen.assert_called_once_with("a" * 40)


if __name__ == "__main__":
    unittest.main()
