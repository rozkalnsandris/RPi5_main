#!/usr/bin/env python3
from __future__ import annotations

from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone
import importlib.util
from importlib.machinery import SourceFileLoader
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "ops/lib/deploy_executor/weather_v9_predecessor_bootstrap_privileged.py"
BROKER = ROOT / "ops/bin/rozkalns-weather-v9-predecessor-bootstrap-broker"
INSTALLER = ROOT / "scripts/install-weather-v9-predecessor-bootstrap-capability.py"
SOCKET = ROOT / "ops/systemd/rozkalns-weather-v9-predecessor-bootstrap.socket"
SERVICE = ROOT / "ops/systemd/rozkalns-weather-v9-predecessor-bootstrap@.service"
CONTRACT = ROOT / "ops/deploy/weather-v9-predecessor-bootstrap-privileged-capability.json"

def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, str(path)))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

core = load(CORE, "weather_v9_predecessor_bootstrap_privileged_test")

def registration() -> object:
    return core.Registration(
        source_sha="5" * 40,
        source_checkout=Path("/srv/fixture/RPi5_main-weather-v9-predecessor-bootstrap-test"),
        manager_checkout=Path("/srv/fixture/RPi5_main"),
        manager_uid=1000,
        manager_gid=1000,
        release_files={name: "a" * 64 for name in core.RELEASE_FILES},
        socket_sha256="b" * 64,
        service_sha256="c" * 64,
    )

def auth_body(reg) -> str:
    payload = {
        "schema": core.AUTH_SCHEMA,
        "operation": core.APPLY_OPERATION,
        "target_alias": core.TARGET_ALIAS,
        "source_sha": reg.source_sha,
        "predecessor_sha": core.PREDECESSOR_SHA,
        "host": "rpi5",
        "live_authorized": True,
        "no_retry": True,
        "no_cleanup": True,
        "no_rollback": True,
    }
    return f"{core.AUTH_START}\n{json.dumps(payload, sort_keys=True, separators=(',', ':'))}\n{core.AUTH_END}"

def fetched(issue_number: int, reg, *, age: int = 0, issue_id: int = 9001):
    now = datetime(2026, 9, 19, 12, 0, 0, tzinfo=timezone.utc)
    return core.FetchedIssue(
        {
            "id": issue_id,
            "number": issue_number,
            "state": "open",
            "title": core.AUTH_TITLE,
            "user": {"id": core.OWNER_NUMERIC_ID, "type": "User"},
            "performed_via_github_app": None,
            "body": auth_body(reg),
            "created_at": (now - timedelta(seconds=age)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        now,
    )

class FakeRuntime:
    def __init__(self):
        self.preflight_calls = 0
        self.apply_calls = []

    def preflight(self):
        self.preflight_calls += 1
        return {
            "result": "PASS",
            "execution_source_sha": "5" * 40,
            "registration_source_sha": core.PREDECESSOR_SHA,
            "host_mutation_started": False,
        }

    def apply(self, issue_number):
        self.apply_calls.append(issue_number)
        return {
            "result": "PASS",
            "execution_source_sha": "5" * 40,
            "registration_source_sha": core.PREDECESSOR_SHA,
            "host_mutation_started": True,
        }

class Tests(unittest.TestCase):
    def frame(self, value):
        return (json.dumps(value, separators=(",", ":")) + "\n").encode()

    def test_request_surface_is_strict(self):
        pre = core.parse_request(self.frame({"schema": core.REQUEST_SCHEMA, "operation": "preflight"}))
        self.assertEqual((pre.operation, pre.authorization_issue_number), ("preflight", None))
        app = core.parse_request(self.frame({
            "schema": core.REQUEST_SCHEMA, "operation": "apply", "authorization_issue_number": 628
        }))
        self.assertEqual((app.operation, app.authorization_issue_number), ("apply", 628))
        bad = [
            b'{"schema":"%s","operation":"preflight","path":"/tmp/x"}\n' % core.REQUEST_SCHEMA.encode(),
            b'{"schema":"%s","operation":"shell"}\n' % core.REQUEST_SCHEMA.encode(),
            b'{"schema":"%s","operation":"preflight","operation":"preflight"}\n' % core.REQUEST_SCHEMA.encode(),
            b'{}\r\n',
            b'{}\x00\n',
            b'x' * (core.REQUEST_MAX_BYTES + 1),
        ]
        for raw in bad:
            with self.assertRaises(core.BootstrapPrivilegedError):
                core.parse_request(raw)

    def test_preflight_never_calls_apply(self):
        runtime = FakeRuntime()
        receipt = core.execute_request(
            self.frame({"schema": core.REQUEST_SCHEMA, "operation": "preflight"}), runtime=runtime
        )
        self.assertEqual(runtime.preflight_calls, 1)
        self.assertEqual(runtime.apply_calls, [])
        self.assertFalse(receipt["host_mutation_started"])

    def test_apply_caller_only_supplies_issue_identity(self):
        runtime = FakeRuntime()
        receipt = core.execute_request(
            self.frame({
                "schema": core.REQUEST_SCHEMA,
                "operation": "apply",
                "authorization_issue_number": 777,
            }),
            runtime=runtime,
        )
        self.assertEqual(runtime.apply_calls, [777])
        self.assertTrue(receipt["host_mutation_started"])

    def test_authorization_exact_ttl_and_owner(self):
        reg = registration()
        value = fetched(77, reg)
        digest = core.validate_authorization(value, issue_number=77, registration=reg)
        self.assertEqual(len(digest), 64)
        with self.assertRaises(core.BootstrapPrivilegedError):
            core.validate_authorization(fetched(77, reg, age=601), issue_number=77, registration=reg)
        wrong = fetched(77, reg)
        changed = dict(wrong.value)
        changed["user"] = {"id": 1, "type": "User"}
        with self.assertRaises(core.BootstrapPrivilegedError):
            core.validate_authorization(core.FetchedIssue(changed, wrong.server_time), issue_number=77, registration=reg)
        app = fetched(77, reg)
        app_changed = dict(app.value)
        app_changed["performed_via_github_app"] = {"id": 123}
        with self.assertRaises(core.BootstrapPrivilegedError):
            core.validate_authorization(core.FetchedIssue(app_changed, app.server_time), issue_number=77, registration=reg)

        # TTL is bound to issue creation, not mutable updated_at metadata.
        stale = fetched(77, reg, age=601)
        stale_changed = dict(stale.value)
        stale_changed["updated_at"] = stale.server_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.assertRaises(core.BootstrapPrivilegedError):
            core.validate_authorization(core.FetchedIssue(stale_changed, stale.server_time), issue_number=77, registration=reg)

    def test_double_fetch_must_be_identical(self):
        reg = registration()
        first = fetched(81, reg, issue_id=1)
        second = fetched(81, reg, issue_id=2)
        queue = [first, second]
        with self.assertRaises(core.BootstrapPrivilegedError):
            core.revalidate_authorization(81, reg, fetcher=lambda _n: queue.pop(0))

    def test_consumption_is_exclusive_and_non_reusable(self):
        reg = registration()
        issue = fetched(91, reg).value
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "consumed.json"
            core.consume_authorization(
                issue,
                "d" * 64,
                reg,
                replay_path=path,
                chown_fn=lambda *_: None,
                chmod_fn=lambda p, mode: p.chmod(mode),
            )
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(core.BootstrapPrivilegedError):
                core.consume_authorization(
                    issue,
                    "d" * 64,
                    reg,
                    replay_path=path,
                    chown_fn=lambda *_: None,
                    chmod_fn=lambda p, mode: p.chmod(mode),
                )

    def test_apply_failure_after_consume_cannot_be_reused(self):
        reg = registration()
        issue_number = 101
        item = fetched(issue_number, reg)
        original = core._recovery_and_adapter
        class FailingRecovery:
            def apply(self):
                raise RuntimeError("synthetic failure after consume")
        core._recovery_and_adapter = lambda _reg: (FailingRecovery(), object())
        try:
            with tempfile.TemporaryDirectory() as td:
                path = Path(td) / "consumed.json"
                original_consume = core.consume_authorization
                core.consume_authorization = lambda issue, body, reg2, replay_path=core.REPLAY_PATH: original_consume(
                    issue, body, reg2, replay_path=path,
                    chown_fn=lambda *_: None,
                    chmod_fn=lambda p, mode: p.chmod(mode),
                )
                try:
                    with self.assertRaises(core.BootstrapPrivilegedError):
                        core.run_apply(reg, issue_number, fetcher=lambda _n: item, replay_path=path)
                    self.assertTrue(path.exists())
                    with self.assertRaises(core.BootstrapPrivilegedError):
                        core.run_apply(reg, issue_number, fetcher=lambda _n: item, replay_path=path)
                finally:
                    core.consume_authorization = original_consume
        finally:
            core._recovery_and_adapter = original

    def test_manager_git_drops_identity_and_has_no_shell(self):
        reg = registration()
        class Installer:
            def render_service_unit(self, data, manager):
                return data
        adapter = core.ManagerGitAdapter(reg, Installer())
        calls = []
        original = core.subprocess.run
        def fake(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, stdout=reg.source_sha + "\n", stderr="")
        core.subprocess.run = fake
        try:
            adapter._run(reg.source_checkout, ("rev-parse", "HEAD"))
        finally:
            core.subprocess.run = original
        _argv, kwargs = calls[0]
        self.assertEqual(kwargs["user"], reg.manager_uid)
        self.assertEqual(kwargs["group"], reg.manager_gid)
        self.assertEqual(kwargs["extra_groups"], ())
        self.assertIs(kwargs["shell"], False)
        with self.assertRaises(core.BootstrapPrivilegedError):
            adapter._run(reg.source_checkout, ("reset", "--hard", "HEAD"))

    def test_broker_rejects_non_root(self):
        broker = load(BROKER, "weather_v9_predecessor_bootstrap_broker_test")
        old = broker.os.geteuid
        broker.os.geteuid = lambda: 1000
        old_argv = broker.sys.argv
        broker.sys.argv = [str(BROKER)]
        try:
            with redirect_stderr(io.StringIO()):
                self.assertEqual(broker.main(), 77)
        finally:
            broker.os.geteuid = old
            broker.sys.argv = old_argv

    def test_systemd_and_installer_are_narrow(self):
        socket = SOCKET.read_text()
        service = SERVICE.read_text()
        installer = INSTALLER.read_text()
        core_source = CORE.read_text()
        self.assertIn("SocketMode=0600", socket)
        self.assertIn("SocketUser=andris", socket)
        self.assertIn("Accept=yes", socket)
        self.assertIn("Type=oneshot", service)
        self.assertIn("User=root", service)
        self.assertIn("StandardInput=socket", service)
        self.assertIn("NoNewPrivileges=yes", service)
        self.assertIn("ProtectSystem=strict", service)
        self.assertIn("ProtectHome=read-only", service)
        self.assertIn("CapabilityBoundingSet=CAP_CHOWN CAP_SETUID CAP_SETGID", service)
        for allowed in (
            "/etc/rozkalns-weather-operator-v9-capability",
            "/var/lib/rozkalns-weather-operator-v9-capability",
            "/var/lib/rozkalns-weather-v9-predecessor-bootstrap",
        ):
            self.assertIn("ReadWritePaths=" + allowed, service)
        for source in (installer, core_source):
            self.assertNotIn("shell=True", source)
            self.assertNotIn("/usr/bin/sudo", source)
            self.assertNotIn("systemctl", installer)

    def test_contract_and_readiness_deny_generic_authority(self):
        contract = json.loads(CONTRACT.read_text())
        self.assertEqual(contract["issue"], 628)
        self.assertFalse(contract["preflight_requires_live_authorization"])
        self.assertTrue(contract["apply_requires_live_authorization"])
        self.assertFalse(contract["installation_activates_systemd"])
        self.assertFalse(contract["source_merge_authorizes_live"])
        self.assertEqual(contract["protect_system"], "strict")
        core_source = CORE.read_text()
        for invariant in (
            "_root_dir(CAPABILITY_ROOT, 0o755)",
            "_root_dir(RELEASE_ROOT, 0o755)",
            "_root_dir(REGISTRATION_PATH.parent, 0o700)",
            "_root_dir(REPLAY_ROOT, 0o700)",
        ):
            self.assertIn(invariant, core_source)
        ready = core.source_readiness()
        for field in (
            "caller_command_allowed", "caller_path_allowed", "caller_argv_allowed",
            "caller_environment_allowed", "caller_identity_allowed",
            "caller_hash_or_sha_allowed", "caller_target_allowed",
            "generic_shell_allowed", "generic_sudo_allowed",
        ):
            self.assertIs(ready[field], False)

if __name__ == "__main__":
    unittest.main()
