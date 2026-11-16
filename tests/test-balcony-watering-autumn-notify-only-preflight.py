#!/usr/bin/env python3
"""Offline no-network/no-actuator tests for existing-11:00 repair preflight."""
from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/bin/balcony-watering-autumn-notify-only-preflight"
loader = importlib.machinery.SourceFileLoader("autumn_notify_only_1498", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)

OLD = b"ACTIVE_SENSORS=(1 3 4 5 6 7 8 9 10 11 12 13)\nactive sensors not usable\napi.telegram.org\n"
CANDIDATE = (
    b"ACTIVE_SENSORS=(1 3 4 5 6 7 8 9 10 11 12 13)\n"
    b"active sensors not usable\n"
    b"balkons/telegram_out\nESP32_MAX_SECONDS=180\nPUMP_IS_ON=0\n"
)
BOT = b'T_OUT = "balkons/telegram_out"\nclient.subscribe(T_OUT)\n'


def job(name, expr, role, *, enabled=False, deliver="local", script=None):
    return {
        "id": name,
        "name": name,
        "enabled": enabled,
        "deliver": deliver,
        "script": script if script is not None else role,
        "prompt": "",
        "schedule": {"kind": "cron", "expr": expr},
    }


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "andris"
        self.root = self.home / ".hermes/scripts"
        self.root.mkdir(parents=True)
        self.repo = self.home / "RPi5_main"
        self.source = self.repo / "ops/bin/balcony-watering-autumn-notify-only"
        self.bot = self.repo / "ops/lib/balkons-bot.py"
        self.source.parent.mkdir(parents=True)
        self.bot.parent.mkdir(parents=True)
        self.source.write_bytes(CANDIDATE)
        self.bot.write_bytes(BOT)
        self.wrapper = self.root / "balcony-watering-autumn-run.sh"
        self.wrapper.write_text(
            '#!/bin/bash\nexec "$HOME/.hermes/scripts/balcony-watering-autumn.sh"\n',
            encoding="utf-8",
        )
        self.target = self.root / "balcony-watering-autumn.sh"
        self.target.write_bytes(OLD)
        self.target.chmod(0o700)
        self.store = self.home / ".hermes/cron/jobs.json"
        self.store.parent.mkdir(parents=True)
        self.jobs = [
            job("legacy07", "0 7 * * *", "laistisana_2x.sh", deliver="telegram"),
            job("legacy14", "0 14 * * *", "laistisana_2x_karstums.sh", deliver="telegram"),
            job("legacy23", "0 23 * * *", "laistisana_2x.sh", deliver="telegram"),
            job("autumn11", "0 11 * * *", "autumn", enabled=True,
                script=str(self.wrapper)),
            job("unrelated", "0 11 * * *", "not-watering"),
        ]
        self.save_store()
        self.hashes = {
            "old_sha": m.digest(OLD),
            "wrapper_sha": m.digest(self.wrapper.read_bytes()),
            "candidate_sha": m.digest(CANDIDATE),
            "job_sha": m.gate_module()._fingerprint(self.jobs[3]),
        }

    def save_store(self):
        self.store.write_text(json.dumps({"jobs": self.jobs, "updated_at": "synthetic"}))
        self.store.chmod(0o600)

    def inspect(self, *, diagnostics=None):
        return m.inspect(
            store=self.store, home=self.home,
            source=self.source, bot=self.bot,
            expected_uid=os.geteuid(), diagnostic_categories=diagnostics,
            **self.hashes,
        )

    def block(self, needle):
        with self.assertRaises(m.Blocked) as ctx:
            self.inspect()
        self.assertEqual(str(ctx.exception), needle)

    def test_existing_11h_pass_is_sanitized_and_does_not_write(self):
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns)
                  for p in (self.store, self.wrapper, self.target, self.source, self.bot)}
        report = self.inspect()
        self.assertEqual(report["result"], "SOURCE_NOTIFY_ONLY_PREFLIGHT_PASS")
        self.assertEqual(report["legacy_jobs"], "three_disabled")
        self.assertEqual(report["legacy_11_13"], "still_required_and_fail_closed")
        self.assertEqual(report["live_bot_delivery"], "unverified")
        self.assertFalse(report["live_apply_authorized"])
        self.assertFalse(report["mutation_started"])
        self.assertFalse(report["writes_performed"])
        self.assertFalse(report["raw_payload_emitted"])
        rendered = json.dumps(report)
        self.assertNotIn(str(self.home), rendered)
        self.assertNotIn("not-watering", rendered)
        self.assertNotIn("laistisana_2x", rendered)
        for path, state in before.items():
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), state)

    def test_counter_increment_only_diagnosed_but_remains_blocked(self):
        self.jobs[3]["run_count"] = 12
        self.hashes["job_sha"] = m.gate_module()._fingerprint(self.jobs[3])
        self.jobs[3]["run_count"] = 13
        self.save_store()
        diagnostics = []
        with self.assertRaises(m.Blocked) as error:
            self.inspect(diagnostics=diagnostics)
        self.assertEqual(str(error.exception), "autumn_job_identity_drift")
        self.assertEqual(diagnostics, ["run_count_increment_only"])
        # Without explicit diagnostic mode the same strict gate still blocks.
        self.block("autumn_job_identity_drift")

    def test_counter_just_added_diagnosed_but_remains_blocked(self):
        self.jobs[3]["run_count"] = 1
        self.save_store()
        diagnostics = []
        with self.assertRaises(m.Blocked) as error:
            self.inspect(diagnostics=diagnostics)
        self.assertEqual(str(error.exception), "autumn_job_identity_drift")
        self.assertEqual(diagnostics, ["run_count_added_only"])

    def test_definition_change_with_counter_is_unclassified(self):
        self.jobs[3]["run_count"] = 7
        self.hashes["job_sha"] = m.gate_module()._fingerprint(self.jobs[3])
        self.jobs[3]["run_count"] = 8
        self.jobs[3]["prompt"] = "PRIVATE_SYNTHETIC_NOT_TO_EMIT"
        self.save_store()
        diagnostics = []
        with self.assertRaises(m.Blocked) as error:
            self.inspect(diagnostics=diagnostics)
        self.assertEqual(str(error.exception), "autumn_job_identity_drift")
        self.assertEqual(diagnostics, ["unclassified"])
        self.assertNotIn("PRIVATE_SYNTHETIC_NOT_TO_EMIT",
                         repr(diagnostics))

    def test_noninteger_or_unbounded_counter_never_classified_as_only(self):
        for value in (True, "8", -1, 1_000_001):
            with self.subTest(value=value):
                self.jobs[3]["run_count"] = value
                self.save_store()
                diagnostics = []
                with self.assertRaises(m.Blocked) as error:
                    self.inspect(diagnostics=diagnostics)
                self.assertEqual(str(error.exception),
                                 "autumn_job_identity_drift")
                self.assertEqual(diagnostics, ["unclassified"])

    def test_counter_guess_does_not_erase_invariant_mismatch(self):
        self.jobs[3]["run_count"] = 1
        self.jobs[3]["deliver"] = "telegram"
        self.save_store()
        diagnostics = []
        with self.assertRaises(m.Blocked) as error:
            self.inspect(diagnostics=diagnostics)
        self.assertEqual(str(error.exception),
                         "autumn_job_binding_or_delivery_invalid")
        self.assertEqual(diagnostics, [])


    def test_hermes_last_dispatch_added_only_always_blocks(self):
        self.jobs[3]["last_dispatch"] = {"kind": "on_time", "at": "sample"}
        self.save_store()
        categories = []
        with self.assertRaises(m.Blocked) as raised:
            self.inspect(diagnostics=categories)
        self.assertEqual(str(raised.exception), "autumn_job_identity_drift")
        self.assertEqual(categories, ["last_dispatch_added_only"])

    def test_hermes_pending_slot_added_only_always_blocks(self):
        self.jobs[3]["pending_slot"] = {"at": "sample", "by": "gateway"}
        self.save_store()
        categories = []
        with self.assertRaises(m.Blocked) as raised:
            self.inspect(diagnostics=categories)
        self.assertEqual(str(raised.exception), "autumn_job_identity_drift")
        self.assertEqual(categories, ["pending_slot_added_only"])

    def test_hermes_two_added_metadata_fields_reconstruct_frozen_hash(self):
        self.jobs[3]["last_dispatch"] = {"kind": "late"}
        self.jobs[3]["pending_slot"] = {"at": "sample"}
        self.save_store()
        categories = []
        with self.assertRaises(m.Blocked):
            self.inspect(diagnostics=categories)
        self.assertEqual(categories,
                         ["last_dispatch_and_pending_slot_added_only"])

    def test_hermes_counter_plus_dispatch_added_always_blocks(self):
        self.jobs[3]["run_count"] = 4
        self.hashes["job_sha"] = m.gate_module()._fingerprint(self.jobs[3])
        self.jobs[3]["run_count"] = 5
        self.jobs[3]["last_dispatch"] = {"kind": "late", "attempt": 5}
        self.save_store()
        categories = []
        with self.assertRaises(m.Blocked):
            self.inspect(diagnostics=categories)
        self.assertEqual(categories, ["run_count_plus_last_dispatch_added_only"])

    def test_hermes_state_added_and_transient_diagnostics_never_pass(self):
        self.jobs[3]["state"] = "scheduled"
        self.save_store()
        categories = []
        with self.assertRaises(m.Blocked):
            self.inspect(diagnostics=categories)
        self.assertEqual(categories, ["state_added_only"])
        self.hashes["job_sha"] = m.gate_module()._fingerprint(self.jobs[3])
        self.jobs[3]["state"] = "running"
        self.save_store()
        categories = []
        with self.assertRaises(m.Blocked):
            self.inspect(diagnostics=categories)
        self.assertEqual(categories, ["state_transient_only"])

    def test_hermes_paused_and_unbounded_fields_stay_unclassified(self):
        for state in ("paused", "completed", "malicious"):
            with self.subTest(state=state):
                self.jobs[3]["state"] = state
                self.save_store()
                categories = []
                with self.assertRaises(m.Blocked):
                    self.inspect(diagnostics=categories)
                self.assertEqual(categories, ["unclassified"])
                self.jobs[3].pop("state")
        self.jobs[3]["last_dispatch"] = {"secret": "SYNTHETIC_PRIVATE" * 300}
        self.save_store()
        categories = []
        with self.assertRaises(m.Blocked):
            self.inspect(diagnostics=categories)
        self.assertEqual(categories, ["unclassified"])
        self.assertNotIn("SYNTHETIC_PRIVATE", repr(categories))

    def test_hermes_definition_change_not_hidden_by_metadata_probe(self):
        self.jobs[3]["last_dispatch"] = {"kind": "late"}
        self.jobs[3]["schedule"]["display"] = "different"
        self.jobs[3]["prompt"] = "SYNTHETIC_SECRET_NEVER_PRINT"
        self.save_store()
        categories = []
        with self.assertRaises(m.Blocked) as raised:
            self.inspect(diagnostics=categories)
        self.assertEqual(str(raised.exception), "autumn_job_identity_drift")
        self.assertEqual(categories, ["unclassified"])
        self.assertNotIn("SYNTHETIC_SECRET_NEVER_PRINT", repr(categories))
        self.jobs[3]["deliver"] = "telegram"
        self.save_store()
        categories = []
        with self.assertRaises(m.Blocked) as raised:
            self.inspect(diagnostics=categories)
        self.assertEqual(str(raised.exception),
                         "autumn_job_binding_or_delivery_invalid")
        self.assertEqual(categories, [])

    def test_hermes_three_scheduler_mutations_are_not_auto_approved(self):
        self.jobs[3]["run_count"] = 2
        self.jobs[3]["last_dispatch"] = {"kind": "on_time"}
        self.jobs[3]["pending_slot"] = {"at": "sample"}
        self.save_store()
        categories = []
        with self.assertRaises(m.Blocked):
            self.inspect(diagnostics=categories)
        self.assertEqual(categories, ["unclassified"])

    def test_frozen_job_definition_digest_must_match(self):
        self.hashes["job_sha"] = "0" * 64
        self.block("autumn_job_identity_drift")

    def test_exact_target_mode_required(self):
        self.target.chmod(0o755)
        self.block("deployed_target_mode_invalid")

    def test_legacy_schedule_must_remain_disabled(self):
        self.jobs[0]["enabled"] = True
        self.save_store()
        self.block("legacy_schedule_not_disabled_or_ambiguous")

    def test_no_duplicate_or_retimed_11h(self):
        self.jobs.append(dict(self.jobs[3], id="extra", name="other"))
        self.save_store()
        self.block("autumn_job_missing_or_duplicate")
        self.jobs.pop()
        self.jobs[3]["schedule"]["expr"] = "0 10 * * *"
        self.save_store()
        self.block("autumn_job_binding_or_delivery_invalid")

    def test_refuse_nonlocal_delivery_and_extra_watering_job(self):
        self.jobs[3]["deliver"] = "telegram"
        self.save_store()
        self.block("autumn_job_binding_or_delivery_invalid")
        self.jobs[3]["deliver"] = "local"
        self.jobs.append(job("extra", "30 12 * * *", "balcony-watering-autumn"))
        self.save_store()
        self.block("autumn_job_missing_or_duplicate")

    def test_reject_wrapper_and_target_hash_drift(self):
        self.wrapper.write_text('#!/bin/bash\nexit 0\n')
        self.block("wrapper_sha_drift")
        self.wrapper.write_text('#!/bin/bash\nexec "$HOME/.hermes/scripts/balcony-watering-autumn.sh"\n')
        self.target.write_bytes(OLD + b"modified")
        self.block("deployed_target_sha_drift")

    def test_reject_unsafe_wrapper_and_target(self):
        self.wrapper.chmod(0o666)
        self.block("file_writable_by_others")
        self.wrapper.chmod(0o644)
        self.target.unlink()
        self.target.symlink_to(self.source)
        self.block("path_symlink_or_escape")

    def test_reject_candidate_source_change(self):
        self.source.write_bytes(CANDIDATE + b"unexpected")
        self.block("candidate_sha_drift")

    def test_reject_candidate_sensor_policy_change_even_if_hash_approved(self):
        changed = CANDIDATE.replace(b"8 9 10 11 12 13", b"8 9 10 12 13")
        self.source.write_bytes(changed)
        self.hashes["candidate_sha"] = m.digest(changed)
        self.block("candidate_policy_unreviewed")

    def test_reject_direct_telegram_bot_source(self):
        self.bot.write_bytes(b"api.telegram.org\n")
        self.block("bot_source_route_unreviewed")

    def test_reject_invalid_store_without_raw_leak(self):
        self.jobs[3]["prompt"] = "SECRET_SYNTHETIC"
        self.save_store()
        # This test changes the frozen definition intentionally; repin only
        # the synthetic test fingerprint to test privacy, not deployment.
        self.hashes["job_sha"] = m.gate_module()._fingerprint(self.jobs[3])
        self.assertNotIn("SECRET_SYNTHETIC", json.dumps(self.inspect()))
        self.store.write_text("{not json")
        self.block("hermes_store_invalid")

    def test_reject_ambiguous_or_unsafe_wrapper_reference(self):
        # A revised wrapper is not an authorized target even when its digest
        # is supplied as a test value.
        self.wrapper.write_text('#!/bin/bash\nexec "$HOME/.hermes/scripts/other"\n')
        self.hashes["wrapper_sha"] = m.digest(self.wrapper.read_bytes())
        self.block("wrapper_referent_ambiguous")


if __name__ == "__main__":
    unittest.main()
