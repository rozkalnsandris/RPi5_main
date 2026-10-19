#!/usr/bin/env python3
"""Offline tests for #1116 installed legacy redirect write boundary."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import ausmalwiese_redirect_write_v1 as write

INSTALL_PATH = SCRIPTS / "install-ausmalwiese-redirect-write-runtime-v1.py"
RUNTIME_PATH = SCRIPTS / "ausmalwiese_redirect_write_runtime_v1.py"
PROVISION_PATH = SCRIPTS / "ausmalwiese_redirect_write_provisioner_v1.py"
CONTRACT_PATH = ROOT / "ops/contracts/ausmalwiese-redirect-write-runtime-v1.json"
SHA = "a" * 40
ZONE = "b" * 32
RULESET = "c" * 32
TOKEN = "T" * 32


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


installer = load(INSTALL_PATH, "redirect_write_runtime_installer_test")
runtime = load(RUNTIME_PATH, "redirect_write_runtime_test")
provisioner = load(PROVISION_PATH, "redirect_write_provisioner_test")


class FakeRunner:
    def __init__(self, *, dirty=False, present=False):
        self.dirty = dirty
        self.present = present
        self.calls = []

    def __call__(
        self, argv, *, input=None, stdout=None, stderr=None, check=False,
        timeout=None, env=None,
    ):
        argv = list(argv)
        self.calls.append((argv, input))
        rc, output = 0, b""
        if argv[:3] == [installer.GIT, "-C", str(installer.SOURCE_ROOT)]:
            rest = argv[3:]
            if rest == ["rev-parse", "--show-toplevel"]:
                output = (str(installer.SOURCE_ROOT) + "\n").encode()
            elif rest == ["symbolic-ref", "--quiet", "--short", "HEAD"]:
                output = b"main\n"
            elif rest == ["rev-parse", "HEAD"]:
                output = (SHA + "\n").encode()
            elif rest[:2] == ["status", "--porcelain=v1"]:
                output = b" M changed" if self.dirty else b""
            elif rest == ["remote", "get-url", "origin"]:
                output = b"https://github.com/rozkalnsandris/RPi5_main.git\n"
            elif len(rest) == 2 and rest[0] == "show" and rest[1].startswith("HEAD:"):
                rel = rest[1][5:]
                output = (ROOT / rel).read_bytes()
            else:
                rc = 91
        elif argv == [installer.SUDO, "-n", installer.TRUE]:
            pass
        elif argv[:3] == [installer.SUDO, "-n", installer.STAT]:
            output = b"0:0:755:directory\n"
        elif argv[:3] == [installer.SUDO, "-n", installer.TEST]:
            rc = 0 if self.present else 1
        else:
            rc = 92
        return subprocess.CompletedProcess(argv, rc, stdout=output, stderr=b"PRIVATE")

class FakeStat:
    st_mode = stat.S_IFDIR | 0o700
    st_uid = 0
    st_gid = 0
    st_dev = 1
    st_ino = 2


class MiniTransport:
    def __init__(self):
        self.rules = [{
            "id": "d" * 32,
            "expression": 'http.host eq "other.rozkalns.net"',
            "action": "redirect",
            "enabled": True,
        }]
        self.writes = []

    def read(self, method, path):
        prefix = f"/zones/{ZONE}"
        if path == prefix:
            return 200, {"success": True, "result": {
                "id": ZONE, "name": write.ZONE_NAME, "status": "active",
            }}
        if path == prefix + "/rulesets":
            return 200, {"success": True, "result": [{
                "id": RULESET, "kind": "zone", "phase": write.PHASE,
            }]}
        if path == prefix + f"/rulesets/phases/{write.PHASE}/entrypoint":
            return 200, {"success": True, "result": {
                "id": RULESET,
                "kind": "zone",
                "phase": write.PHASE,
                "rules": copy.deepcopy(self.rules),
            }}
        raise AssertionError(path)

    def write_once(self, method, path, payload):
        self.writes.append((method, path, copy.deepcopy(payload)))
        if len(self.writes) > 1:
            raise AssertionError("second write")
        value = copy.deepcopy(payload)
        value["id"] = "e" * 32
        self.rules.append(value)


class RuntimeBoundaryTests(unittest.TestCase):
    def test_installer_preflight_binds_exact_tracked_release_without_writes(self):
        fake = FakeRunner()
        with mock.patch.object(installer.os, "geteuid", return_value=1000):
            values = installer.preflight(SHA, runner=fake)
        self.assertEqual(len(values), 6)
        meta = json.loads(values[-1])
        self.assertEqual(meta["source_sha"], SHA)
        self.assertEqual(meta["repository"], "rozkalnsandris/RPi5_main")
        self.assertEqual(meta["zone_name"], "rozkalns.net")
        keys = {
            "launcher_sha256", "provisioner_sha256", "inventory_sha256",
            "adapter_sha256", "write_sha256",
        }
        self.assertTrue(keys.issubset(meta))
        for key, raw in zip(
            (
                "launcher_sha256", "provisioner_sha256", "inventory_sha256",
                "adapter_sha256", "write_sha256",
            ),
            values[:-1],
        ):
            self.assertEqual(meta[key], hashlib.sha256(raw).hexdigest())
        self.assertFalse(any(
            argv[:3] in (
                [installer.SUDO, "-n", installer.MKDIR],
                [installer.SUDO, "-n", installer.INSTALL],
            )
            for argv, _ in fake.calls
        ))

    def test_installer_preflight_blocks_dirty_or_existing_target(self):
        for fake, reason in (
            (FakeRunner(dirty=True), "dirty_checkout"),
            (FakeRunner(present=True), "target_already_exists"),
        ):
            with self.subTest(reason=reason),                  mock.patch.object(installer.os, "geteuid", return_value=1000):
                with self.assertRaisesRegex(installer.Stop, reason):
                    installer.preflight(SHA, runner=fake)

    def test_runtime_release_verification_pins_every_installed_byte(self):
        mapping = {
            str(runtime.ENTRY): b"launcher",
            str(runtime.PROVISIONER): b"provisioner",
            str(runtime.INVENTORY): b"inventory",
            str(runtime.ADAPTER): b"adapter",
            str(runtime.WRITE): b"write",
        }
        meta = {
            "schema_version": 1,
            "repository": runtime.REPOSITORY,
            "source_sha": SHA,
            "zone_name": runtime.ZONE_NAME,
            "launcher_sha256": hashlib.sha256(mapping[str(runtime.ENTRY)]).hexdigest(),
            "provisioner_sha256": hashlib.sha256(mapping[str(runtime.PROVISIONER)]).hexdigest(),
            "inventory_sha256": hashlib.sha256(mapping[str(runtime.INVENTORY)]).hexdigest(),
            "adapter_sha256": hashlib.sha256(mapping[str(runtime.ADAPTER)]).hexdigest(),
            "write_sha256": hashlib.sha256(mapping[str(runtime.WRITE)]).hexdigest(),
        }
        mapping[str(runtime.RELEASE)] = json.dumps(meta).encode()
        with mock.patch.object(runtime.os, "geteuid", return_value=0),              mock.patch.object(runtime, "__file__", str(runtime.ENTRY)),              mock.patch.object(
                 runtime, "guarded_bytes",
                 side_effect=lambda path, mode, maximum: mapping[str(path)],
             ):
            self.assertEqual(
                runtime.verified_install(SHA),
                (b"inventory", b"adapter", b"write"),
            )
            meta["write_sha256"] = "0" * 64
            mapping[str(runtime.RELEASE)] = json.dumps(meta).encode()
            with self.assertRaisesRegex(runtime.Stop, "release_identity_invalid"):
                runtime.verified_install(SHA)

    def test_protected_credential_shape_and_runtime_reads_file_once(self):
        raw = provisioner.credential_bytes(ZONE, TOKEN)
        obj = json.loads(raw)
        self.assertEqual(
            obj,
            {"zone_name": "rozkalns.net", "zone_id": ZONE, "api_token": TOKEN},
        )
        for bad_zone in ("B" * 32, "b" * 31, "../"):
            with self.assertRaisesRegex(provisioner.Stop, "zone_id_invalid"):
                provisioner.credential_bytes(bad_zone, TOKEN)

        secret = json.dumps(obj).encode()
        calls = []
        def read(path, mode, maximum):
            calls.append(str(path))
            self.assertEqual(path, runtime.SECRET)
            self.assertEqual(mode, 0o600)
            return secret
        with mock.patch.object(runtime, "safe_parents"),              mock.patch.object(runtime.Path, "lstat", return_value=FakeStat()),              mock.patch.object(runtime, "guarded_bytes", side_effect=read):
            self.assertEqual(runtime.credential(), (ZONE, TOKEN))
        self.assertEqual(calls, [str(runtime.SECRET)])

    def test_runtime_preflight_and_apply_cli_require_exact_confirmations(self):
        result = {
            "schema": "rozkalns.rpi5-main.redirect-write-preflight.v1",
            "zone_name": "rozkalns.net",
            "phase": "http_request_dynamic_redirect",
            "legacy_hostname": "coloring.rozkalns.net",
            "baseline_sha256": "f" * 64,
            "operation": "ADD_RULE",
            "mutation_required": True,
            "safe_to_apply": False,
        }
        with mock.patch.object(runtime, "core_call", return_value=result) as call,              mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            code = runtime.main([
                "--expected-main", SHA,
                "--preflight",
                "--confirm", runtime.PRE_CONFIRM,
            ])
        self.assertEqual(code, 0)
        call.assert_called_once_with(SHA, expected_baseline=None)
        self.assertNotIn(TOKEN, output.getvalue())

        with mock.patch.object(runtime, "core_call") as call,              mock.patch("sys.stdout", new_callable=io.StringIO):
            code = runtime.main([
                "--expected-main", SHA,
                "--apply",
                "--expected-baseline", "f" * 64,
                "--confirm", "WRONG",
            ])
        self.assertEqual(code, 3)
        call.assert_not_called()

    def test_existing_core_blocks_baseline_drift_and_keeps_one_write_budget(self):
        fake = MiniTransport()
        before = write.preflight(fake, ZONE)
        fake.rules[0]["description"] = "drift"
        with self.assertRaisesRegex(write.WriteBlocked, "BASELINE_DRIFT"):
            write.run_once(fake, ZONE, before["baseline_sha256"])
        self.assertEqual(fake.writes, [])

        fake = MiniTransport()
        before = write.preflight(fake, ZONE)
        result = write.run_once(fake, ZONE, before["baseline_sha256"])
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(fake.writes), 1)

    def test_source_has_no_ambient_credential_input_or_live_authority(self):
        runtime_source = RUNTIME_PATH.read_text(encoding="utf-8")
        provision_source = PROVISION_PATH.read_text(encoding="utf-8")
        installer_source = INSTALL_PATH.read_text(encoding="utf-8")
        self.assertNotIn("os.environ", runtime_source)
        self.assertNotIn("sys.stdin", runtime_source)
        self.assertNotIn("getpass", runtime_source)
        self.assertIn('os.open("/dev/tty"', provision_source)
        self.assertNotIn("os.environ", provision_source)
        self.assertNotIn("sys.stdin", provision_source)
        self.assertNotIn("Cloudflare request", installer_source.splitlines()[0])
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertFalse(contract["source_authorized_capabilities"]["host_install"])
        self.assertFalse(contract["source_authorized_capabilities"]["credential_read"])
        self.assertFalse(contract["source_authorized_capabilities"]["cloudflare_write"])
        self.assertEqual(contract["runtime_modes"]["apply"]["provider_writes_max"], 1)
        self.assertEqual(contract["runtime_modes"]["apply"]["retries"], 0)
        self.assertFalse(contract["runtime_modes"]["apply"]["rollback"])
        self.assertFalse(contract["runtime_modes"]["apply"]["cleanup"])


if __name__ == "__main__":
    unittest.main()
