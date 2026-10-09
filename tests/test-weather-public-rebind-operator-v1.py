#!/usr/bin/env python3
"""Hermetic source checks for Weather-only operator. Never touch live host."""
from __future__ import annotations
import copy
import json
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("weather_rebind_operator", ROOT / "scripts/weather_public_rebind_operator_v1.py")
assert spec and spec.loader
op = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = op
spec.loader.exec_module(op)


class WeatherRebindOperatorTests(unittest.TestCase):
    def test_exact_argv_matches_reviewed_contract(self):
        spec = op.contract()
        self.assertEqual(op.FROZEN_ARGV, spec["phases"][4]["argv"])
        self.assertEqual(op.FROZEN_ARGV[-1], "weather")
        self.assertIn("--no-deps", op.FROZEN_ARGV)
        self.assertIn("--force-recreate", op.FROZEN_ARGV)
        self.assertEqual(op.FROZEN_ARGV[op.FROZEN_ARGV.index("--pull") + 1], "never")
        self.assertNotIn("down", op.FROZEN_ARGV)

    def test_source_gate_fails_closed_for_nonroot_and_wrong_checkout(self):
        with patch.object(op.os, "geteuid", return_value=1000):
            with self.assertRaises(op.Blocked):
                op.source_gate("a" * 40)
        with patch.object(op.os, "geteuid", return_value=0), patch.object(op, "git", return_value="unexpected"):
            with self.assertRaises(op.Blocked):
                op.source_gate("a" * 40)


    def test_root_git_status_does_not_refresh_shared_index(self):
        """The root source gate must never take optional Git index locks."""
        expected_sha = "a" * 40
        status_args = ("status", "--porcelain=v1", "--untracked-files=all")
        answers = {
            ("rev-parse", "--show-toplevel"): str(op.ROOT),
            ("branch", "--show-current"): "main",
            ("rev-parse", "HEAD"): expected_sha,
            ("remote", "get-url", "origin"): op.ORIGIN,
            status_args: "",
        }
        calls = []

        def fake_command(argv, timeout=20):
            self.assertEqual(
                argv[:6],
                ["/usr/bin/git", "--no-optional-locks", "-c",
                 f"safe.directory={op.ROOT}", "-C", str(op.ROOT)],
            )
            args = tuple(argv[6:])
            calls.append(args)
            return answers[args]

        with patch.object(op, "command", side_effect=fake_command), \
             patch.object(op.os, "geteuid", return_value=0), \
             patch.object(op, "source_errors", return_value=[]):
            op.source_gate(expected_sha)
            self.assertIn(status_args, calls)
            self.assertEqual(calls.count(status_args), 1)
            answers[status_args] = "?? unexpected-untracked"
            with self.assertRaises(op.Blocked):
                op.source_gate(expected_sha)
            self.assertEqual(calls.count(status_args), 2)

    def test_fixed_file_mode_symlink_and_length_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "file"
            p.write_bytes(b"sample")
            p.chmod(0o444)
            self.assertEqual(op.fixed_file(p, op.os.getuid(), 0o444), b"sample")
            with self.assertRaises(op.Blocked):
                op.fixed_file(p, op.os.getuid(), 0o600)
            with self.assertRaises(op.Blocked):
                op.fixed_file(p, op.os.getuid(), 0o444, limit=2)
            link = Path(tmp) / "link"
            link.symlink_to(p)
            with self.assertRaises(OSError):
                op.fixed_file(link, op.os.getuid(), 0o444)

    def test_preflight_lock_must_exist_and_never_be_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "absent"
            with self.assertRaises(FileNotFoundError):
                with op.weather_lock(path):
                    pass
            self.assertFalse(path.exists())

    def test_staging_preserves_unrelated_files_and_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = {k: root / k for k in ("compose", "registry", "identity")}
            old = {k:k.encode() for k in paths}
            new = {k:(k+"new").encode() for k in paths}
            for k in paths:
                paths[k].write_bytes(old[k])
                paths[k].chmod(0o444)
            sentinel = root / "sentinel"
            sentinel.write_bytes(b"SAFE")
            stages = []
            def fake_stage(path, data):
                path.write_bytes(data)
                path.chmod(0o444)
            with patch.object(op, "stage", side_effect=fake_stage), patch.object(
                op, "fixed_file", side_effect=lambda p, uid, mode:p.read_bytes()
            ):
                op.replace_three(paths, old, new, lambda n,m:stages.append((n,m)),
                                 quiescence_check=lambda: None)
            self.assertEqual([x[0] for x in stages[-3:]],
                             ["REPLACE_COMPOSE","REPLACE_REGISTRY","REPLACE_IDENTITY"])
            self.assertTrue(all(stages[i][1] for i in range(len(stages))))
            self.assertEqual([paths[k].read_bytes() for k in paths], [new[k] for k in paths])
            self.assertEqual(sentinel.read_bytes(), b"SAFE")
            self.assertFalse(list(root.glob("*.staged")))

    def test_staging_failure_never_triggers_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths={k:Path(tmp)/k for k in ("compose","registry","identity")}
            for k,p in paths.items(): p.write_bytes(k.encode())
            stages=[]
            with patch.object(op, "stage", side_effect=OSError("failed")):
                with self.assertRaises(OSError):
                    op.replace_three(paths, {k:k.encode() for k in paths},
                                     {k:b"new" for k in paths},
                                     lambda n,m:stages.append((n,m)),
                                     quiescence_check=lambda: None)
            self.assertEqual(stages,[("STAGING",True)])
            self.assertEqual([p.read_bytes() for p in paths.values()],
                             [k.encode() for k in paths])

    def test_never_runs_host_commands_after_blocked_source(self):
        with patch.object(op,"source_gate",side_effect=op.Blocked("NO")):
            with patch.object(op,"command") as run:
                result=op.execute("a"*40,apply=True)
            run.assert_not_called()
        self.assertEqual(result["result"],"BLOCKED")
        self.assertFalse(result["mutation_performed"])


    def test_listener_classification_is_loopback_only(self):
        for observation, accepted in [
            ("LISTEN 0 4096 127.0.0.1:9180 0.0.0.0:*", True),
            ("LISTEN 0 4096 0.0.0.0:9180 0.0.0.0:*", False),
            ("LISTEN 0 4096 [::]:9180 [::]:*", False),
            ("LISTEN 0 4096 127.0.0.1:9180 0.0.0.0:*\nLISTEN 0 4096 [::]:9180 [::]:*", False),
            ("", False),
        ]:
            with self.subTest(observation=observation):
                with patch.object(op, "command", return_value=observation):
                    self.assertIs(op.listener_loopback(), accepted)

    def test_health_request_is_fixed_local_tcp_without_redirects(self):
        with patch.object(op, "HTTPConnection") as create:
            client = create.return_value
            client.getresponse.return_value.status = 200
            self.assertTrue(op.health("health"))
            create.assert_called_once_with("127.0.0.1", 9180, timeout=5)
            client.request.assert_called_once_with("GET", "/health")
            client.close.assert_called_once()
        with patch.object(op, "HTTPConnection") as create:
            self.assertFalse(op.health("redirect"))
            create.assert_not_called()

    def test_only_weather_compose_digest_delta_is_allowed(self):
        spec = op.contract()
        desired = json.loads((ROOT / spec["source_files"]["registry"]).read_text())
        old = copy.deepcopy(desired)
        item = next(t for t in old["targets"] if t["target_alias"] == spec["target_alias"])
        item["compose"]["file_sha256"] = spec["baseline"]["compose_sha256_from_readonly_host"]
        op.require_registry_delta(old, desired, spec)
        cases = []
        bad = copy.deepcopy(old)
        next(t for t in bad["targets"] if t["target_alias"] != spec["target_alias"])["persistent_volumes"] = ["unauthorized"]
        cases.append(bad)
        bad = copy.deepcopy(old)
        next(t for t in bad["targets"] if t["target_alias"] == spec["target_alias"])["shared_workflow_sha"] = "0" * 40
        cases.append(bad)
        bad = copy.deepcopy(old)
        bad["targets"].reverse()
        cases.append(bad)
        bad = copy.deepcopy(old)
        bad["targets"][0]["compose"]["project"] = "different"
        cases.append(bad)
        bad = copy.deepcopy(old)
        bad["targets"][0]["compose"]["file_sha256"] = "1" * 64
        cases.append(bad)
        bad = copy.deepcopy(old)
        bad["unexpected"] = True
        cases.append(bad)
        for bad in cases:
            with self.subTest(case=cases.index(bad)):
                with self.assertRaises(op.Blocked):
                    op.require_registry_delta(bad, desired, spec)

    def test_protected_env_metadata_root_runtime_group_0640_only(self):
        import stat
        from types import SimpleNamespace
        spec = op.contract()
        runtime_gid = 725
        good = SimpleNamespace(st_mode=stat.S_IFREG | 0o640, st_uid=0, st_gid=runtime_gid)
        self.assertTrue(op.protected_env_metadata_valid(good, runtime_gid, spec))
        for mode, uid, gid in ((0o600, 0, runtime_gid), (0o644, 0, runtime_gid),
                               (0o640, 1000, runtime_gid), (0o640, 0, 0)):
            with self.subTest(mode=mode, uid=uid, gid=gid):
                bad = SimpleNamespace(st_mode=stat.S_IFREG | mode, st_uid=uid, st_gid=gid)
                self.assertFalse(op.protected_env_metadata_valid(bad, runtime_gid, spec))
        link = SimpleNamespace(st_mode=stat.S_IFLNK | 0o640, st_uid=0, st_gid=runtime_gid)
        self.assertFalse(op.protected_env_metadata_valid(link, runtime_gid, spec))
        self.assertNotIn("read_bytes()", op.protected_env_metadata_valid.__doc__ or "")

    def test_quiescence_exact_statuses_block_active_failed_and_unknown(self):
        spec = op.contract()
        good = {k:dict(v["expected"]) for k,v in spec["quiescence"]["units"].items()}
        self.assertTrue(all(op.classify_quiescence(spec, good).values()))
        for key, state, value in (
            ("weather_ingest_service_quiesced", "ActiveState", "failed"),
            ("weather_ingest_service_quiesced", "Result", "exit-code"),
            ("weather_ingest_service_quiesced", "ActiveState", "active"),
            ("weather_ingest_timer_quiesced", "ActiveState", "active"),
            ("simple_deployer_service_quiesced", "ActiveState", "active"),
            ("simple_deployer_timer_quiesced", "ActiveState", "active"),
            ("weather_ingest_timer_quiesced", "UnitFileState", "disabled"),
            ("simple_deployer_timer_quiesced", "SubState", "waiting"),
            ("weather_ingest_service_quiesced", "Result", "unknown"),
        ):
            with self.subTest(key=key, state=state, value=value):
                bad = copy.deepcopy(good)
                bad[key][state] = value
                self.assertFalse(op.classify_quiescence(spec, bad)[key])
        for k in good:
            case = copy.deepcopy(good)
            del case[k]
            with self.assertRaises(op.Blocked):
                op.classify_quiescence(spec, case)
        case = copy.deepcopy(good)
        case["raw_journal"] = "forbidden"
        with self.assertRaises(op.Blocked):
            op.classify_quiescence(spec, case)

    def test_quiescence_uses_fixed_read_only_systemctl_argv(self):
        spec = op.contract()
        fixtures = {v["unit"]:v["expected"] for v in spec["quiescence"]["units"].values()}
        seen = []
        def fake_cmd(argv, timeout=20):
            seen.append(tuple(argv))
            unit = argv[-1]
            values = fixtures[unit]
            return "\n".join(k + "=" + values[k] for k in
                             spec["quiescence"]["metadata_only_properties"])
        with patch.object(op, "command", side_effect=fake_cmd):
            self.assertTrue(all(op.require_quiescence(spec).values()))
        self.assertEqual(len(seen), 4)
        for argv in seen:
            self.assertEqual(argv[:4], (
                "/usr/bin/systemctl", "show", "--no-pager",
                "--property=ActiveState,SubState,Result,UnitFileState",
            ))
        fixtures["rozkalns-weather-public-ingest.service"] = {
            **fixtures["rozkalns-weather-public-ingest.service"],
            "ActiveState": "failed", "SubState": "failed", "Result": "exit-code",
        }
        with patch.object(op, "command", side_effect=fake_cmd):
            with self.assertRaises(op.Blocked):
                op.require_quiescence(spec)

    def test_replace_requires_quiescence_before_staging_and_each_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = {k:Path(tmp)/k for k in ("compose","registry","identity")}
            old = {k:k.encode() for k in paths}
            new = {k:b"new" for k in paths}
            for k,p in paths.items():
                p.write_bytes(old[k])
                p.chmod(0o444)
            progress, checks = [], []
            def gate():
                checks.append(True)
                if len(checks) == 3:
                    raise op.Blocked("TIMER_REACTIVATED")
            with patch.object(op, "stage", side_effect=lambda path,data:path.write_bytes(data)), \
                 patch.object(op, "fixed_file", side_effect=lambda p,uid,mode:p.read_bytes()):
                with self.assertRaises(op.Blocked):
                    op.replace_three(paths,old,new,lambda name,m:progress.append((name,m)),
                                     quiescence_check=gate)
            self.assertEqual(len(checks),3)
            self.assertEqual([x[0] for x in progress],["STAGING","STAGING","STAGING"])
            self.assertTrue(all(paths[k].read_bytes()==old[k] for k in paths))

    def test_no_implicit_systemd_or_recovery_mutations(self):
        src=(ROOT/"scripts/weather_public_rebind_operator_v1.py").read_text()
        for forbidden in ("reset-failed", "restart", "systemctl stop",
                          "systemctl start", "enable --now", "disable --now",
                          "journalctl", "daemon-reload"):
            self.assertNotIn(forbidden, src)

    def test_no_implicit_live_capabilities(self):
        source=(ROOT/"scripts/weather_public_rebind_operator_v1.py").read_text()
        self.assertNotIn("shell=True",source)
        self.assertNotIn("docker compose down",source)
        self.assertNotIn("shutil.rmtree",source)
        self.assertNotIn("os.environ.copy",source)
        self.assertNotIn("print(result.stdout)",source)
        self.assertIn("LOCAL_PASS_PHASE7_PENDING",source)


if __name__=="__main__":
    unittest.main()
