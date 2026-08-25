#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops/bin/balkons-bot-deploy-verifier"
SOURCE_PATH = ROOT / "ops/lib/balkons-bot.py"
OVERLAY_PATH = ROOT / "ops/systemd/balkons-bot-runtime-override.conf"
PREFLIGHT_PATH = ROOT / "ops/bin/balkons-bot-preflight"

loader = importlib.machinery.SourceFileLoader("balkons_bot_deploy_verifier", str(MODULE_PATH))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
verifier = importlib.util.module_from_spec(spec)
loader.exec_module(verifier)

REPO_SHA = "a" * 40
BASELINE_PATH_SHA = "3" * 64
FRAGMENT_SHA = "4" * 64
USER_SHA = "5" * 64
K10_BYTES = b"[Service]\nSendSIGKILL=no\n"
K10_SHA = hashlib.sha256(K10_BYTES).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class FakeRunner:
    def __init__(
        self,
        *,
        repo: Path,
        restart: str = verifier.BASELINE_RESTART,
        mainpid: int = 4242,
    ) -> None:
        self.repo = repo
        self.restart = restart
        self.mainpid = mainpid
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command):
        command = tuple(command)
        self.commands.append(command)
        if command == verifier.build_git_head_command(self.repo):
            return verifier.CommandResult(0, REPO_SHA + "\n")
        if command == verifier.build_git_branch_command(self.repo):
            return verifier.CommandResult(0, "main\n")
        if command == verifier.build_git_status_command(self.repo):
            return verifier.CommandResult(0, "")
        if command == verifier.build_git_tracked_command(self.repo):
            payload = "".join(
                f"100644 {'d' * 40} 0\t{path}\n"
                for path in (
                    verifier.SELF_REL,
                    verifier.SOURCE_REL,
                    verifier.DROPIN_REL,
                    verifier.PREFLIGHT_REL,
                )
            )
            return verifier.CommandResult(0, payload)
        if command and command[0] == str(self.repo / verifier.PREFLIGHT_REL):
            expected_live_sha = command[-1]
            live_path_sha = (
                BASELINE_PATH_SHA
                if expected_live_sha == verifier.CANONICAL_H3_LIVE_SOURCE_SHA256
                else verifier.sha256_text(str(verifier.SOURCE_TARGET))
            )
            report = {
                "schema": "rpi5.balkons_bot_preflight.v1",
                "scope": "READ_ONLY",
                "service": verifier.SERVICE,
                "expected_repo_sha": REPO_SHA,
                "observed_repo_sha": REPO_SHA,
                "live_source_sha256": expected_live_sha,
                "live_source_provenance_match": True,
                "critical_worktree_clean": True,
                "critical_paths_tracked": True,
                "service_metadata": {
                    "load_state": "loaded",
                    "active_state": "active",
                    "sub_state": "running",
                    "user_sha256": USER_SHA,
                    "user_is_root": False,
                    "python_executable_path_sha256": verifier.CANONICAL_PYTHON_PATH_SHA256,
                    "live_source_path_sha256": live_path_sha,
                    "fragment_path_sha256": FRAGMENT_SHA,
                    "restart": self.restart,
                    "restart_usec": verifier.BASELINE_RESTART_USEC,
                    "timeout_stop_usec": verifier.BASELINE_TIMEOUT_STOP_USEC,
                    "send_sigkill": "no",
                },
                "paho": {"version": "1.6.1", "callback_api_class": "legacy"},
                "blockers": [],
                "preflight": "PASS",
                "mutation_started": False,
                "writes_performed": False,
            }
            return verifier.CommandResult(0, json.dumps(report))
        if command == verifier.build_mainpid_command():
            return verifier.CommandResult(0, f"MainPID={self.mainpid}\n")
        raise AssertionError(f"unexpected command: {command}")


@unittest.skipIf(os.geteuid() == 0, "deployment verifier is intentionally non-root")
class BalkonsBotDeployVerifierTests(unittest.TestCase):
    def make_fixture(self):
        temporary = tempfile.TemporaryDirectory(prefix="balkons-bot-deploy-")
        self.addCleanup(temporary.cleanup)
        work = Path(temporary.name)
        repo = work / "repo"
        fake_root = work / "root"

        copies = {
            verifier.SELF_REL: MODULE_PATH.read_bytes(),
            verifier.SOURCE_REL: SOURCE_PATH.read_bytes(),
            verifier.DROPIN_REL: OVERLAY_PATH.read_bytes(),
            verifier.PREFLIGHT_REL: PREFLIGHT_PATH.read_bytes(),
        }
        for rel, data in copies.items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        k10 = verifier.map_absolute(verifier.K10_DROPIN_TARGET, fake_root)
        k10.parent.mkdir(parents=True, exist_ok=True)
        k10.write_bytes(K10_BYTES)
        k10.chmod(0o644)

        hashes = {
            "verifier": sha256_bytes(copies[verifier.SELF_REL]),
            "source": sha256_bytes(copies[verifier.SOURCE_REL]),
            "dropin": sha256_bytes(copies[verifier.DROPIN_REL]),
            "preflight": sha256_bytes(copies[verifier.PREFLIGHT_REL]),
        }
        runner = FakeRunner(repo=repo)
        kwargs = {
            "expected_repo_sha": REPO_SHA,
            "expected_checkout_fingerprint": verifier.sha256_text(str(repo.resolve())),
            "expected_verifier_sha256": hashes["verifier"],
            "expected_source_sha256": hashes["source"],
            "expected_dropin_sha256": hashes["dropin"],
            "expected_preflight_sha256": hashes["preflight"],
            "expected_k10_dropin_sha256": K10_SHA,
            "expected_baseline_live_path_sha256": BASELINE_PATH_SHA,
            "expected_fragment_path_sha256": FRAGMENT_SHA,
            "expected_user_sha256": USER_SHA,
            "repo_root": repo,
            "runner": runner,
            "root_prefix": fake_root,
            "effective_uid": os.geteuid(),
            "expected_root_owner_uid": os.geteuid(),
        }
        return repo, fake_root, runner, hashes, kwargs

    def test_check_accepts_exact_k10_baseline_and_absent_forward_targets(self):
        _repo, _fake_root, _runner, _hashes, kwargs = self.make_fixture()
        report = verifier.collect(mode="check", **kwargs)
        self.assertEqual(report["result"], "READY")
        self.assertFalse(report["credential_content_read"])
        self.assertFalse(report["mutation_started"])
        self.assertFalse(report["writes_performed"])
        self.assertEqual(report["preflight"]["live_source_sha256"], verifier.CANONICAL_H3_LIVE_SOURCE_SHA256)

    def test_check_blocks_if_forward_source_target_already_exists(self):
        _repo, fake_root, _runner, _hashes, kwargs = self.make_fixture()
        target = verifier.map_absolute(verifier.SOURCE_TARGET, fake_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("unexpected preexisting target\n", encoding="utf-8")
        with self.assertRaises(verifier.DeployVerifyError) as caught:
            verifier.collect(mode="check", **kwargs)
        self.assertEqual(caught.exception.code, "deploy_source_target_already_exists")

    def test_verify_accepts_exact_targets_preflight_and_two_argument_process(self):
        _repo, fake_root, _runner, hashes, kwargs = self.make_fixture()
        source_target = verifier.map_absolute(verifier.SOURCE_TARGET, fake_root)
        dropin_target = verifier.map_absolute(verifier.DROPIN_TARGET, fake_root)
        source_target.parent.mkdir(parents=True, exist_ok=True)
        dropin_target.parent.mkdir(parents=True, exist_ok=True)
        source_target.write_bytes(SOURCE_PATH.read_bytes())
        dropin_target.write_bytes(OVERLAY_PATH.read_bytes())
        source_target.chmod(0o644)
        dropin_target.chmod(0o644)

        argv = b"/usr/bin/python3\0/usr/local/lib/rpi5-balkons-bot.py\0"
        report = verifier.collect(
            mode="verify",
            argv_reader=lambda _pid: argv,
            **kwargs,
        )
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["process_argv_shape"], "exact_python_and_deployed_source_only")
        self.assertEqual(report["preflight"]["live_source_sha256"], hashes["source"])
        self.assertFalse(report["credential_content_read"])

    def test_verify_rejects_extra_argv_without_disclosing_it(self):
        _repo, fake_root, _runner, _hashes, kwargs = self.make_fixture()
        source_target = verifier.map_absolute(verifier.SOURCE_TARGET, fake_root)
        dropin_target = verifier.map_absolute(verifier.DROPIN_TARGET, fake_root)
        source_target.parent.mkdir(parents=True, exist_ok=True)
        dropin_target.parent.mkdir(parents=True, exist_ok=True)
        source_target.write_bytes(SOURCE_PATH.read_bytes())
        dropin_target.write_bytes(OVERLAY_PATH.read_bytes())
        source_target.chmod(0o644)
        dropin_target.chmod(0o644)

        secret_probe = "DO_NOT_DISCLOSE_SECRET_ARG"
        argv = (
            b"/usr/bin/python3\0/usr/local/lib/rpi5-balkons-bot.py\0"
            + secret_probe.encode("utf-8")
            + b"\0"
        )
        with self.assertRaises(verifier.DeployVerifyError) as caught:
            verifier.collect(mode="verify", argv_reader=lambda _pid: argv, **kwargs)
        self.assertEqual(caught.exception.code, "process_argv_shape_invalid")
        self.assertNotIn(secret_probe, str(caught.exception))

    def test_lifecycle_drift_blocks(self):
        repo, _fake_root, runner, _hashes, kwargs = self.make_fixture()
        drifted = FakeRunner(repo=repo, restart="on-failure")
        kwargs["runner"] = drifted
        with self.assertRaises(verifier.DeployVerifyError) as caught:
            verifier.collect(mode="check", **kwargs)
        self.assertEqual(caught.exception.code, "preflight_metadata_restart_mismatch")
        self.assertNotEqual(runner, drifted)

    def test_verifier_has_no_mutating_or_secret_read_surface(self):
        text = MODULE_PATH.read_text(encoding="utf-8")
        forbidden = (
            "sudo",
            "daemon-reload",
            "systemctl restart",
            "systemctl stop",
            "systemctl start",
            "systemctl kill",
            "journalctl",
            "docker inspect",
            "/proc/*/environ",
            "CREDENTIALS_DIRECTORY",
            "/etc/credstore",
            "write_text(",
            "write_bytes(",
            ".unlink(",
            "os.remove(",
            "os.chmod(",
            "os.chown(",
        )
        for token in forbidden:
            self.assertNotIn(token, text)
        self.assertIn("/proc/{pid}/cmdline", text)
        self.assertIn('"systemctl",\n        "show"', text)

    def test_runtime_overlay_is_exact_scoped_contract(self):
        text = OVERLAY_PATH.read_text(encoding="utf-8")
        lines = text.splitlines()
        self.assertEqual(lines.count("ExecStart="), 1)
        self.assertIn("ExecStart=/usr/bin/python3 /usr/local/lib/rpi5-balkons-bot.py", lines)
        self.assertEqual(lines.count("LoadCredential="), 1)
        expected_credentials = {
            "LoadCredential=telegram-token:/etc/credstore/balkons-bot-telegram-token",
            "LoadCredential=telegram-chat-id:/etc/credstore/balkons-bot-telegram-chat-id",
            "LoadCredential=mqtt-host:/etc/credstore/balkons-bot-mqtt-host",
            "LoadCredential=mqtt-username:/etc/credstore/balkons-bot-mqtt-username",
            "LoadCredential=mqtt-secret:/etc/credstore/balkons-bot-mqtt-secret",
        }
        self.assertEqual({line for line in lines if line.startswith("LoadCredential=") and line != "LoadCredential="}, expected_credentials)
        for required in (
            "SendSIGKILL=no",
            "UMask=0077",
            "NoNewPrivileges=yes",
            "PrivateTmp=yes",
            "PrivateDevices=yes",
            "ProtectSystem=strict",
            "ProtectHome=read-only",
            "ProtectKernelTunables=yes",
            "ProtectKernelModules=yes",
            "ProtectControlGroups=yes",
            "RestrictSUIDSGID=yes",
            "LockPersonality=yes",
            "MemoryDenyWriteExecute=yes",
            "RestrictRealtime=yes",
            "RestrictNamespaces=yes",
            "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
            "CapabilityBoundingSet=",
            "AmbientCapabilities=",
        ):
            self.assertIn(required, lines)
        self.assertNotIn("User=", text)
        self.assertNotIn("Restart=", text)
        self.assertNotIn("RestartSec=", text)
        self.assertNotIn("TimeoutStopSec=", text)
        self.assertNotIn("@", text)


if __name__ == "__main__":
    unittest.main()
