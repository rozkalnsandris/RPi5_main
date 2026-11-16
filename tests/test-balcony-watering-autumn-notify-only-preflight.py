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
from unittest import mock

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



    def enable_strict_script_only(self):
        # Synthetic fixture: does not touch the real RPi5/Hermes store.
        self.jobs[3].update({
            "no_agent": True, "timezone": "Europe/Berlin",
            "grace_minutes": 0, "state": "scheduled",
        })
        self.save_store()

    def test_script_only_ignores_bounded_scheduler_runtime_changes(self):
        self.enable_strict_script_only()
        self.jobs[3]["run_count"] = 12
        self.jobs[3]["repeat"] = {"times": None, "completed": 12}
        self.jobs[3]["last_dispatch"] = {"kind": "on_time", "at": "synthetic"}
        self.jobs[3]["last_run_at"] = "synthetic"
        self.jobs[3]["last_status"] = "ok"
        self.save_store()
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns)
                  for p in (self.store, self.wrapper, self.target, self.source, self.bot)}
        result = self.inspect()
        self.assertEqual(result["result"], "SOURCE_NOTIFY_ONLY_PREFLIGHT_PASS")
        self.assertEqual(result["identity_mode"], "strict_script_only")
        self.assertTrue(result["script_only_contract_verified"])
        self.assertNotEqual(result["job_definition_sha256"], self.hashes["job_sha"])
        self.assertFalse(result["live_apply_authorized"])
        self.assertFalse(result["writes_performed"])
        self.assertFalse(result["mutation_started"])
        self.assertFalse(result["raw_payload_emitted"])
        for file, state in before.items():
            self.assertEqual((file.read_bytes(), file.stat().st_mtime_ns), state)

    def test_pinned_legacy_identity_reports_backward_compatible_mode(self):
        result = self.inspect()
        self.assertEqual(result["identity_mode"], "pinned_legacy")
        self.assertFalse(result["script_only_contract_verified"])
        self.assertEqual(result["job_definition_sha256"], self.hashes["job_sha"])

    def test_script_only_wrong_no_agent_prompt_clock_or_state_stays_blocked(self):
        self.enable_strict_script_only()
        for field, changes in (
            ("no_agent", (False, None, "true")),
            ("prompt", ("PRIVATE_SYNTHETIC_LLM_PROMPT", None)),
            ("timezone", (None, "UTC", "Europe/Paris")),
            ("grace_minutes", (None, 1, True)),
            ("state", ("running", "paused", "completed")),
            ("repeat", ({"times": 1, "completed": 0},
                        {"times": None, "completed": True})),
            ("skills", (["PRIVATE_SYNTHETIC_SKILL"],)),
            ("model", ("PRIVATE_SYNTHETIC_MODEL",)),
            ("provider", ("PRIVATE_SYNTHETIC_PROVIDER",)),
            ("monitor_script", ("PRIVATE_SYNTHETIC_COMMAND",)),
            ("pending_slot", ({"at": "now"},)),
            ("fire_claim", ({"at": "now"},)),
            ("unknown_field", ("PRIVATE_SYNTHETIC_UNREVIEWED",)),
        ):
            original = self.jobs[3].get(field, object())
            for change in changes:
                with self.subTest(field=field, change_type=type(change).__name__):
                    self.jobs[3][field] = change
                    self.save_store()
                    self.block("autumn_job_identity_drift")
                    self.assertNotIn("PRIVATE_SYNTHETIC", str(self.jobs[3].get("id")))
            if field in ("no_agent", "prompt", "timezone", "grace_minutes", "state"):
                self.jobs[3][field] = {
                    "no_agent": True, "prompt": "", "timezone": "Europe/Berlin",
                    "grace_minutes": 0, "state": "scheduled",
                }[field]
            else:
                self.jobs[3].pop(field, None)
            self.save_store()

    def test_script_only_schedule_and_wrapper_drift_still_fail_closed(self):
        self.enable_strict_script_only()
        self.jobs[3]["schedule"]["display"] = "0 10 * * *"
        self.save_store()
        self.block("autumn_job_identity_drift")
        self.jobs[3]["schedule"] = {
            "kind": "cron", "expr": "0 11 * * *", "display": "0 11 * * *"
        }
        self.save_store()
        self.assertEqual(self.inspect()["identity_mode"], "strict_script_only")
        self.wrapper.write_text("#!/bin/bash\nexit 0\n")
        self.block("wrapper_sha_drift")

    def test_script_only_rejects_controller_sensor_and_route_drift(self):
        self.enable_strict_script_only()
        self.target.write_bytes(OLD + b"changed")
        self.block("deployed_target_sha_drift")
        self.target.write_bytes(OLD)
        self.source.write_bytes(CANDIDATE + b"tampered")
        self.block("candidate_sha_drift")
        self.source.write_bytes(CANDIDATE)
        self.bot.write_bytes(b"PRIVATE_SYNTHETIC_WRONG_ROUTE")
        self.block("bot_source_route_unreviewed")

    def test_script_only_rejects_hidden_watering_job_and_legacy_reactivation(self):
        self.enable_strict_script_only()
        self.jobs.append(job("extra", "0 12 * * *", "balcony-watering-autumn"))
        self.save_store()
        self.block("autumn_job_missing_or_duplicate")
        self.jobs.pop()
        self.jobs[0]["enabled"] = True
        self.save_store()
        self.block("legacy_schedule_not_disabled_or_ambiguous")

    def test_script_only_bounded_metadata_and_private_value_never_leak(self):
        self.enable_strict_script_only()
        for key, value in (
            ("run_count", True),
            ("run_count", 1_000_001),
            ("last_dispatch", "PRIVATE_SYNTHETIC"),
            ("last_dispatch", {"private": "PRIVATE_SYNTHETIC" * 1000}),
            ("execution_skipped", "PRIVATE_SYNTHETIC"),
        ):
            self.jobs[3][key] = value
            self.save_store()
            with self.assertRaises(m.Blocked) as raised:
                self.inspect()
            self.assertEqual(str(raised.exception), "autumn_job_identity_drift")
            self.assertNotIn("PRIVATE_SYNTHETIC", str(raised.exception))
            self.jobs[3].pop(key, None)


# Pure source-only comparator; production Gate-1 and install gates stay intact.
COMPARE_SCRIPT = ROOT / "ops/lib/balcony_autumn_definition_compare.py"
compare_loader = importlib.machinery.SourceFileLoader(
    "balcony_compare_1509", str(COMPARE_SCRIPT)
)
compare_spec = importlib.util.spec_from_loader(compare_loader.name, compare_loader)
assert compare_spec is not None
comparison = importlib.util.module_from_spec(compare_spec)
compare_loader.exec_module(comparison)


class VerifiedDefinitionComparisonTests(unittest.TestCase):
    def setUp(self):
        self.before = {
            "id": "private-synthetic-identifier",
            "name": "private-synthetic-name",
            "enabled": True,
            "deliver": "local",
            "script": "PRIVATE_SYNTHETIC_SCRIPT_BODY",
            "prompt": "PRIVATE_SYNTHETIC_PROMPT",
            "schedule": {"kind": "cron", "expr": "0 11 * * *"},
        }
        self.after = json.loads(json.dumps(self.before))
        original = m.gate_module()._fingerprint(self.before)
        self.patch = mock.patch.object(comparison, "FROZEN_REFERENCE_SHA256",
                                       original)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def assert_blocked_sanitized(self, report):
        self.assertEqual(report["result"], "BLOCKED")
        self.assertFalse(report["live_apply_authorized"])
        self.assertFalse(report["mutation_started"])
        self.assertFalse(report["writes_performed"])
        self.assertFalse(report["raw_payload_emitted"])
        text = json.dumps(report, sort_keys=True)
        for prohibited in ("PRIVATE_SYNTHETIC", "private-synthetic",
                           "0 11 * * *", "script_sha256", "PRIVATE"):
            self.assertNotIn(prohibited, text)
        self.assertLess(len(text), 2048)

    def test_reference_unavailable_is_not_inferred_from_sha(self):
        report = comparison.compare_verified_definitions(None, self.after)
        self.assert_blocked_sanitized(report)
        self.assertEqual(report["reason"], "verified_reference_unavailable")
        self.assertEqual(report["changed_definition_categories"], [])

    def test_observed_missing_still_blocks(self):
        report = comparison.compare_verified_definitions(self.before, None)
        self.assert_blocked_sanitized(report)
        self.assertEqual(report["reason"], "observed_definition_unavailable")

    def test_unauthenticated_reference_rejected_before_any_diff(self):
        self.before["prompt"] = "PRIVATE_CHANGED"
        report = comparison.compare_verified_definitions(self.before, self.after)
        self.assert_blocked_sanitized(report)
        self.assertEqual(report["reason"], "reference_fingerprint_mismatch")
        self.assertFalse(report["reference_fingerprint_verified"])
        self.assertEqual(report["changed_definition_categories"], [])

    def test_verified_equal_definition_still_blocked(self):
        report = comparison.compare_verified_definitions(self.before, self.after)
        self.assert_blocked_sanitized(report)
        self.assertTrue(report["reference_fingerprint_verified"])
        self.assertEqual(report["reason"], "definition_fingerprint_unchanged")
        self.assertEqual(report["changed_definition_categories"], [])

    def test_sensitive_binding_changes_report_categories_only(self):
        self.after["script"] = "PRIVATE_SYNTHETIC_NEW_SCRIPT_BODY"
        self.after["prompt"] = "PRIVATE_SYNTHETIC_NEW_PROMPT"
        self.after["deliver"] = "PRIVATE_SYNTHETIC_CHAT_ID"
        self.after["schedule"]["expr"] = "0 12 * * *"
        report = comparison.compare_verified_definitions(self.before, self.after)
        self.assert_blocked_sanitized(report)
        self.assertEqual(report["reason"], "definition_difference_categorized")
        self.assertEqual(report["changed_definition_categories"],
                         ["delivery_binding", "prompt_definition",
                          "schedule_contract", "script_binding"])

    def test_hermes_scheduler_field_categories_never_authorize(self):
        self.after["run_count"] = 2
        self.after["state"] = "running"
        self.after["last_dispatch"] = {"opaque": "PRIVATE_SYNTHETIC"}
        self.after["pending_slot"] = {"opaque": "PRIVATE_SYNTHETIC"}
        report = comparison.compare_verified_definitions(self.before, self.after)
        self.assert_blocked_sanitized(report)
        self.assertEqual(report["changed_definition_categories"],
                         ["hermes_last_dispatch", "hermes_pending_slot",
                          "hermes_run_count", "hermes_scheduler_state"])

    def test_unknown_definition_key_never_echoed(self):
        self.after["PRIVATE_SYNTHETIC_ARBITRARY_KEY"] = "PRIVATE_SYNTHETIC"
        report = comparison.compare_verified_definitions(self.before, self.after)
        self.assert_blocked_sanitized(report)
        self.assertEqual(report["changed_definition_categories"],
                         ["other_definition_fields"])

    def test_transient_fields_excluded_by_gate_cannot_force_pass(self):
        self.after["last_status"] = "PRIVATE_SYNTHETIC"
        self.after["next_run_at"] = "PRIVATE_SYNTHETIC"
        report = comparison.compare_verified_definitions(self.before, self.after)
        self.assert_blocked_sanitized(report)
        self.assertEqual(report["reason"], "definition_fingerprint_unchanged")
        self.assertEqual(report["changed_definition_categories"], [])

    def test_invalid_or_excessive_inputs_are_blocked_with_no_leak(self):
        bad = ([], True, {"blob": float("nan")},
               {"blob": "PRIVATE_SYNTHETIC" * 10_000},
               {str(i): i for i in range(100)})
        for value in bad:
            with self.subTest(value_type=type(value).__name__):
                report = comparison.compare_verified_definitions(self.before,
                                                                  value)
                self.assert_blocked_sanitized(report)
                self.assertEqual(report["reason"], "unreviewed_definition_shape")

    def test_reference_checksum_never_dynamically_repinned(self):
        with mock.patch.object(comparison, "FROZEN_REFERENCE_SHA256",
                               "0" * 64):
            report = comparison.compare_verified_definitions(self.before,
                                                              self.after)
        self.assert_blocked_sanitized(report)
        self.assertEqual(report["reason"], "reference_fingerprint_mismatch")

    def test_module_is_pure_offline_and_has_no_cli(self):
        source = COMPARE_SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("jobs.json", "subprocess", "requests.", "urllib.",
                          "socket.", "os.system", "mqtt", "telegram",
                          "open(", "read_bytes(", "write_text(",
                          "if __name__"):
            self.assertNotIn(forbidden, source)


# Independent forward-only validator (#1513): synthetic bindings only.
# No Hermes store access; the original preflight and operator are unchanged.
INDEPENDENT = ROOT / "ops/lib/balcony_autumn_independent_validator.py"
independent_loader = importlib.machinery.SourceFileLoader(
    "balcony_independent_1513", str(INDEPENDENT)
)
independent_spec = importlib.util.spec_from_loader(
    independent_loader.name, independent_loader
)
assert independent_spec is not None
independent = importlib.util.module_from_spec(independent_spec)
independent_loader.exec_module(independent)


class IndependentCurrentJobContractTests(unittest.TestCase):
    def setUp(self):
        self.jobs = [
            job("legacy-seven", "0 7 * * *", "synthetic-old-a",
                deliver="telegram"),
            job("legacy-fourteen", "0 14 * * *", "synthetic-heat",
                deliver="telegram"),
            job("legacy-twenty-three", "0 23 * * *", "synthetic-old-b",
                deliver="telegram"),
            job("autumn-eleven", "0 11 * * *", "synthetic-reviewed-wrapper",
                enabled=True, deliver="local"),
            job("other-task", "0 10 * * *", "unrelated-task"),
        ]
        self.jobs[3]["timezone"] = "Europe/Berlin"
        self.jobs[3]["grace_minutes"] = 15
        self.bindings = {}
        for slot, item in zip(independent.SLOTS, self.jobs):
            self.bindings[slot] = {
                "name": item["name"],
                "script_sha256": hashlib.sha256(
                    item["script"].encode("utf-8")
                ).hexdigest(),
                "prompt_sha256": hashlib.sha256(
                    item["prompt"].encode("utf-8")
                ).hexdigest(),
                "deliver": item["deliver"],
                "timezone": item.get("timezone"),
                "grace_minutes": item.get("grace_minutes"),
            }

    def assess(self):
        return independent.assess_jobs(self.jobs, bindings=self.bindings)

    def assert_blocked_private(self, result, reason, *, matched=False):
        self.assertEqual(result["result"], "BLOCKED")
        self.assertEqual(result["reason"], reason)
        self.assertIs(result["in_memory_contract_match"], matched)
        self.assertFalse(result["source_contract_independently_approved"])
        self.assertFalse(result["host_source_provenance_verified"])
        self.assertFalse(result["sensor_runtime_verified"])
        self.assertFalse(result["telegram_delivery_verified"])
        self.assertFalse(result["live_apply_authorized"])
        self.assertFalse(result["writes_performed"])
        self.assertFalse(result["mutation_started"])
        self.assertFalse(result["raw_payload_emitted"])
        rendered = json.dumps(result, sort_keys=True)
        self.assertLess(len(rendered), 1200)
        for private in (
            "synthetic-reviewed-wrapper", "legacy-seven",
            "Europe/Berlin", self.bindings["autumn_1100"]["script_sha256"],
            "private-synthetic-token", "SECRET_SYNTHETIC",
        ):
            self.assertNotIn(private, rendered)

    def test_no_production_contract_stays_blocked(self):
        self.assertIsNone(independent.PRODUCTION_BINDINGS)
        report = independent.assess_jobs(self.jobs)
        self.assert_blocked_private(report, "independent_source_contract_missing")

    def test_synthetic_exact_contract_match_is_still_blocked(self):
        self.assert_blocked_private(
            self.assess(), "in_memory_contract_match_not_authorized",
            matched=True,
        )

    def test_missing_or_malformed_expected_bindings_refused(self):
        self.bindings.pop("legacy_0700")
        self.assert_blocked_private(
            self.assess(), "independent_source_contract_invalid"
        )
        self.bindings["legacy_0700"] = dict(self.bindings["legacy_1400"])
        self.assert_blocked_private(
            self.assess(), "independent_source_contract_invalid"
        )
        self.bindings["legacy_0700"]["name"] = "legacy-seven"
        self.bindings["legacy_0700"]["script_sha256"] = "not-a-digest"
        self.assert_blocked_private(
            self.assess(), "independent_source_contract_invalid"
        )

    def test_any_watering_binding_change_stays_blocked(self):
        for field in ("script", "prompt"):
            with self.subTest(field=field):
                self.jobs[3][field] = "SECRET_SYNTHETIC_CHANGED"
                self.assert_blocked_private(
                    self.assess(), "script_or_prompt_binding_mismatch"
                )
                self.jobs[3][field] = (
                    "synthetic-reviewed-wrapper" if field == "script" else ""
                )
        self.jobs[0]["script"] = "synthetic-different-legacy-command"
        self.assert_blocked_private(
            self.assess(), "script_or_prompt_binding_mismatch"
        )

    def test_wrong_legacy_enabled_and_11h_delivery_refused(self):
        self.jobs[0]["enabled"] = True
        self.assert_blocked_private(self.assess(), "enabled_status_mismatch")
        self.jobs[0]["enabled"] = False
        self.jobs[3]["deliver"] = "telegram"
        self.assert_blocked_private(self.assess(), "delivery_contract_mismatch")

    def test_wrong_schedule_and_time_contract_refused(self):
        self.jobs[3]["schedule"]["expr"] = "0 10 * * *"
        self.assert_blocked_private(self.assess(), "schedule_contract_mismatch")
        self.jobs[3]["schedule"]["expr"] = "0 11 * * *"
        self.jobs[3]["schedule"]["extra"] = "SECRET_SYNTHETIC"
        self.assert_blocked_private(self.assess(), "schedule_contract_mismatch")
        self.jobs[3]["schedule"].pop("extra")
        self.jobs[3]["timezone"] = "UTC"
        self.assert_blocked_private(self.assess(), "time_contract_mismatch")
        self.jobs[3]["timezone"] = "Europe/Berlin"
        self.jobs[3]["grace_minutes"] = 16
        self.assert_blocked_private(self.assess(), "time_contract_mismatch")

    def test_unknown_or_active_scheduler_state_refused(self):
        for state in ("running", "paused", "completed", "unknown", None):
            with self.subTest(state=state):
                self.jobs[3]["state"] = state
                self.assert_blocked_private(
                    self.assess(), "scheduler_state_unreviewed"
                )
        self.jobs[3]["state"] = "scheduled"
        self.assert_blocked_private(
            self.assess(), "in_memory_contract_match_not_authorized",
            matched=True,
        )

    def test_bookkeeping_is_bounded_and_pending_slot_never_ignored(self):
        self.jobs[3]["run_count"] = 8
        self.jobs[3]["next_run_at"] = "synthetic-time"
        self.jobs[3]["last_dispatch"] = {
            "kind": "on_time", "at": "synthetic-time"
        }
        self.assert_blocked_private(
            self.assess(), "in_memory_contract_match_not_authorized",
            matched=True,
        )
        self.jobs[3]["run_count"] = True
        self.assert_blocked_private(
            self.assess(), "scheduler_metadata_unreviewed"
        )
        self.jobs[3]["run_count"] = 8
        self.jobs[3]["pending_slot"] = {"at": "soon", "by": "scheduler"}
        self.assert_blocked_private(
            self.assess(), "scheduler_metadata_unreviewed"
        )
        self.jobs[3].pop("pending_slot")
        self.jobs[3]["last_dispatch"]["unexpected"] = "PRIVATE"
        self.assert_blocked_private(
            self.assess(), "scheduler_metadata_unreviewed"
        )

    def test_duplicate_missing_and_unexpected_watering_candidate(self):
        self.jobs.append(dict(self.jobs[3], id="distinct-id"))
        self.assert_blocked_private(
            self.assess(), "required_slot_missing_or_duplicate"
        )
        self.jobs.pop()
        self.jobs[3]["id"] = self.jobs[0]["id"]
        self.assert_blocked_private(self.assess(), "duplicate_job_identity")
        self.jobs[3]["id"] = "autumn-eleven"
        self.jobs[3]["name"] = "missing"
        self.assert_blocked_private(
            self.assess(), "required_slot_missing_or_duplicate"
        )
        self.jobs[3]["name"] = "autumn-eleven"
        self.jobs.append(job("unexpected-job", "0 12 * * *",
                             "balcony-watering-autumn"))
        self.assert_blocked_private(
            self.assess(), "unexpected_watering_candidate"
        )

    def test_injection_unknown_fields_unbounded_and_malformed_rejected(self):
        self.jobs[3]["SECRET_SYNTHETIC_UNREVIEWED_KEY"] = "private-synthetic-token"
        self.assert_blocked_private(
            self.assess(), "unreviewed_definition_field"
        )
        self.jobs[3].pop("SECRET_SYNTHETIC_UNREVIEWED_KEY")
        self.jobs[3]["repeat"] = {"times": 2, "completed": 1}
        self.assert_blocked_private(
            self.assess(), "unreviewed_definition_field"
        )
        self.jobs[3].pop("repeat")
        self.jobs[3]["script"] = "SECRET_SYNTHETIC" * 10_000
        self.assert_blocked_private(
            self.assess(), "unreviewed_job_collection"
        )
        self.jobs[3]["script"] = "synthetic-reviewed-wrapper"
        self.jobs[3]["prompt"] = float("nan")
        self.assert_blocked_private(
            self.assess(), "unreviewed_job_collection"
        )
        self.jobs[3]["prompt"] = ""
        report = independent.assess_jobs([], bindings=self.bindings)
        self.assert_blocked_private(report, "unreviewed_job_collection")

    def test_module_no_host_file_cli_network_or_controller_side_effect(self):
        source = INDEPENDENT.read_text(encoding="utf-8")
        for forbidden in ("subprocess", "urllib.", "socket.",
                          "os.system", "pathlib", "read_bytes(",
                          "write_text(", "open(", "if __name__",
                          "controller.apply", "mqtt.publish", "requests."):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("import os", source)
        self.assertNotIn("JOB_SHA256 =", source)
        self.assertNotIn("c3609b09eb842f73d8fc78e8828fd350838be9f7453adfcfd6855c56d09c1140",
                         source)

if __name__ == "__main__":
    unittest.main()
