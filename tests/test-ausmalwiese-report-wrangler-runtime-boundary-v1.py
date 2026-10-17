#!/usr/bin/env python3
"""Offline tests for the report Wrangler root-owned secrets runtime boundary."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import stat
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/ausmalwiese_report_wrangler_deploy_v1.py"
spec = importlib.util.spec_from_file_location("report_runtime_1075", SOURCE)
assert spec and spec.loader
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)


def application():
    return {
        "schema": "ausmalwiese.report-wrangler-source.v1",
        "repository": plan.SOURCE_REPO,
        "commit": plan.SOURCE_COMMIT,
        "worker_path": plan.WORKER_PATH,
        "worker_blob": plan.WORKER_BLOB,
        "config_path": plan.CONFIG_PATH,
        "config_blob": plan.CONFIG_BLOB,
        "config": copy.deepcopy(plan.expected_config()),
    }


def directory(mode=0o755, *, uid=0, gid=0, ino=1, dev=1):
    return SimpleNamespace(
        st_mode=stat.S_IFDIR | mode,
        st_uid=uid,
        st_gid=gid,
        st_nlink=2,
        st_size=0,
        st_ino=ino,
        st_dev=dev,
    )


def regular(
    mode=0o600, *, uid=0, gid=0, links=1, size=249, ino=9, dev=8
):
    return SimpleNamespace(
        st_mode=stat.S_IFREG | mode,
        st_uid=uid,
        st_gid=gid,
        st_nlink=links,
        st_size=size,
        st_ino=ino,
        st_dev=dev,
    )


def runtime_lstat(path):
    if path == str(plan.RUNTIME_ENTRY):
        return regular(0o500, size=20000, ino=20, dev=2)
    if path == plan.RUNTIME_SECRETS_FILE:
        return regular()
    if path == "/etc/rpi5-secrets/cloudflare":
        return directory(0o700, ino=4, dev=2)
    if path in {
        "/",
        "/usr",
        "/usr/local",
        "/usr/local/sbin",
        "/etc",
        "/etc/rpi5-secrets",
    }:
        return directory(0o755, ino=3, dev=2)
    raise FileNotFoundError(path)


class RuntimeBoundaryTests(unittest.TestCase):
    def test_contract_keeps_source_only_and_binds_runtime_boundary(self):
        data = __import__("json").loads(plan.CONTRACT.read_text("utf-8"))
        plan.check_contract(data)
        launcher = data["launcher"]
        self.assertEqual(
            launcher["runtime_entry"],
            "/usr/local/sbin/rpi5-ausmalwiese-report-wrangler-deploy",
        )
        self.assertEqual(
            launcher["runtime_secrets_file"],
            "/etc/rpi5-secrets/cloudflare/"
            "ausmalwiese-report-wrangler-secrets.json",
        )
        self.assertEqual(
            launcher["runtime_secrets_transport"],
            "sealed-memfd-via-dev-stdin",
        )
        self.assertEqual(launcher["runtime_operator"], "andris")
        self.assertFalse(launcher["runtime_persistent_permission_widening"])
        self.assertFalse(data["actions"]["run_wrangler"])
        self.assertFalse(data["actions"]["credential_or_secret_access"])
        self.assertFalse(data["actions"]["live"])

    def test_runtime_constants_are_fixed_and_non_generic(self):
        self.assertEqual(plan.RUNTIME_SOURCE_ROOT, "/home/andris/coloring-pages")
        self.assertEqual(plan.RUNTIME_OPERATOR_UID, 1000)
        self.assertEqual(plan.RUNTIME_OPERATOR_GID, 1000)
        self.assertEqual(plan.RUNTIME_SECRETS_STDIN, "/dev/stdin")
        self.assertEqual(plan.NPX, "/usr/bin/npx")
        self.assertNotIn("CLOUDFLARE_API_TOKEN", plan.RUNTIME_ENV)
        self.assertNotIn("CLOUDFLARE_API_KEY", plan.RUNTIME_ENV)
        self.assertEqual(plan.RUNTIME_ENV["HOME"], "/home/andris")
        self.assertEqual(
            plan.RUNTIME_ENV["XDG_CONFIG_HOME"], "/home/andris/.config"
        )

    def test_runtime_entry_requires_root_exact_installed_file(self):
        with mock.patch.object(plan.os, "geteuid", return_value=0), \
             mock.patch.object(
                 plan.Path,
                 "absolute",
                 return_value=plan.RUNTIME_ENTRY,
             ):
            plan.trusted_runtime_entry(lstat=runtime_lstat)

        with mock.patch.object(plan.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(plan.Blocked, "RUNTIME_ROOT_REQUIRED"):
                plan.trusted_runtime_entry(lstat=runtime_lstat)

    def test_runtime_entry_rejects_wrong_mode_or_parent(self):
        def wrong_entry(path):
            if path == str(plan.RUNTIME_ENTRY):
                return regular(0o755, size=20000)
            return runtime_lstat(path)

        with mock.patch.object(plan.os, "geteuid", return_value=0), \
             mock.patch.object(
                 plan.Path,
                 "absolute",
                 return_value=plan.RUNTIME_ENTRY,
             ):
            with self.assertRaisesRegex(plan.Blocked, "RUNTIME_PATH_UNTRUSTED"):
                plan.trusted_runtime_entry(lstat=wrong_entry)

        def writable_parent(path):
            if path == "/usr/local":
                return directory(0o777)
            return runtime_lstat(path)

        with mock.patch.object(plan.os, "geteuid", return_value=0), \
             mock.patch.object(
                 plan.Path,
                 "absolute",
                 return_value=plan.RUNTIME_ENTRY,
             ):
            with self.assertRaisesRegex(plan.Blocked, "RUNTIME_PATH_UNTRUSTED"):
                plan.trusted_runtime_entry(lstat=writable_parent)

    def test_root_owned_secret_metadata_is_exact(self):
        item = plan.validate_root_owned_runtime_secret(lstat=runtime_lstat)
        self.assertEqual(item.st_uid, 0)
        self.assertEqual(item.st_gid, 0)
        self.assertEqual(stat.S_IMODE(item.st_mode), 0o600)

        def wrong_owner(path):
            if path == plan.RUNTIME_SECRETS_FILE:
                return regular(uid=1000)
            return runtime_lstat(path)

        with self.assertRaisesRegex(
            plan.Blocked, "RUNTIME_SECRETS_UNPROTECTED"
        ):
            plan.validate_root_owned_runtime_secret(lstat=wrong_owner)

    def test_open_secret_rechecks_inode_without_reading_content(self):
        opened = regular()
        with mock.patch.object(plan.os, "close") as close:
            fd, size = plan.open_root_owned_runtime_secret(
                lstat=runtime_lstat,
                opener=lambda path, flags: 77,
                fstat=lambda fd: opened,
            )
        self.assertEqual(fd, 77)
        self.assertEqual(size, 249)
        close.assert_not_called()

        drifted = regular(ino=10)
        with mock.patch.object(plan.os, "close") as close:
            with self.assertRaisesRegex(
                plan.Blocked, "RUNTIME_SECRETS_OPEN_DRIFT"
            ):
                plan.open_root_owned_runtime_secret(
                    lstat=runtime_lstat,
                    opener=lambda path, flags: 77,
                    fstat=lambda fd: drifted,
                )
        close.assert_called_once_with(77)

    def test_memfd_uses_kernel_copy_and_operator_only_metadata(self):
        secret_meta = regular()
        memfd_meta = regular(
            0o400,
            uid=plan.RUNTIME_OPERATOR_UID,
            gid=plan.RUNTIME_OPERATOR_GID,
            size=249,
        )
        with mock.patch.object(plan.os, "memfd_create", return_value=88), \
             mock.patch.object(plan.os, "sendfile", return_value=249) as send, \
             mock.patch.object(plan.os, "fchown") as chown, \
             mock.patch.object(plan.os, "fchmod") as chmod, \
             mock.patch.object(plan.os, "lseek") as seek, \
             mock.patch.object(plan.os, "fstat", return_value=memfd_meta), \
             mock.patch.object(plan.fcntl, "fcntl") as seal, \
             mock.patch.object(plan.os, "close") as close:
            fd = plan.sealed_operator_secret_memfd(77, secret_meta.st_size)
        self.assertEqual(fd, 88)
        send.assert_called_once_with(88, 77, 0, 249)
        chown.assert_called_once_with(
            88, plan.RUNTIME_OPERATOR_UID, plan.RUNTIME_OPERATOR_GID
        )
        chmod.assert_called_once_with(88, 0o400)
        seek.assert_called_once_with(88, 0, plan.os.SEEK_SET)
        self.assertEqual(seal.call_count, 1)
        close.assert_not_called()

    def test_runtime_command_uses_dev_stdin_not_persistent_secret_path(self):
        command = plan.runtime_deploy_command(application())
        self.assertEqual(
            command[:4],
            ["/usr/bin/npx", "--yes", "wrangler@4.135.0", "deploy"],
        )
        self.assertIn("--secrets-file", command)
        self.assertIn("/dev/stdin", command)
        self.assertNotIn(plan.RUNTIME_SECRETS_FILE, command)
        self.assertIn("--strict", command)
        self.assertIn("--no-bundle", command)

    def test_runtime_executes_wrangler_as_fixed_operator_once(self):
        calls = []

        def runner(args, **kwargs):
            calls.append((list(args), dict(kwargs)))
            if args[-1] == "--version":
                return SimpleNamespace(
                    returncode=0, stdout="4.135.0\n", stderr=""
                )
            return SimpleNamespace(returncode=0, stdout="deployed", stderr="")

        with mock.patch.object(plan, "trusted_runtime_entry"), \
             mock.patch.object(
                 plan, "application_evidence_from_checkout",
                 return_value=application(),
             ), \
             mock.patch.object(
                 plan, "open_root_owned_runtime_secret",
                 return_value=(70, 249),
             ), \
             mock.patch.object(
                 plan, "sealed_operator_secret_memfd", return_value=71
             ), \
             mock.patch.object(plan.os, "close") as close:
            result = plan.execute_root_owned_runtime_once(runner=runner)

        self.assertEqual(
            result,
            "DEPLOY_DISPATCH_SUCCEEDED_READ_ONLY_VERIFICATION_REQUIRED",
        )
        self.assertEqual(len(calls), 2)
        for _, kwargs in calls:
            self.assertEqual(kwargs["user"], 1000)
            self.assertEqual(kwargs["group"], 1000)
            self.assertEqual(kwargs["extra_groups"], ())
            self.assertEqual(kwargs["env"], plan.RUNTIME_ENV)
            self.assertEqual(kwargs["cwd"], plan.RUNTIME_SOURCE_ROOT)
        self.assertEqual(calls[0][1]["stdin"], plan.subprocess.DEVNULL)
        self.assertEqual(calls[1][1]["stdin"], 71)
        self.assertIn("/dev/stdin", calls[1][0])
        self.assertNotIn(plan.RUNTIME_SECRETS_FILE, calls[1][0])
        self.assertEqual(close.call_args_list, [mock.call(70), mock.call(71)])

    def test_runtime_version_drift_blocks_before_secret_open(self):
        def runner(args, **kwargs):
            return SimpleNamespace(
                returncode=0, stdout="4.134.0\n", stderr=""
            )

        with mock.patch.object(plan, "trusted_runtime_entry"), \
             mock.patch.object(
                 plan, "application_evidence_from_checkout",
                 return_value=application(),
             ), \
             mock.patch.object(
                 plan, "open_root_owned_runtime_secret"
             ) as open_secret:
            with self.assertRaisesRegex(
                plan.Blocked, "WRANGLER_VERSION_DRIFT"
            ):
                plan.execute_root_owned_runtime_once(runner=runner)
        open_secret.assert_not_called()

    def test_runtime_failed_dispatch_is_terminal_and_not_retried(self):
        calls = []

        def runner(args, **kwargs):
            calls.append(list(args))
            if args[-1] == "--version":
                return SimpleNamespace(
                    returncode=0, stdout="wrangler 4.135.0\n", stderr=""
                )
            return SimpleNamespace(returncode=1, stdout="", stderr="redacted")

        with mock.patch.object(plan, "trusted_runtime_entry"), \
             mock.patch.object(
                 plan, "application_evidence_from_checkout",
                 return_value=application(),
             ), \
             mock.patch.object(
                 plan, "open_root_owned_runtime_secret",
                 return_value=(70, 249),
             ), \
             mock.patch.object(
                 plan, "sealed_operator_secret_memfd", return_value=71
             ), \
             mock.patch.object(plan.os, "close"):
            with self.assertRaisesRegex(
                plan.Blocked, "DEPLOY_DISPATCH_UNKNOWN"
            ):
                plan.execute_root_owned_runtime_once(runner=runner)
        deploys = [
            call for call in calls
            if call[:4] == [
                "/usr/bin/npx", "--yes", "wrangler@4.135.0", "deploy"
            ]
        ]
        self.assertEqual(len(deploys), 1)

    def test_repository_copy_cannot_enter_runtime_mode(self):
        with mock.patch.object(plan.os, "geteuid", return_value=1000), \
             mock.patch("builtins.print"):
            self.assertEqual(
                plan.main(
                    [
                        "--runtime-deploy",
                        "--confirm",
                        plan.RUNTIME_CONFIRM,
                    ]
                ),
                2,
            )

    def test_source_never_reads_persistent_secret_into_python(self):
        text = SOURCE.read_text("utf-8")
        self.assertIn("os.sendfile", text)
        self.assertNotIn("os.read(secret_fd", text)
        self.assertNotIn("read_text(RUNTIME_SECRETS_FILE", text)
        self.assertNotIn("open(RUNTIME_SECRETS_FILE).read", text)
        self.assertNotIn("shell=True", text)


if __name__ == "__main__":
    unittest.main()
