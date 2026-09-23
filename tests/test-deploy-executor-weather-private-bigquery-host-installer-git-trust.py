#!/usr/bin/env python3
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor import weather_private_bigquery_host_installer as installer  # noqa: E402


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout.strip()


@contextmanager
def manager_fixture(*, reviewed_origin: bool = True, dirty: bool = False):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "manager-home"
        manager = home / "RPi5_main"
        source_checkout = root / "installer-trusted"
        manager.mkdir(parents=True)
        subprocess.run(["git", "init", str(manager)], check=True, stdout=subprocess.DEVNULL)
        git(manager, "config", "user.name", "fixture")
        git(manager, "config", "user.email", "fixture@example.com")
        tracked = manager / "tracked.txt"
        tracked.write_text("base\n", encoding="utf-8")
        git(manager, "add", "tracked.txt")
        git(manager, "commit", "-m", "fixture")
        git(
            manager,
            "remote",
            "add",
            "origin",
            installer.REVIEWED_ORIGIN
            if reviewed_origin
            else "https://example.invalid/wrong.git",
        )
        git(manager, "worktree", "add", "--detach", str(source_checkout), "HEAD")
        if dirty:
            tracked.write_text("dirty manager content\n", encoding="utf-8")

        old_source = installer.SOURCE_CHECKOUT
        old_getpwuid = installer.pwd.getpwuid
        uid = manager.stat().st_uid
        gid = manager.stat().st_gid
        installer.SOURCE_CHECKOUT = source_checkout
        installer.pwd.getpwuid = lambda observed_uid: (
            SimpleNamespace(
                pw_name="fixture-owner",
                pw_uid=uid,
                pw_gid=gid,
                pw_dir=str(home),
            )
            if observed_uid == uid
            else old_getpwuid(observed_uid)
        )
        try:
            yield manager
        finally:
            installer.SOURCE_CHECKOUT = old_source
            installer.pwd.getpwuid = old_getpwuid


class WeatherNextPrivateHostInstallerGitTrustTests(unittest.TestCase):
    def test_fixed_root_git_trust_is_exact_command_scoped(self):
        completed = subprocess.CompletedProcess(
            args=(),
            returncode=0,
            stdout="ok\n",
            stderr="",
        )
        for checkout in (installer.SOURCE_CHECKOUT, installer.TRUSTED_CHECKOUT):
            with self.subTest(checkout=str(checkout)):
                with mock.patch.object(
                    installer.subprocess,
                    "run",
                    return_value=completed,
                ) as run_process:
                    result = installer._run_fixed_git(
                        checkout,
                        "rev-parse",
                        "HEAD",
                    )

                self.assertEqual(result.stdout, "ok\n")
                argv = run_process.call_args.args[0]
                self.assertEqual(
                    argv[:6],
                    (
                        "/usr/bin/git",
                        "-c",
                        f"safe.directory={checkout}",
                        "--no-optional-locks",
                        "-C",
                        str(checkout),
                    ),
                )
                self.assertNotIn("safe.directory=*", argv)
                self.assertNotIn("--global", argv)
                self.assertNotIn("--system", argv)
                self.assertFalse(run_process.call_args.kwargs["shell"])

    def test_arbitrary_root_checkout_is_rejected_before_git_process(self):
        with mock.patch.object(installer.subprocess, "run") as run_process:
            with self.assertRaises(installer.WeatherNextPrivateHostInstallerError):
                installer._run_fixed_git(
                    Path("/tmp/unreviewed-checkout"),
                    "rev-parse",
                    "HEAD",
                )
        run_process.assert_not_called()

    def test_manager_resolves_from_trusted_worktree_to_repo_owner_home(self):
        self.assertEqual(
            installer.MANAGER_CHECKOUT_RESOLVER,
            "repo-owner-home/RPi5_main",
        )
        with manager_fixture() as manager:
            resolved = installer._resolve_manager_checkout()
            self.assertEqual(resolved.path, manager)
            self.assertEqual(
                installer._manager_git_success(
                    resolved,
                    "remote",
                    "get-url",
                    "origin",
                ),
                installer.REVIEWED_ORIGIN,
            )

    def test_dirty_manager_is_allowed_as_provenance_but_snapshot_is_frozen(self):
        with manager_fixture(dirty=True) as manager:
            before = (
                git(manager, "rev-parse", "HEAD"),
                git(manager, "status", "--porcelain=v1", "--untracked-files=all"),
            )
            backend = installer.PosixFixedInstallBackend()
            backend.observe("a" * 40)
            after = (
                git(manager, "rev-parse", "HEAD"),
                git(manager, "status", "--porcelain=v1", "--untracked-files=all"),
            )
            self.assertEqual(after, before)

            (manager / "later.txt").write_text("drift\n", encoding="utf-8")
            with self.assertRaisesRegex(
                installer.WeatherNextPrivateHostInstallerError,
                "manager working tree/index/HEAD changed",
            ):
                backend._require_manager_unchanged()

    def test_wrong_manager_origin_fails_during_preconsume_observation(self):
        with manager_fixture(reviewed_origin=False):
            backend = installer.PosixFixedInstallBackend()
            with self.assertRaisesRegex(
                installer.WeatherNextPrivateHostInstallerError,
                "manager checkout origin drifted",
            ):
                backend.observe("a" * 40)

    def test_manager_fetch_preserves_owner_global_credential_context_read_only(self):
        manager = installer.ManagerCheckout(
            path=Path("/home/fixture-owner/RPi5_main"),
            username="fixture-owner",
            uid=1001,
            gid=1001,
            home=Path("/home/fixture-owner"),
        )
        completed = subprocess.CompletedProcess(
            args=(),
            returncode=0,
            stdout="",
            stderr="",
        )
        with (
            mock.patch.object(installer.os, "geteuid", return_value=installer.ROOT_UID),
            mock.patch.object(installer.subprocess, "run", return_value=completed) as run_process,
        ):
            installer._run_manager_git(
                manager,
                "fetch",
                "--no-tags",
                "origin",
                "refs/heads/main:refs/remotes/origin/main",
                mutation=True,
            )

        argv = run_process.call_args.args[0]
        self.assertEqual(
            argv[:6],
            (
                "/usr/sbin/runuser",
                "-u",
                "fixture-owner",
                "--",
                "/usr/bin/env",
                "-i",
            ),
        )
        self.assertIn("GIT_CONFIG_NOSYSTEM=1", argv)
        self.assertNotIn("GIT_CONFIG_GLOBAL=/dev/null", argv)
        self.assertNotIn("config", argv)
        self.assertFalse(run_process.call_args.kwargs["shell"])

    def test_manager_git_surface_forbids_hidden_repair(self):
        source = (
            ROOT
            / "ops/lib/deploy_executor/weather_private_bigquery_host_installer.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('TRUSTED_CHECKOUT.parent / "RPi5_main"', source)
        for forbidden in (
            '"clone"',
            '"reset"',
            '"clean"',
            '"pull"',
            '"switch"',
            '"rebase"',
            "safe.directory=*",
            "git config",
        ):
            self.assertNotIn(forbidden, source)
        readiness = installer.source_readiness()
        self.assertEqual(
            readiness["manager_checkout_resolver"],
            "repo-owner-home/RPi5_main",
        )
        self.assertTrue(readiness["manager_fetch_as_repository_owner"])
        self.assertTrue(readiness["manager_worktree_add_as_root_only"])

    def test_contract_requires_boundary_refresh_before_backend_authority(self):
        value = json.loads(
            (
                ROOT
                / "ops/deploy/weather-private-bigquery-host-privileged-installer.json"
            ).read_text(encoding="utf-8")
        )
        capability = value["capability_install"]
        self.assertTrue(capability["manager_global_git_config_read_only_allowed"])
        self.assertFalse(capability["manager_git_config_mutation_allowed"])

        continuity = value["post_merge_continuity"]
        self.assertTrue(continuity["installed_privileged_installer_imports_from_trusted_checkout"])
        self.assertFalse(continuity["source_merge_updates_installed_privileged_installer"])
        self.assertFalse(continuity["initial_bootstrap_is_upgrade_path"])
        self.assertTrue(continuity["installed_boundary_exact_new_source_required_before_backend_queue"])
        self.assertEqual(continuity["boundary_mismatch_state"], "SOURCE_PREREQUISITE_REQUIRED")
        self.assertFalse(continuity["backend_ready_queue_allowed_before_boundary_rebind"])
        self.assertFalse(continuity["backend_live_auth_allowed_before_boundary_rebind"])
        self.assertEqual(
            value["next_gate_after_merge"],
            "SOURCE_PREREQUISITE_WEATHERNEXT_INSTALLER_BOUNDARY_UPGRADE_REBIND_THEN_FRESH_BACKEND_QUEUE_AND_LIVE_AUTH",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
