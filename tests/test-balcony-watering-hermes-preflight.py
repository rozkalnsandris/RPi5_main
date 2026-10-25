#!/usr/bin/env python3
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops/bin/balcony-watering-hermes-preflight"

loader = importlib.machinery.SourceFileLoader("balcony_watering_hermes_preflight", str(MODULE_PATH))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)


def job(job_id: str, name: str, expr: str, marker: str, **overrides):
    value = {
        "id": job_id,
        "name": name,
        "prompt": f"Run /private/{marker} with existing protected runtime wiring",
        "schedule": {"kind": "cron", "expr": expr, "display": expr},
        "deliver": "local",
        "enabled": True,
        "state": "scheduled",
        "repeat": {"times": None, "completed": 7},
        "next_run_at": "2026-10-26T07:00:00+01:00",
        "last_run_at": "2026-10-25T07:00:00+02:00",
        "last_status": "ok",
    }
    value.update(overrides)
    return value


def legacy_jobs():
    return [
        job("j07", "balcony morning", "0 7 * * *", "laistisana_2x.sh"),
        job("j14", "balcony heat", "0 14 * * *", "laistisana_2x_karstums.sh"),
        job("j23", "balcony night", "0 23 * * *", "laistisana_2x.sh"),
    ]


class HermesWateringPreflightTests(unittest.TestCase):
    def make_store(self, jobs=None, *, bare_list=False):
        temporary = tempfile.TemporaryDirectory(prefix="balcony-hermes-preflight-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "jobs.json"
        values = legacy_jobs() if jobs is None else jobs
        payload = values if bare_list else {
            "jobs": values,
            "updated_at": "2026-10-25T15:00:00+00:00",
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        path.chmod(0o600)
        return path

    def collect(self, jobs=None):
        path = self.make_store(jobs)
        return m.collect(store_path=path, expected_uid=os.geteuid())

    def test_valid_legacy_projection_passes_without_payload_disclosure(self):
        report = self.collect()
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["store"]["job_count"], 3)
        self.assertEqual(report["store"]["format"], "canonical_dict")
        self.assertEqual(report["autumn"], {"status": "absent", "count": 0})
        for slot, _expr, binding in m.LEGACY_SLOTS:
            self.assertEqual(report["legacy"][slot]["status"], "matched")
            self.assertEqual(report["legacy"][slot]["binding"], binding)
            self.assertTrue(report["legacy"][slot]["enabled"])
            self.assertTrue(report["legacy"][slot]["deliver_local"])
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn("/private/", rendered)
        self.assertNotIn("laistisana_2x.sh", rendered)
        self.assertFalse(report["mutation_started"])
        self.assertFalse(report["writes_performed"])
        self.assertFalse(report["store"]["raw_payload_emitted"])

    def test_legacy_bare_list_is_classified_without_mutation(self):
        path = self.make_store(bare_list=True)
        report = m.collect(store_path=path, expected_uid=os.geteuid())
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["store"]["format"], "legacy_bare_list")
        self.assertFalse(report["mutation_started"])
        self.assertFalse(report["writes_performed"])

    def test_unknown_canonical_store_shape_blocks(self):
        path = self.make_store()
        path.write_text(
            json.dumps({"jobs": legacy_jobs(), "updated_at": "x", "extra": True}),
            encoding="utf-8",
        )
        with self.assertRaises(m.PreflightError) as caught:
            m.collect(store_path=path, expected_uid=os.geteuid())
        self.assertEqual(caught.exception.code, "store_shape_invalid")

    def test_missing_and_duplicate_legacy_jobs_block(self):
        missing = self.collect(legacy_jobs()[1:])
        self.assertIn("legacy_0700_primary_missing", missing["blockers"])

        duplicate_jobs = legacy_jobs()
        duplicate_jobs.append(
            job("j07b", "balcony morning duplicate", "0 7 * * *", "balcony-watering-2x")
        )
        duplicate = self.collect(duplicate_jobs)
        self.assertIn("legacy_0700_primary_duplicate", duplicate["blockers"])

    def test_disabled_or_nonlocal_legacy_job_blocks(self):
        jobs = legacy_jobs()
        jobs[0]["enabled"] = False
        jobs[2]["deliver"] = "telegram"
        report = self.collect(jobs)
        self.assertIn("legacy_0700_primary_disabled", report["blockers"])
        self.assertIn("legacy_2300_primary_delivery_not_local", report["blockers"])

    def test_recognized_existing_autumn_job_is_reported_and_blocks_initial_create(self):
        jobs = legacy_jobs()
        jobs.append(
            {
                "id": "j11",
                "name": "balcony-watering-autumn",
                "script": "balcony-watering-autumn",
                "no_agent": True,
                "schedule": {"kind": "cron", "expr": "0 11 * * *", "display": "0 11 * * *"},
                "deliver": "local",
                "enabled": True,
                "state": "scheduled",
            }
        )
        report = self.collect(jobs)
        self.assertEqual(report["autumn"]["status"], "recognized_existing")
        self.assertIn("autumn_job_already_exists", report["blockers"])

    def test_unrecognized_existing_autumn_job_is_sanitized(self):
        secret = "DO_NOT_DISCLOSE_PRIVATE_COMMAND"
        jobs = legacy_jobs()
        jobs.append(
            {
                "id": "j11",
                "name": "balcony-watering-autumn",
                "prompt": secret,
                "schedule": {"kind": "cron", "expr": "0 11 * * *"},
                "deliver": "local",
                "enabled": True,
                "state": "scheduled",
            }
        )
        report = self.collect(jobs)
        self.assertEqual(report["autumn"]["status"], "unrecognized_existing")
        self.assertIn("autumn_job_unrecognized", report["blockers"])
        self.assertNotIn(secret, json.dumps(report, sort_keys=True))

    def test_unexpected_watering_candidate_blocks(self):
        jobs = legacy_jobs()
        jobs.append(
            job("other", "balkona watering extra", "30 12 * * *", "opaque-command")
        )
        report = self.collect(jobs)
        self.assertIn("unexpected_watering_job_candidate", report["blockers"])

    def test_unrelated_fingerprint_ignores_runtime_only_metadata(self):
        jobs = legacy_jobs()
        unrelated = {
            "id": "news",
            "name": "daily-news",
            "prompt": "private unrelated prompt",
            "schedule": {"kind": "cron", "expr": "5 8 * * *"},
            "deliver": "local",
            "enabled": True,
            "repeat": {"times": None, "completed": 2},
            "next_run_at": "2026-10-26T08:05:00+01:00",
            "last_run_at": "2026-10-25T08:05:00+02:00",
            "last_status": "ok",
        }
        jobs.append(unrelated)
        first = self.collect(jobs)["unrelated_definition_sha256"]

        changed = json.loads(json.dumps(jobs))
        changed[-1]["next_run_at"] = "2030-01-01T00:00:00Z"
        changed[-1]["last_run_at"] = "2030-01-01T00:00:01Z"
        changed[-1]["last_status"] = "failed"
        changed[-1]["repeat"]["completed"] = 999
        second = self.collect(changed)["unrelated_definition_sha256"]
        self.assertEqual(first, second)

        changed[-1]["deliver"] = "telegram"
        third = self.collect(changed)["unrelated_definition_sha256"]
        self.assertNotEqual(first, third)

    def test_duplicate_job_id_blocks(self):
        jobs = legacy_jobs()
        jobs[1]["id"] = jobs[0]["id"]
        path = self.make_store(jobs)
        with self.assertRaises(m.PreflightError) as caught:
            m.collect(store_path=path, expected_uid=os.geteuid())
        self.assertEqual(caught.exception.code, "job_id_duplicate")

    def test_duplicate_json_key_and_malformed_store_block(self):
        path = self.make_store()
        path.write_text('{"jobs":[{"id":"x","id":"y"}]}', encoding="utf-8")
        with self.assertRaises(m.PreflightError) as caught:
            m.collect(store_path=path, expected_uid=os.geteuid())
        self.assertEqual(caught.exception.code, "store_duplicate_json_key")

        path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(m.PreflightError) as caught:
            m.collect(store_path=path, expected_uid=os.geteuid())
        self.assertEqual(caught.exception.code, "store_json_invalid")

    def test_oversize_bad_mode_and_symlink_store_block(self):
        path = self.make_store()
        with mock.patch.object(m, "MAX_STORE_BYTES", 8):
            with self.assertRaises(m.PreflightError) as caught:
                m.collect(store_path=path, expected_uid=os.geteuid())
        self.assertEqual(caught.exception.code, "store_size_invalid")

        path.chmod(0o644)
        with self.assertRaises(m.PreflightError) as caught:
            m.collect(store_path=path, expected_uid=os.geteuid())
        self.assertEqual(caught.exception.code, "store_mode_invalid")

        target = self.make_store()
        link = target.parent / "jobs-link.json"
        link.symlink_to(target)
        with self.assertRaises(m.PreflightError) as caught:
            m.collect(store_path=link, expected_uid=os.geteuid())
        self.assertEqual(caught.exception.code, "store_unsafe")

    def test_preflight_source_has_no_mutation_or_command_execution_surface(self):
        text = MODULE_PATH.read_text(encoding="utf-8")
        for token in (
            "subprocess",
            "os.system",
            "write_text(",
            "write_bytes(",
            ".unlink(",
            "os.remove(",
            "os.rename(",
            "os.replace(",
            "hermes cron pause",
            "hermes cron resume",
            "hermes cron create",
            "hermes cron edit",
            "hermes cron remove",
            "hermes cron run",
            "hermes cron tick",
        ):
            self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main()
