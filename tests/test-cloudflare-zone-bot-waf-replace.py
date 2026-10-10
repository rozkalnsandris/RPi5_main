#!/usr/bin/env python3
"""Offline fail-closed replacement tests; never use sudo, Cloudflare, or real secrets."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/replace-cloudflare-zone-bot-waf.py"
spec = importlib.util.spec_from_file_location("zone_waf_replace", SCRIPT)
op = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(op)

CANDIDATE = "a" * 40
SOURCE = b"#!/usr/bin/env python3\n" + b"x" * 16000


class Runner:
    def __init__(self, fail_at=0, missing_staging=True, old_digest=True):
        self.calls = []
        self.mutations = 0
        self.fail_at = fail_at
        self.missing_staging = missing_staging
        self.old_digest = old_digest
        self.candidate_digest = hashlib.sha256(SOURCE).hexdigest()
        self.release_digest = hashlib.sha256(op.metadata(CANDIDATE, SOURCE)).hexdigest()

    def __call__(self, args, *, input=None, stdout=None, stderr=None, check=False):
        args = list(args)
        self.calls.append((args, input))
        command = args[2] if args[:2] == [op.SUDO, "-n"] else args[0]
        text, rc = "", 0
        if command == op.GIT:
            tail = args[3:]
            if tail == ["rev-parse", "--show-toplevel"]:
                text = str(op.ROOT)
            elif tail == ["symbolic-ref", "--quiet", "--short", "HEAD"]:
                text = "main"
            elif tail == ["rev-parse", "HEAD"]:
                text = CANDIDATE
            elif tail == ["status", "--porcelain=v1", "--untracked-files=all"]:
                text = ""
            elif tail == ["remote", "get-url", "origin"]:
                text = "https://github.com/rozkalnsandris/RPi5_main.git"
            elif tail == ["ls-files", "--error-unmatch", op.SOURCE_REL]:
                text = op.SOURCE_REL
            else:
                rc = 5
        elif command == op.STAT:
            path = args[-1]
            if path in op.ROOT_DIRS:
                text = "0:0:700:directory"
            elif path in (op.TARGET, op.STAGE_OPERATOR):
                text = "0:0:500:regular file"
            elif path in (op.RELEASE, op.STAGE_RELEASE):
                text = "0:0:400:regular file"
        elif command == op.SHA256SUM:
            path = args[-1]
            digest = {
                op.TARGET: op.OLD_OPERATOR_SHA if self.old_digest else "0" * 64,
                op.RELEASE: op.OLD_RELEASE_SHA,
                op.STAGE_OPERATOR: self.candidate_digest,
                op.STAGE_RELEASE: self.release_digest,
            }[path]
            text = f"{digest}  {path}"
        elif command == op.TEST:
            rc = 1 if self.missing_staging else 0
        elif command in (op.INSTALL, op.MV):
            self.mutations += 1
            if self.mutations == self.fail_at:
                rc = 2
        return subprocess.CompletedProcess(args, rc, stdout=text.encode(), stderr=b"")


class ReplaceTests(unittest.TestCase):
    def test_fixed_identity_and_non_secret_paths(self):
        self.assertEqual(op.OLD_MAIN, "861c1da26caba215ef05a1681a6bcd190641c43f")
        self.assertEqual(op.OLD_OPERATOR_SHA, "95adf48824f24a381b7691b078afbbe9948578e338dab69099848e42e4a61e42")
        self.assertEqual(op.OLD_RELEASE_SHA, "dd71c7ce33430c465af7ada9e15981c8e38c4c0e2d4d94b26e20786059782ccc")
        self.assertNotIn("zone-waf-writer.json", SCRIPT.read_text())
        self.assertNotIn("api.cloudflare.com", SCRIPT.read_text())
        self.assertNotIn("shell=True", SCRIPT.read_text())
        self.assertNotIn("/usr/bin/rm", SCRIPT.read_text())

    def test_metadata_pins_exact_main_and_operator_digest(self):
        obj = json.loads(op.metadata(CANDIDATE, SOURCE))
        self.assertEqual(obj, {"source_sha": CANDIDATE,
                               "operator_sha256": hashlib.sha256(SOURCE).hexdigest()})

    def test_success_stages_verifies_then_performs_two_fixed_renames(self):
        r = Runner()
        with mock.patch.object(op, "source_bytes", return_value=SOURCE):
            op.replace(CANDIDATE, runner=r)
        writes = [(args, payload) for args, payload in r.calls if
                  args[:3] in ([op.SUDO, "-n", op.INSTALL], [op.SUDO, "-n", op.MV])]
        self.assertEqual(len(writes), 4)
        self.assertEqual(writes[0][0][-2:], ["/dev/stdin", op.STAGE_OPERATOR])
        self.assertEqual(writes[0][1], SOURCE)
        self.assertEqual(writes[1][0][-2:], ["/dev/stdin", op.STAGE_RELEASE])
        self.assertEqual(writes[1][1], op.metadata(CANDIDATE, SOURCE))
        self.assertEqual(writes[2][0], [op.SUDO, "-n", op.MV, "-T", "--",
                                         op.STAGE_OPERATOR, op.TARGET])
        self.assertEqual(writes[3][0], [op.SUDO, "-n", op.MV, "-T", "--",
                                         op.STAGE_RELEASE, op.RELEASE])
        # Both incumbents and both staged digests must be read before the first rename.
        first_mv = next(i for i, (a, _) in enumerate(r.calls) if a[:3] == [op.SUDO, "-n", op.MV])
        checked = [a[-1] for a, _ in r.calls[:first_mv] if a[:3] == [op.SUDO, "-n", op.SHA256SUM]]
        self.assertEqual(checked[-4:], [op.STAGE_OPERATOR, op.STAGE_RELEASE, op.TARGET, op.RELEASE])

    def test_preflight_rejects_incumbent_drift_and_existing_staging(self):
        for runner in (Runner(old_digest=False), Runner(missing_staging=False)):
            with self.subTest(runner=runner):
                with mock.patch.object(op, "source_bytes", return_value=SOURCE):
                    with self.assertRaises(op.Stop):
                        op.preflight(CANDIDATE, runner=runner)
                self.assertEqual(runner.mutations, 0)

    def test_every_root_mutation_failure_stops_without_retry_or_cleanup(self):
        for n in range(1, 5):
            r = Runner(fail_at=n)
            with self.subTest(n=n):
                with mock.patch.object(op, "source_bytes", return_value=SOURCE):
                    with self.assertRaisesRegex(op.Stop, "mutation_outcome_unknown"):
                        op.replace(CANDIDATE, runner=r)
                self.assertEqual(r.mutations, n)
                self.assertFalse(any(a[:3] == [op.SUDO, "-n", "/usr/bin/rm"]
                                     for a, _ in r.calls))

    def test_apply_requires_exact_confirmation(self):
        with mock.patch.object(op, "replace", side_effect=AssertionError("must not apply")):
            self.assertEqual(op.main(["--expected-main", CANDIDATE, "--apply"]), 4)


if __name__ == "__main__":
    unittest.main()
