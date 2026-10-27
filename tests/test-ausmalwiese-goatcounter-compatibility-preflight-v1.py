#!/usr/bin/env python3
"""Disconnected tests for Ausmalwiese GoatCounter compatibility preflight."""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ausmalwiese_goatcounter_compatibility_preflight_v1 as preflight  # noqa: E402


class FakeHost:
    def __init__(self):
        self.hostname = "rpi5"
        self.os_name = "Linux"
        self.arch = "aarch64"
        self.euid = 1000
        self.users: set[str] = set()
        self.groups: set[str] = set()
        self.paths: dict[Path, preflight.PathMeta] = {}
        self.parents: dict[Path, preflight.PathMeta] = {}
        self.units: dict[str, str] = {}
        self.ports: set[int] = set()
        self.calls: list[str] = []

    def identity(self):
        self.calls.append("identity")
        return self.hostname, self.os_name, self.arch, self.euid

    def user_exists(self, name):
        self.calls.append("user:" + name)
        return name in self.users

    def group_exists(self, name):
        self.calls.append("group:" + name)
        return name in self.groups

    def path_meta(self, path):
        self.calls.append("path:" + str(path))
        if path == preflight.CATALOG_PATH:
            return self.paths.get(
                path,
                preflight.PathMeta(
                    True,
                    regular=True,
                    mode=0o644,
                    size=1024,
                ),
            )
        return self.paths.get(path, preflight.PathMeta(False))

    def resolved_dir_meta(self, path):
        self.calls.append("parent:" + str(path))
        return self.parents.get(
            path,
            preflight.PathMeta(True, directory=True, mode=0o755),
        )

    def unit_load_state(self, unit):
        self.calls.append("unit:" + unit)
        return self.units.get(unit, "not-found")

    def port_occupied(self, port):
        self.calls.append("port:" + str(port))
        return port in self.ports


class CompatibilityPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.host = FakeHost()
        self._write_source_tree()

    def _write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _write_source_tree(self):
        self._write(
            "ops/contracts/ausmalwiese-goatcounter-pageview-v1.json",
            json.dumps(preflight.EXPECTED_CONTRACT, indent=2) + "\n",
        )
        self._write(
            "ops/systemd/ausmalwiese-goatcounter.service",
            "[Unit]\n"
            + "\n".join(preflight.EXPECTED_GOATCOUNTER_UNIT_LINES)
            + "\n",
        )
        self._write(
            "ops/systemd/ausmalwiese-goatcounter-pageview.service",
            "[Unit]\n"
            + "\n".join(preflight.EXPECTED_PAGEVIEW_UNIT_LINES)
            + "\n",
        )
        self._write(
            "scripts/ausmalwiese_goatcounter_pageview_adapter_v1.py",
            "from pathlib import Path\n"
            "CATALOG_PATH = Path('/srv/coloring-pages-content/public/catalog.json')\n"
            "ADAPTER_HOST = '127.0.0.1'\n"
            "ADAPTER_PORT = 9193\n"
            "GOATCOUNTER_URL = 'http://127.0.0.1:9194/api/v0/count'\n"
            "CREDENTIAL_NAME = 'goatcounter-token'\n",
        )

    def run_preflight(self):
        return preflight.run_preflight(repo_root=self.root, host=self.host)

    def assert_stop(self, code):
        with self.assertRaisesRegex(preflight.PreflightStop, "^" + code + "$"):
            self.run_preflight()

    def test_clean_absent_state_passes(self):
        self.assertEqual(self.run_preflight(), preflight.PASS)
        self.assertIn("port:9193", self.host.calls)
        self.assertIn("port:9194", self.host.calls)
        self.assertIn("unit:" + preflight.GOATCOUNTER_UNIT, self.host.calls)
        self.assertIn("unit:" + preflight.PAGEVIEW_UNIT, self.host.calls)

    def test_source_contract_drift_stops_before_host_metadata(self):
        data = dict(preflight.EXPECTED_CONTRACT)
        data["issue"] = 9999
        self._write(
            "ops/contracts/ausmalwiese-goatcounter-pageview-v1.json",
            json.dumps(data),
        )
        self.assert_stop("SOURCE_CONTRACT_DRIFT")
        self.assertEqual(self.host.calls, [])

    def test_source_unit_drift_stops_before_host_metadata(self):
        path = self.root / "ops/systemd/ausmalwiese-goatcounter.service"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "User=ausmalwiese-goatcounter",
                "User=unexpected",
            ),
            encoding="utf-8",
        )
        self.assert_stop("SOURCE_CONTRACT_DRIFT")
        self.assertEqual(self.host.calls, [])

    def test_adapter_source_drift_stops_before_host_metadata(self):
        path = self.root / "scripts/ausmalwiese_goatcounter_pageview_adapter_v1.py"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "ADAPTER_PORT = 9193",
                "ADAPTER_PORT = 9999",
            ),
            encoding="utf-8",
        )
        self.assert_stop("SOURCE_CONTRACT_DRIFT")
        self.assertEqual(self.host.calls, [])

    def test_identity_failures_are_fixed_codes(self):
        cases = (
            ("ROOT_FORBIDDEN", "euid", 0),
            ("WRONG_HOST", "hostname", "other"),
            ("WRONG_OS", "os_name", "OtherOS"),
            ("WRONG_ARCH", "arch", "x86_64"),
        )
        for code, attr, value in cases:
            with self.subTest(code=code):
                old = getattr(self.host, attr)
                setattr(self.host, attr, value)
                self.assert_stop(code)
                setattr(self.host, attr, old)

    def test_exact_user_conflicts(self):
        cases = (
            (preflight.GOATCOUNTER_USER, "USER_GOATCOUNTER_CONFLICT"),
            (preflight.PAGEVIEW_USER, "USER_PAGEVIEW_CONFLICT"),
        )
        for name, code in cases:
            with self.subTest(name=name):
                self.host.users.add(name)
                self.assert_stop(code)
                self.host.users.clear()

    def test_exact_group_conflicts(self):
        cases = (
            (preflight.GOATCOUNTER_GROUP, "GROUP_GOATCOUNTER_CONFLICT"),
            (preflight.PAGEVIEW_GROUP, "GROUP_PAGEVIEW_CONFLICT"),
        )
        for name, code in cases:
            with self.subTest(name=name):
                self.host.groups.add(name)
                self.assert_stop(code)
                self.host.groups.clear()

    def test_preexisting_target_roots_fail_closed(self):
        cases = (
            (preflight.EXEC_ROOT, "EXEC_TARGET_CONFLICT"),
            (preflight.DATA_ROOT, "DATA_TARGET_CONFLICT"),
            (preflight.CREDENTIAL_ROOT, "CREDENTIAL_TARGET_CONFLICT"),
        )
        for path, code in cases:
            with self.subTest(path=path):
                self.host.paths[path] = preflight.PathMeta(
                    True, directory=True, mode=0o700
                )
                self.assert_stop(code)
                self.host.paths.clear()

    def test_exact_unit_name_conflicts(self):
        cases = (
            (preflight.GOATCOUNTER_UNIT, "UNIT_GOATCOUNTER_CONFLICT"),
            (preflight.PAGEVIEW_UNIT, "UNIT_PAGEVIEW_CONFLICT"),
        )
        for unit, code in cases:
            with self.subTest(unit=unit):
                self.host.units[unit] = "loaded"
                self.assert_stop(code)
                self.host.units.clear()

    def test_exact_ports_conflict_without_pid_data(self):
        for port, code in (
            (9193, "PORT_9193_CONFLICT"),
            (9194, "PORT_9194_CONFLICT"),
        ):
            with self.subTest(port=port):
                self.host.ports.add(port)
                self.assert_stop(code)
                self.host.ports.clear()

    def test_catalog_missing_symlink_type_size_and_mode_failures(self):
        cases = (
            (preflight.PathMeta(False), "CATALOG_UNAVAILABLE"),
            (
                preflight.PathMeta(
                    True, symlink=True, regular=False, mode=0o777, size=10
                ),
                "CATALOG_SYMLINK",
            ),
            (
                preflight.PathMeta(True, directory=True, mode=0o755, size=10),
                "CATALOG_TYPE",
            ),
            (
                preflight.PathMeta(True, regular=True, mode=0o644, size=0),
                "CATALOG_SIZE",
            ),
            (
                preflight.PathMeta(
                    True,
                    regular=True,
                    mode=0o644,
                    size=preflight.MAX_CATALOG_BYTES + 1,
                ),
                "CATALOG_SIZE",
            ),
            (
                preflight.PathMeta(True, regular=True, mode=0o640, size=10),
                "CATALOG_MODE",
            ),
            (
                preflight.PathMeta(True, regular=True, mode=0o646, size=10),
                "CATALOG_MODE",
            ),
        )
        for meta, code in cases:
            with self.subTest(code=code, meta=meta):
                self.host.paths[preflight.CATALOG_PATH] = meta
                self.assert_stop(code)
                self.host.paths.clear()

    def test_catalog_parent_traversal_metadata_failures(self):
        parent = preflight.CATALOG_PARENTS[-1]
        cases = (
            (preflight.PathMeta(False), "CATALOG_PARENT_UNAVAILABLE"),
            (
                preflight.PathMeta(True, regular=True, mode=0o755),
                "CATALOG_PARENT_TYPE",
            ),
            (
                preflight.PathMeta(True, directory=True, mode=0o750),
                "CATALOG_PARENT_MODE",
            ),
        )
        for meta, code in cases:
            with self.subTest(code=code):
                self.host.parents[parent] = meta
                self.assert_stop(code)
                self.host.parents.clear()

    def test_operator_safe_code_collapses_unknown_detail(self):
        private = "private-value:/etc/secret"
        code = preflight.operator_safe_code(preflight.PreflightStop(private))
        self.assertEqual(code, preflight.FALLBACK_STOP)
        self.assertNotIn(private, code)

    def test_main_output_never_emits_unknown_exception_detail(self):
        private = "private-value:/etc/secret"
        stream = io.StringIO()
        with mock.patch.object(
            preflight,
            "run_preflight",
            side_effect=preflight.PreflightStop(private),
        ), contextlib.redirect_stdout(stream):
            status = preflight.main()
        self.assertEqual(status, 2)
        self.assertEqual(
            stream.getvalue().strip(),
            "GOATCOUNTER_COMPATIBILITY=STOP CODE=PREFLIGHT_INTERNAL",
        )
        self.assertNotIn(private, stream.getvalue())

    def test_real_port_probe_uses_only_exact_filtered_ss_without_processes(self):
        cp = subprocess.CompletedProcess(
            [preflight.SS],
            0,
            stdout="",
            stderr="private-ignored",
        )
        with mock.patch.object(preflight.subprocess, "run", return_value=cp) as run:
            self.assertFalse(preflight.RealHostMetadata().port_occupied(9193))
        argv = run.call_args.args[0]
        self.assertEqual(
            argv,
            [preflight.SS, "-H", "-ltn", "sport = :9193"],
        )
        self.assertNotIn("-p", argv)

    def test_real_port_probe_treats_any_exact_listener_as_conflict(self):
        cp = subprocess.CompletedProcess(
            [preflight.SS],
            0,
            stdout="LISTEN 0 128 127.0.0.1:9194 0.0.0.0:*\n",
            stderr="",
        )
        with mock.patch.object(preflight.subprocess, "run", return_value=cp):
            self.assertTrue(preflight.RealHostMetadata().port_occupied(9194))

    def test_real_unit_probe_reads_only_load_state_metadata(self):
        cp = subprocess.CompletedProcess(
            [preflight.SYSTEMCTL],
            0,
            stdout="not-found\n",
            stderr="private-ignored",
        )
        with mock.patch.object(preflight.subprocess, "run", return_value=cp) as run:
            state = preflight.RealHostMetadata().unit_load_state(
                preflight.GOATCOUNTER_UNIT
            )
        self.assertEqual(state, "not-found")
        argv = run.call_args.args[0]
        self.assertEqual(
            argv,
            [
                preflight.SYSTEMCTL,
                "show",
                "--property=LoadState",
                "--value",
                preflight.GOATCOUNTER_UNIT,
            ],
        )
        self.assertNotIn("cat", argv)

    def test_real_tool_failures_are_sanitized(self):
        with mock.patch.object(
            preflight.subprocess,
            "run",
            side_effect=OSError("private tool detail"),
        ):
            with self.assertRaisesRegex(
                preflight.PreflightStop, "^PORT_CHECK_UNAVAILABLE$"
            ):
                preflight.RealHostMetadata().port_occupied(9193)
            with self.assertRaisesRegex(
                preflight.PreflightStop, "^UNIT_CHECK_UNAVAILABLE$"
            ):
                preflight.RealHostMetadata().unit_load_state(
                    preflight.GOATCOUNTER_UNIT
                )


if __name__ == "__main__":
    unittest.main()
