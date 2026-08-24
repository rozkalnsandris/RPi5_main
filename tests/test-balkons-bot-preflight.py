#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops/bin/balkons-bot-preflight"

loader = importlib.machinery.SourceFileLoader("balkons_bot_preflight", str(MODULE_PATH))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
preflight = importlib.util.module_from_spec(spec)
loader.exec_module(preflight)

REPO_SHA = "a" * 40


class FakeRunner:
    def __init__(
        self,
        *,
        repo_sha: str = REPO_SHA,
        dirty: bool = False,
        send_sigkill: str = "no",
        active_state: str = "active",
        sub_state: str = "running",
        exec_start: str | None = None,
        live_source: Path,
    ) -> None:
        self.repo_sha = repo_sha
        self.dirty = dirty
        self.send_sigkill = send_sigkill
        self.active_state = active_state
        self.sub_state = sub_state
        self.live_source = live_source
        self.exec_start = exec_start or (
            "{ path=/usr/bin/python3 ; "
            f"argv[]=/usr/bin/python3 {live_source} ; "
            "ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; "
            "pid=0 ; code=(null) ; status=0/0 }"
        )
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command):
        command = tuple(command)
        self.commands.append(command)
        if command[0] == "git" and command[3:5] == ("rev-parse", "HEAD"):
            return preflight.CommandResult(0, self.repo_sha + "\n")
        if command[0] == "git" and command[3] == "status":
            return preflight.CommandResult(
                0,
                " M ops/lib/balkons-bot.py\n" if self.dirty else "",
            )
        if command[:3] == ("systemctl", "show", preflight.SERVICE):
            payload = "\n".join(
                [
                    "LoadState=loaded",
                    f"ActiveState={self.active_state}",
                    f"SubState={self.sub_state}",
                    "User=svc-private-user",
                    f"ExecStart={self.exec_start}",
                    "Restart=on-failure",
                    "RestartUSec=3s",
                    "TimeoutStopUSec=45s",
                    f"SendSIGKILL={self.send_sigkill}",
                    "FragmentPath=/private/systemd/balkons-bot.service",
                ]
            )
            return preflight.CommandResult(0, payload + "\n")
        if command[0] == "/usr/bin/python3" and command[1] == "-c":
            return preflight.CommandResult(
                0,
                json.dumps(
                    {"version": "2.1.0", "callback_api_versioned": True}
                ),
            )
        raise AssertionError(f"unexpected command shape: {command[0]} {command[1:2]}")


class BalkonsBotPreflightTests(unittest.TestCase):
    def make_repo(self):
        temporary = tempfile.TemporaryDirectory()
        repo = Path(temporary.name)
        for rel, content in (
            (preflight.PREFLIGHT_REL, MODULE_PATH.read_text(encoding="utf-8")),
            (preflight.SOURCE_REL, "print('tracked source')\n"),
            (preflight.TEMPLATE_REL, "[Service]\nUser=@SERVICE_USER@\n"),
        ):
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        live = repo / "runtime" / "bot-current.py"
        live.parent.mkdir(parents=True, exist_ok=True)
        live.write_text("SECRET_BEARING_SOURCE_BYTES\n", encoding="utf-8")
        live_hash = hashlib.sha256(live.read_bytes()).hexdigest()
        return temporary, repo, live, live_hash

    def test_pass_report_is_sanitized_and_read_only(self):
        temporary, repo, live, live_hash = self.make_repo()
        self.addCleanup(temporary.cleanup)
        runner = FakeRunner(live_source=live)

        report = preflight.collect_preflight(
            REPO_SHA,
            live_hash,
            repo_root=repo,
            runner=runner,
        )

        self.assertEqual(report["preflight"], "PASS")
        self.assertFalse(report["mutation_started"])
        self.assertFalse(report["writes_performed"])
        self.assertEqual(report["paho"]["callback_api_class"], "versioned")
        encoded = json.dumps(report, sort_keys=True)
        self.assertNotIn(str(live), encoded)
        self.assertNotIn("svc-private-user", encoded)
        self.assertNotIn("/private/systemd", encoded)
        self.assertNotIn("SECRET_BEARING_SOURCE_BYTES", encoded)

        systemctl_commands = [cmd for cmd in runner.commands if cmd[0] == "systemctl"]
        self.assertEqual(len(systemctl_commands), 1)
        self.assertEqual(systemctl_commands[0][1], "show")
        self.assertNotIn("cat", systemctl_commands[0])

    def test_live_source_provenance_mismatch_blocks(self):
        temporary, repo, live, _live_hash = self.make_repo()
        self.addCleanup(temporary.cleanup)
        runner = FakeRunner(live_source=live)

        report = preflight.collect_preflight(
            REPO_SHA,
            "b" * 64,
            repo_root=repo,
            runner=runner,
        )
        self.assertEqual(report["preflight"], "BLOCKED")
        self.assertIn("live_source_provenance_mismatch", report["blockers"])

    def test_dirty_critical_paths_block(self):
        temporary, repo, live, live_hash = self.make_repo()
        self.addCleanup(temporary.cleanup)
        runner = FakeRunner(live_source=live, dirty=True)
        report = preflight.collect_preflight(
            REPO_SHA,
            live_hash,
            repo_root=repo,
            runner=runner,
        )
        self.assertIn("critical_worktree_dirty", report["blockers"])

    def test_send_sigkill_must_remain_disabled(self):
        temporary, repo, live, live_hash = self.make_repo()
        self.addCleanup(temporary.cleanup)
        runner = FakeRunner(live_source=live, send_sigkill="yes")
        report = preflight.collect_preflight(
            REPO_SHA,
            live_hash,
            repo_root=repo,
            runner=runner,
        )
        self.assertIn("send_sigkill_not_disabled", report["blockers"])

    def test_repo_sha_mismatch_blocks(self):
        temporary, repo, live, live_hash = self.make_repo()
        self.addCleanup(temporary.cleanup)
        runner = FakeRunner(live_source=live, repo_sha="c" * 40)
        report = preflight.collect_preflight(
            REPO_SHA,
            live_hash,
            repo_root=repo,
            runner=runner,
        )
        self.assertIn("repo_head_mismatch", report["blockers"])

    def test_execstart_shape_fails_closed_without_path_disclosure(self):
        temporary, repo, live, live_hash = self.make_repo()
        self.addCleanup(temporary.cleanup)
        runner = FakeRunner(
            live_source=live,
            exec_start="{ path=/usr/bin/python3 ; argv[]=/usr/bin/python3 ; ignore_errors=no }",
        )
        with self.assertRaises(preflight.PreflightError) as caught:
            preflight.collect_preflight(
                REPO_SHA,
                live_hash,
                repo_root=repo,
                runner=runner,
            )
        self.assertEqual(caught.exception.code, "execstart_source_ambiguous")

    def test_command_builders_are_narrow_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            systemctl = preflight.build_systemctl_command()
            self.assertEqual(systemctl[:3], ("systemctl", "show", preflight.SERVICE))
            self.assertNotIn("cat", systemctl)
            self.assertNotIn("restart", systemctl)
            self.assertNotIn("reload", systemctl)
            self.assertNotIn("stop", systemctl)
            self.assertNotIn("start", systemctl)

            git_head = preflight.build_git_head_command(repo)
            git_status = preflight.build_git_status_command(repo)
            self.assertEqual(git_head[3:], ("rev-parse", "HEAD"))
            self.assertEqual(git_status[3], "status")

    def test_source_has_no_broad_runtime_or_secret_reads(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        forbidden = (
            "/proc/",
            "docker inspect",
            "systemctl cat",
            "journalctl",
            "mosquitto_",
            "/etc/credstore",
            "CREDENTIALS_DIRECTORY",
            ".env",
            "sudo",
        )
        for token in forbidden:
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
