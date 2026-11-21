#!/usr/bin/env python3
"""Pure synthetic tests: never contact Docker, systemd or RPi5."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = ROOT / "ops/lib/deploy_executor/hermes_image_retention_v1.py"
spec = importlib.util.spec_from_file_location("hermes_image_retention_v1", SOURCE)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
NOW = datetime(2026, 11, 22, 6, tzinfo=timezone.utc)
ROLLBACK = next(iter(mod.PINNED))


def image(letter: str = "a", *, age: int = 20, extras: tuple[str, ...] = ()) -> dict:
    ident = "sha256:" + letter * 64
    ref = mod.IMAGE + "@" + ident
    return {
        "Id": ident,
        "RepoTags": [ref, *extras],
        "RepoDigests": [ref],
        "Config": {"Labels": {"org.opencontainers.image.revision": "b" * 40}},
        "Created": (NOW - timedelta(days=age)).isoformat(),
    }


class Selection(unittest.TestCase):
    def test_only_exact_unreferenced_old_digest_is_selected(self):
        old = image()
        young = image("c", age=13)
        marked = image("d", extras=("production",))
        tagged = image("e")
        tagged["RepoDigests"].append("other")
        badrev = image("f")
        badrev["Config"]["Labels"]["org.opencontainers.image.revision"] = "not-a-sha"
        objs = {x["Id"]: x for x in [old, young, marked, tagged, badrev]}
        self.assertEqual(mod.select(objs, set(), NOW), [old["Id"]])

    def test_stopped_container_reference_protects_image(self):
        old = image()
        self.assertEqual(mod.select({old["Id"]: old}, {old["Id"]}, NOW), [])

    def test_rollback_pin_protects_even_old_image(self):
        old = image()
        old["Id"] = ROLLBACK
        ref = mod.IMAGE + "@" + ROLLBACK
        old["RepoTags"] = [ref]
        old["RepoDigests"] = [ref]
        self.assertEqual(mod.select({ROLLBACK: old}, set(), NOW), [])

    def test_protects_exact_age_limit_and_clock_future(self):
        obj = image()
        obj["Created"] = (NOW - mod.RETENTION + timedelta(seconds=1)).isoformat()
        self.assertFalse(mod.candidate_for(obj, set(), NOW))
        obj["Created"] = (NOW - mod.RETENTION).isoformat()
        self.assertTrue(mod.candidate_for(obj, set(), NOW))
        obj["Created"] = (NOW + timedelta(hours=1)).isoformat()
        self.assertFalse(mod.candidate_for(obj, set(), NOW))

    def test_selects_oldest_first_with_hard_cap(self):
        objs = {}
        for i in range(38):
            ident = "sha256:" + format(i + 1, "064x")
            ref = mod.IMAGE + "@" + ident
            objs[ident] = {"Id": ident, "RepoTags": [ref], "RepoDigests": [ref],
                           "Config": {"Labels": {"org.opencontainers.image.revision": "c" * 40}},
                           "Created": (NOW - timedelta(days=15 + i)).isoformat()}
        selected = mod.select(objs, set(), NOW)
        self.assertEqual(len(selected), mod.MAX_REMOVE)
        self.assertEqual(selected[0], "sha256:" + format(38, "064x"))
        self.assertNotIn("sha256:" + format(1, "064x"), selected)

    def test_invalid_created_and_extra_tags_are_excluded(self):
        obj = image()
        obj["Created"] = "invalid"
        self.assertEqual(mod.select({obj["Id"]: obj}, set(), NOW), [])
        obj = image()
        obj["RepoTags"].append(mod.IMAGE + ":production")
        self.assertEqual(mod.select({obj["Id"]: obj}, set(), NOW), [])


class State(unittest.TestCase):
    def test_state_marker_is_atomic_and_blocked_is_sticky(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td) / "state"
            directory.mkdir(mode=0o700)
            with mock.patch.object(mod, "STATE_DIR", directory), mock.patch.object(mod, "STATE_PATH", directory / "state.json"):
                mod.write_state("BLOCKED", "e" * 64)
                with self.assertRaisesRegex(mod.Stop, "previous_attempt_blocked"):
                    mod.inspect_state()
                mod.write_state("DONE", "e" * 64)
                mod.inspect_state()
                state = json.loads((directory / "state.json").read_text())
                self.assertEqual(state["state"], "DONE")
                self.assertEqual(state["manifest_sha256"], "e" * 64)
                self.assertEqual((directory / "state.json").stat().st_mode & 0o777, 0o600)

    def test_refuses_symlink_state_file(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td) / "state"
            directory.mkdir(mode=0o700)
            (directory / "state.json").symlink_to(Path(td) / "other")
            with mock.patch.object(mod, "STATE_DIR", directory), mock.patch.object(mod, "STATE_PATH", directory / "state.json"):
                with self.assertRaisesRegex(mod.Stop, "state_symlink"):
                    mod.inspect_state()


class Execution(unittest.TestCase):
    def simulate(self, *, fails: bool):
        with tempfile.TemporaryDirectory() as td:
            lock = Path(td) / "lock"
            lock.touch(mode=0o600)
            state = Path(td) / "state"
            state.mkdir(mode=0o700)
            old = image()
            obj = {old["Id"]: old}
            for pin in mod.PINNED:
                obj[pin] = {"Id": pin}
            present = set(obj)
            calls = []

            def fake_command(args, timeout=45):
                calls.append(tuple(args))
                if args[:4] == ["docker", "image", "ls", "--all"]:
                    return json.dumps({"Repository": "<none>", "Tag": "<none>", "ID": old["Id"]}) + "\n"
                if args[:3] == ["docker", "image", "rm"]:
                    if fails:
                        raise mod.Stop("synthetic_removal_error")
                    present.remove(old["Id"])
                return ""

            def fake_info(ids):
                return {item: obj[item] for item in ids if item in present}

            with (mock.patch.object(mod, "LOCK_PATH", lock),
                  mock.patch.object(mod, "STATE_DIR", state),
                  mock.patch.object(mod, "STATE_PATH", state / "state.json"),
                  mock.patch.object(mod, "command", fake_command),
                  mock.patch.object(mod, "image_set", lambda: set(present)),
                  mock.patch.object(mod, "image_info", fake_info),
                  mock.patch.object(mod, "container_state", lambda: (set(), set(), set())),
                  mock.patch.object(mod, "volumes", lambda: set()),
                  mock.patch.object(mod, "health", lambda: None),
                  mock.patch.object(mod, "update_success_today", lambda when: None),
                  mock.patch.object(mod.socket, "gethostname", lambda: mod.HOST)):
                if fails:
                    with self.assertRaisesRegex(mod.Stop, "synthetic_removal_error"):
                        mod.run(apply=True)
                    self.assertEqual(json.loads((state / "state.json").read_text())["state"], "BLOCKED")
                    first_rm_count = sum(c[:3] == ("docker", "image", "rm") for c in calls)
                    with self.assertRaisesRegex(mod.Stop, "previous_attempt_blocked"):
                        mod.run(apply=True)
                    self.assertEqual(sum(c[:3] == ("docker", "image", "rm") for c in calls), first_rm_count)
                else:
                    mod.run(apply=True)
                    self.assertEqual(json.loads((state / "state.json").read_text())["state"], "DONE")
                    self.assertNotIn(old["Id"], present)
                    self.assertTrue(set(mod.PINNED) <= present)
                    self.assertEqual(sum(c[:3] == ("docker", "image", "rm") for c in calls), 1)

    def test_exact_success_removes_only_target(self):
        self.simulate(fails=False)

    def test_failure_blocks_future_scheduled_attempts(self):
        self.simulate(fails=True)


class SystemdContracts(unittest.TestCase):
    def test_owner_isolated_weekly_timer_and_source_pins(self):
        unit = (ROOT / "ops/systemd/rozkalns-hermes-image-retention.service").read_text()
        timer = (ROOT / "ops/systemd/rozkalns-hermes-image-retention.timer").read_text()
        self.assertIn("OnCalendar=Sun *-*-* 04:30:00", timer)
        self.assertIn("Persistent=false", timer)
        self.assertIn("StateDirectory=rozkalns-hermes-image-retention", unit)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertIn("--apply", unit)
        self.assertNotIn("docker image prune -a", SOURCE.read_text())
        self.assertNotIn("docker system prune", SOURCE.read_text())
        self.assertIn('"--no-prune"', SOURCE.read_text())


if __name__ == "__main__":
    unittest.main()
