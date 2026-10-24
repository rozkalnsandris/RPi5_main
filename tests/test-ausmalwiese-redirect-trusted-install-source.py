#!/usr/bin/env python3
"""Offline fake-runner tests for #996 trusted Redirect Rules installer/launcher."""
from __future__ import annotations
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "scripts/install-ausmalwiese-redirect-get.py"
LAUNCH = ROOT / "scripts/ausmalwiese_redirect_trusted_launcher.py"
INVENTORY = ROOT / "scripts/ausmalwiese_redirect_inventory.py"
ADAPTER = ROOT / "scripts/ausmalwiese_redirect_get_adapter.py"
SHA = "b" * 40


def source(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(obj)
    return obj


installer = source(INSTALL, "redirect_source_install")
launcher = source(LAUNCH, "redirect_source_launcher")


class FakeRunner:
    def __init__(self, *, sha=SHA, branch="main", dirty=False, present=False,
                 parent_mode="755", fail_write=0, checksum_bad=False):
        self.sha = sha
        self.branch = branch
        self.dirty = dirty
        self.present = present
        self.parent_mode = parent_mode
        self.fail_write = fail_write
        self.checksum_bad = checksum_bad
        self.calls = []
        self.writes = 0

    def __call__(self, argv, *, input=None, stdout=None, stderr=None,
                 check=False, timeout=None):
        argv = list(argv)
        self.calls.append((argv, input))
        rc, output = 0, b""
        if argv[:3] == [installer.GIT, "-C", str(installer.SOURCE_ROOT)]:
            rest = argv[3:]
            if rest == ["rev-parse", "--show-toplevel"]:
                output = (str(installer.SOURCE_ROOT) + "\n").encode()
            elif rest == ["symbolic-ref", "--quiet", "--short", "HEAD"]:
                output = (self.branch + "\n").encode()
            elif rest == ["rev-parse", "HEAD"]:
                output = (self.sha + "\n").encode()
            elif rest[:2] == ["status", "--porcelain=v1"]:
                output = b" M file" if self.dirty else b""
            elif rest == ["remote", "get-url", "origin"]:
                output = b"https://github.com/rozkalnsandris/RPi5_main.git\n"
            elif len(rest) == 2 and rest[0] == "show" and rest[1].startswith("HEAD:"):
                path = rest[1][5:]
                if path not in installer.SOURCE_PATHS:
                    rc = 9
                else:
                    output = (ROOT / path).read_bytes()
            else:
                rc = 9
        elif argv[:3] == [installer.SUDO, "-n", installer.STAT]:
            path = argv[-1]
            if path in installer.PARENTS:
                output = f"0:0:{self.parent_mode}:directory\n".encode()
            elif path == installer.LIB:
                output = b"0:0:700:directory\n"
            elif path == installer.EXE:
                output = b"0:0:500:regular file\n"
            elif path in (installer.INV, installer.ADAPT, installer.RELEASE):
                output = b"0:0:400:regular file\n"
        elif argv[:3] == [installer.SUDO, "-n", installer.TEST]:
            rc = 0 if self.present else 1
        elif argv == [installer.SUDO, "-n", installer.TRUE]:
            pass
        elif argv[:3] == [installer.SUDO, "-n", installer.SHA256SUM]:
            path = argv[-1]
            files = {
                installer.EXE: LAUNCH.read_bytes(),
                installer.INV: INVENTORY.read_bytes(),
                installer.ADAPT: ADAPTER.read_bytes(),
                installer.RELEASE: installer.release_bytes(
                    SHA, LAUNCH.read_bytes(), INVENTORY.read_bytes(), ADAPTER.read_bytes()),
            }
            if path not in files:
                rc = 10
            else:
                digest = "0" * 64 if self.checksum_bad else hashlib.sha256(files[path]).hexdigest()
                output = (digest + "  " + path + "\n").encode()
        elif argv[:3] in ([installer.SUDO, "-n", installer.MKDIR],
                          [installer.SUDO, "-n", installer.INSTALL]):
            self.writes += 1
            if self.writes == self.fail_write:
                rc = 44
        else:
            rc = 42
        return subprocess.CompletedProcess(argv, rc, stdout=output,
                                           stderr=b"PRIVATE_ERROR_NOT_FOR_OUTPUT")


class RedirectTrustedSourceTests(unittest.TestCase):
    def with_preflight(self, runner):
        with mock.patch.object(installer.os, "geteuid", return_value=1000):
            return installer.preflight(SHA, runner=runner)

    def test_exact_checkout_and_bounded_sources(self):
        fake = FakeRunner()
        files = self.with_preflight(fake)
        self.assertEqual(len(files), 4)
        self.assertEqual(files[0], LAUNCH.read_bytes())
        self.assertEqual(files[1], INVENTORY.read_bytes())
        self.assertEqual(files[2], ADAPTER.read_bytes())
        manifest = json.loads(files[3])
        self.assertEqual(manifest["repository"], "rozkalnsandris/RPi5_main")
        self.assertEqual(manifest["source_sha"], SHA)
        self.assertEqual(manifest["zone_name"], "rozkalns.net")
        self.assertEqual(set(manifest), {"schema_version", "repository", "source_sha",
                                        "zone_name", "launcher_sha256",
                                        "inventory_sha256", "adapter_sha256"})
        self.assertEqual(fake.writes, 0)

    def test_preflight_blocks_drift_dirty_root_and_unsafe_host(self):
        for obj in (
            FakeRunner(sha="a" * 40), FakeRunner(branch="feat/test"),
            FakeRunner(dirty=True), FakeRunner(parent_mode="777"),
            FakeRunner(present=True),
        ):
            with self.subTest(obj=obj.__dict__):
                with self.assertRaises(installer.Stop):
                    self.with_preflight(obj)
                self.assertEqual(obj.writes, 0)
        with mock.patch.object(installer.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(installer.Stop, "must_be_unprivileged"):
                installer.preflight(SHA, runner=FakeRunner())

    def test_no_non_allowlisted_source_or_path(self):
        with self.assertRaisesRegex(installer.Stop, "path_scope_invalid"):
            installer.tracked("ops/contracts/private.json", runner=FakeRunner())
        self.assertEqual(installer.TARGETS, (
            "/usr/local/sbin/rpi5-ausmalwiese-redirect-get",
            "/usr/local/libexec/rpi5-ausmalwiese-redirect-get",
            "/usr/local/libexec/rpi5-ausmalwiese-redirect-get/inventory.py",
            "/usr/local/libexec/rpi5-ausmalwiese-redirect-get/adapter.py",
            "/usr/local/libexec/rpi5-ausmalwiese-redirect-get/release.json",
        ))

    def test_apply_is_fixed_five_writes_and_checksum_postcheck(self):
        fake = FakeRunner()
        with mock.patch.object(installer.os, "geteuid", return_value=1000):
            installer.apply(SHA, runner=fake)
        writes = [(argv, data) for argv, data in fake.calls if
                  argv[:3] in ([installer.SUDO, "-n", installer.MKDIR],
                               [installer.SUDO, "-n", installer.INSTALL])]
        self.assertEqual(len(writes), 5)
        self.assertEqual(fake.writes, 5)
        self.assertEqual(writes[0][0], [installer.SUDO, "-n", installer.MKDIR,
                                       "-m", "0700", "--", installer.LIB])
        self.assertEqual([v[0][-1] for v in writes[1:]],
                         [installer.EXE, installer.INV, installer.ADAPT, installer.RELEASE])
        self.assertEqual([v[0][v[0].index("-m")+1] for v in writes[1:]],
                         ["0500", "0400", "0400", "0400"])
        self.assertTrue(all(v[0][-2] == "/dev/stdin" and v[1] for v in writes[1:]))

    def test_first_write_failure_is_terminal_without_cleanup_or_retry(self):
        fake = FakeRunner(fail_write=1)
        with mock.patch.object(installer.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(installer.Stop, "post_dispatch_unknown_state"):
                installer.apply(SHA, runner=fake)
        self.assertEqual(fake.writes, 1)
        fake = FakeRunner(checksum_bad=True)
        with mock.patch.object(installer.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(installer.Stop, "post_dispatch_unknown_state"):
                installer.apply(SHA, runner=fake)
        self.assertEqual(fake.writes, 5)

    def test_cli_dry_run_and_confirm_are_inert_on_failure(self):
        with mock.patch.object(installer, "apply") as do_apply, \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            code = installer.main(["--expected-main", SHA, "--apply", "--confirm", "WRONG"])
        self.assertEqual(code, 3)
        do_apply.assert_not_called()
        self.assertIn("owner_confirmation_required", stdout.getvalue())

    def test_launcher_rejects_checkout_and_untrusted_files(self):
        with self.assertRaisesRegex(launcher.Stop, "trusted_install_required"):
            launcher.installed_sources(SHA)
        fake_metadata = json.dumps({
            "schema_version": 1, "repository": installer.REPO, "source_sha": SHA,
            "zone_name": "rozkalns.net", "launcher_sha256": hashlib.sha256(LAUNCH.read_bytes()).hexdigest(),
            "inventory_sha256": hashlib.sha256(INVENTORY.read_bytes()).hexdigest(),
            "adapter_sha256": hashlib.sha256(ADAPTER.read_bytes()).hexdigest(),
        }).encode()
        mapping = {str(launcher.ENTRY): LAUNCH.read_bytes(), str(launcher.INVENTORY): INVENTORY.read_bytes(),
                   str(launcher.ADAPTER): ADAPTER.read_bytes(), str(launcher.RELEASE): fake_metadata}
        with mock.patch.object(launcher.os, "geteuid", return_value=0), \
             mock.patch.object(launcher, "__file__", str(launcher.ENTRY)), \
             mock.patch.object(launcher, "guarded_bytes", side_effect=lambda p,m,l: mapping[str(p)]):
            self.assertEqual(launcher.installed_sources(SHA),
                             (INVENTORY.read_bytes(), ADAPTER.read_bytes()))
            mapping[str(launcher.RELEASE)] = fake_metadata.replace(SHA.encode(), b"a" * 40)
            with self.assertRaisesRegex(launcher.Stop, "release_invalid"):
                launcher.installed_sources(SHA)

    def test_launcher_sanitizes_via_mocked_installed_modules_without_network(self):
        inventory_code = b"PHASE='http_request_dynamic_redirect'\nclass InventoryBlocked(Exception): pass\n"
        adapter_code = (b"def sanitized_redirect_inventory(zone_id, in_memory_read_token):\n"
                        b"    return {'schema':'rozkalns.rpi5-main.redirect-inventory-sanitized.v1', "
                        b"'zone_name':'rozkalns.net','account_level_checked':False, "
                        b"'safe_to_apply':False, 'rule_count':2}\n")
        with mock.patch.object(launcher, "installed_sources",
                               return_value=(inventory_code, adapter_code)):
            result = launcher.run_once(SHA, "a" * 32, "T" * 32)
        self.assertEqual(result["rule_count"], 2)
        self.assertNotIn("ausmalwiese_redirect_inventory", sys.modules)
        with mock.patch.object(launcher, "installed_sources", return_value=(inventory_code, adapter_code)):
            for zone in ("b" * 31, "B" * 32, "../", None):
                with self.assertRaisesRegex(launcher.Stop, "invalid_zone_id"):
                    launcher.run_once(SHA, zone, "T" * 32)

    def test_no_ambient_credential_or_runtime_execute_in_source(self):
        for p in (INSTALL, LAUNCH):
            raw = p.read_text(encoding="utf-8")
            for forbidden in ("CLOUDFLARE_API_TOKEN", "os.environ", "getpass",
                              "/etc/rpi5-secrets", "requests.post("):
                self.assertNotIn(forbidden, raw)
        self.assertNotIn('if __name__ == "__main__"', LAUNCH.read_text())
        self.assertIn("NO-CREDENTIAL-ACCESS", (ROOT / "docs/AUSMALWIESE_REDIRECT_TRUSTED_INSTALL_V1.md").read_text())
        policy = json.loads((ROOT / "ops/contracts/ausmalwiese-redirect-get-install-v1.json").read_text())
        self.assertFalse(policy["authorized"]["install"])
        self.assertFalse(policy["authorized"]["credential_access"])
        self.assertFalse(policy["authorized"]["cloudflare_get"])
        self.assertEqual(policy["cloudflare"]["allowed_methods"], ["GET"])
        self.assertEqual(policy["installation"]["targets"], list(installer.TARGETS))


if __name__ == "__main__":
    unittest.main()
