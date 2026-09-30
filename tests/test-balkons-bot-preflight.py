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
MODULE_PATH = ROOT / "ops/bin/balkons-bot-preflight"
OVERLAY_PATH = ROOT / "ops/systemd/balkons-bot-runtime-override.conf"

loader = importlib.machinery.SourceFileLoader("balkons_bot_preflight", str(MODULE_PATH))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
preflight = importlib.util.module_from_spec(spec)
loader.exec_module(preflight)
REPO_SHA = "a" * 40


class FakeRunner:
    def __init__(self, *, repo_sha: str = REPO_SHA, dirty: bool = False, send_sigkill: str = "no",
                 active_state: str = "active", sub_state: str = "running",
                 exec_start: str | None = None, live_source: Path) -> None:
        self.repo_sha = repo_sha
        self.dirty = dirty
        self.send_sigkill = send_sigkill
        self.active_state = active_state
        self.sub_state = sub_state
        self.live_source = live_source
        self.exec_start = exec_start or (
            "{ path=/usr/bin/python3 ; " f"argv[]=/usr/bin/python3 {live_source} ; "
            "ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        )
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command):
        command = tuple(command)
        self.commands.append(command)
        if command[:4] == ("git", "-C", str(ROOT), "rev-parse"):
            raise AssertionError("tests must use temp repo root")
        if command[0] == "git" and command[3:5] == ("rev-parse", "HEAD"):
            return preflight.CommandResult(0, self.repo_sha + "\n")
        if command[0] == "git" and command[3] == "status":
            return preflight.CommandResult(0, " M ops/lib/balkons-bot.py\n" if self.dirty else "")
        if command[0] == "git" and command[3:5] == ("ls-files", "--stage"):
            payload = "".join(f"100644 {'d' * 40} 0\t{path}\n" for path in preflight.CRITICAL_RELS)
            return preflight.CommandResult(0, payload)
        if command[:3] == ("systemctl", "show", preflight.SERVICE):
            payload = "\n".join([
                "LoadState=loaded", f"ActiveState={self.active_state}", f"SubState={self.sub_state}",
                "User=svc-private-user", f"ExecStart={self.exec_start}", "Restart=on-failure",
                "RestartUSec=3s", "TimeoutStopUSec=45s", f"SendSIGKILL={self.send_sigkill}",
                "FragmentPath=/private/systemd/balkons-bot.service",
            ])
            return preflight.CommandResult(0, payload + "\n")
        if command[0] == "/usr/bin/python3" and command[1:3] == ("-I", "-c"):
            return preflight.CommandResult(0, json.dumps({"version": "2.1.0", "callback_api_versioned": True}))
        raise AssertionError(f"unexpected command shape: {command[0]} {command[1:2]}")


class BalkonsBotPreflightTests(unittest.TestCase):
    def make_repo(self):
        temporary = tempfile.TemporaryDirectory()
        repo = Path(temporary.name) / "repo"
        fake_root = Path(temporary.name) / "root"
        for rel, content in (
            (preflight.PREFLIGHT_REL, MODULE_PATH.read_text(encoding="utf-8")),
            (preflight.SOURCE_REL, "print('tracked source')\n"),
            (preflight.TEMPLATE_REL, "[Service]\nUser=@SERVICE_USER@\n"),
            (preflight.DROPIN_REL, OVERLAY_PATH.read_text(encoding="utf-8")),
        ):
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        live = repo / "runtime" / "bot-current.py"
        live.parent.mkdir(parents=True, exist_ok=True)
        live.write_text("SECRET_BEARING_SOURCE_BYTES\n", encoding="utf-8")
        live_hash = hashlib.sha256(live.read_bytes()).hexdigest()
        for _credential_id, absolute_path in preflight.ENCRYPTED_CREDENTIAL_SPECS:
            path = preflight.map_absolute(absolute_path, fake_root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("ENCRYPTED_CIPHERTEXT_FIXTURE\n", encoding="utf-8")
            path.chmod(preflight.ENCRYPTED_CREDENTIAL_MODE)
        return temporary, repo, fake_root, live, live_hash

    def collect(self, repo: Path, fake_root: Path, live_hash: str, runner: FakeRunner):
        return preflight.collect_preflight(
            REPO_SHA, live_hash, repo_root=repo, runner=runner,
            credential_root_prefix=fake_root, expected_credential_owner_uid=os.geteuid(),
        )

    def test_pass_report_is_sanitized_and_read_only(self):
        temporary, repo, fake_root, live, live_hash = self.make_repo()
        self.addCleanup(temporary.cleanup)
        runner = FakeRunner(live_source=live)
        report = self.collect(repo, fake_root, live_hash, runner)
        self.assertEqual(report["preflight"], "PASS")
        self.assertFalse(report["mutation_started"])
        self.assertFalse(report["writes_performed"])
        self.assertTrue(report["critical_paths_tracked"])
        self.assertEqual(report["paho"]["callback_api_class"], "versioned")
        credentials = report["encrypted_credentials"]
        self.assertEqual(credentials["ids"], list(preflight.ENCRYPTED_CREDENTIAL_IDS))
        self.assertTrue(credentials["all_metadata_valid"])
        self.assertEqual(credentials["metadata_valid_count"], 5)
        self.assertFalse(credentials["content_read"])
        self.assertFalse(credentials["content_hashed"])
        encoded = json.dumps(report, sort_keys=True)
        for forbidden in (str(live), "svc-private-user", "/private/systemd", "ENCRYPTED_CIPHERTEXT_FIXTURE", "SECRET_BEARING_SOURCE_BYTES"):
            self.assertNotIn(forbidden, encoded)
        systemctl_commands = [cmd for cmd in runner.commands if cmd[0] == "systemctl"]
        self.assertEqual(len(systemctl_commands), 1)
        self.assertEqual(systemctl_commands[0][1], "show")
        self.assertNotIn("cat", systemctl_commands[0])

    def test_missing_encrypted_credential_blocks_without_content_read(self):
        temporary, repo, fake_root, live, live_hash = self.make_repo()
        self.addCleanup(temporary.cleanup)
        preflight.map_absolute(preflight.ENCRYPTED_CREDENTIAL_SPECS[0][1], fake_root).unlink()
        report = self.collect(repo, fake_root, live_hash, FakeRunner(live_source=live))
        self.assertEqual(report["preflight"], "BLOCKED")
        self.assertIn("encrypted_credential_telegram_token_missing", report["blockers"])
        self.assertFalse(report["encrypted_credentials"]["content_read"])
        self.assertFalse(report["encrypted_credentials"]["content_hashed"])

    def test_wrong_encrypted_credential_mode_blocks(self):
        temporary, repo, fake_root, live, live_hash = self.make_repo()
        self.addCleanup(temporary.cleanup)
        wrong = preflight.map_absolute(preflight.ENCRYPTED_CREDENTIAL_SPECS[-1][1], fake_root)
        wrong.chmod(0o600)
        report = self.collect(repo, fake_root, live_hash, FakeRunner(live_source=live))
        self.assertIn("encrypted_credential_mqtt_secret_metadata_invalid", report["blockers"])

    def test_live_source_provenance_mismatch_blocks(self):
        temporary, repo, fake_root, live, _live_hash = self.make_repo()
        self.addCleanup(temporary.cleanup)
        report = preflight.collect_preflight(
            REPO_SHA, "b" * 64, repo_root=repo, runner=FakeRunner(live_source=live),
            credential_root_prefix=fake_root, expected_credential_owner_uid=os.geteuid(),
        )
        self.assertEqual(report["preflight"], "BLOCKED")
        self.assertIn("live_source_provenance_mismatch", report["blockers"])

    def test_dirty_critical_paths_block(self):
        temporary, repo, fake_root, live, live_hash = self.make_repo()
        self.addCleanup(temporary.cleanup)
        report = self.collect(repo, fake_root, live_hash, FakeRunner(live_source=live, dirty=True))
        self.assertIn("critical_worktree_dirty", report["blockers"])

    def test_send_sigkill_must_remain_disabled(self):
        temporary, repo, fake_root, live, live_hash = self.make_repo()
        self.addCleanup(temporary.cleanup)
        report = self.collect(repo, fake_root, live_hash, FakeRunner(live_source=live, send_sigkill="yes"))
        self.assertIn("send_sigkill_not_disabled", report["blockers"])

    def test_repo_sha_mismatch_blocks(self):
        temporary, repo, fake_root, live, live_hash = self.make_repo()
        self.addCleanup(temporary.cleanup)
        report = self.collect(repo, fake_root, live_hash, FakeRunner(live_source=live, repo_sha="c" * 40))
        self.assertIn("repo_head_mismatch", report["blockers"])

    def test_execstart_shape_fails_closed_without_path_disclosure(self):
        temporary, repo, fake_root, live, live_hash = self.make_repo()
        self.addCleanup(temporary.cleanup)
        runner = FakeRunner(live_source=live, exec_start="{ path=/usr/bin/python3 ; argv[]=/usr/bin/python3 ; ignore_errors=no }")
        with self.assertRaises(preflight.PreflightError) as caught:
            preflight.collect_preflight(
                REPO_SHA, live_hash, repo_root=repo, runner=runner,
                credential_root_prefix=fake_root, expected_credential_owner_uid=os.geteuid(),
            )
        self.assertEqual(caught.exception.code, "execstart_source_ambiguous")

    def test_command_builders_are_narrow_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            systemctl = preflight.build_systemctl_command()
            self.assertEqual(systemctl[:3], ("systemctl", "show", preflight.SERVICE))
            for token in ("cat", "restart", "reload", "stop", "start"):
                self.assertNotIn(token, systemctl)
            self.assertEqual(preflight.build_git_head_command(repo)[3:], ("rev-parse", "HEAD"))
            self.assertEqual(preflight.build_git_status_command(repo)[3], "status")
            self.assertEqual(preflight.build_git_tracked_command(repo)[3:5], ("ls-files", "--stage"))
            self.assertEqual(preflight.build_paho_command(Path("/usr/bin/python3"))[1:3], ("-I", "-c"))

    def test_non_system_python_exec_fails_closed(self):
        with self.assertRaises(preflight.PreflightError) as caught:
            preflight.parse_exec_start("{ path=/tmp/python3 ; argv[]=/tmp/python3 /tmp/bot.py ; ignore_errors=no }")
        self.assertEqual(caught.exception.code, "python_executable_not_system_python")

    def test_versioned_system_python_is_accepted(self):
        python_executable, source = preflight.parse_exec_start(
            "{ path=/usr/bin/python3.11 ; argv[]=/usr/bin/python3.11 /opt/private/bot.py ; ignore_errors=no }"
        )
        self.assertEqual(python_executable, Path("/usr/bin/python3.11"))
        self.assertEqual(source, Path("/opt/private/bot.py"))

    def test_execstart_python_mismatch_fails_closed(self):
        with self.assertRaises(preflight.PreflightError) as caught:
            preflight.parse_exec_start(
                "{ path=/usr/bin/python3 ; argv[]=/usr/local/bin/python3 /opt/private/bot.py ; ignore_errors=no }"
            )
        self.assertEqual(caught.exception.code, "execstart_python_mismatch")

    def test_source_has_no_broad_runtime_or_credential_content_reads(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        for token in (
            "/proc/", "docker inspect", "systemctl cat", "journalctl", "mosquitto_",
            "/etc/credstore/", "CREDENTIALS_DIRECTORY", ".env", "sudo", "systemd-creds decrypt",
        ):
            self.assertNotIn(token, source)
        self.assertIn("/etc/credstore.encrypted/", source)
        self.assertIn(".lstat()", source)
        credential_slice = source[source.index("def collect_encrypted_credential_metadata"):source.index("def collect_preflight")]
        self.assertNotIn("sha256_file(path)", credential_slice)


if __name__ == "__main__":
    unittest.main()
