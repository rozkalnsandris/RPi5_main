#!/usr/bin/env python3
"""Offline fail-closed replacement tests for Ausmalwiese household WAF."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "replace-ausmalwiese-goatcounter-household-waf-v1.py"
spec = importlib.util.spec_from_file_location("household_waf_replace", SCRIPT)
op = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(op)

CANDIDATE = "f" * 40
SOURCE = b"#!/usr/bin/env python3\n" + b"x" * 22000


class Runner:
    def __init__(self, fail_at=0, missing_staging=True, old_digest=True):
        self.calls = []
        self.mutations = 0
        self.fail_at = fail_at
        self.missing_staging = missing_staging
        self.live_operator_digest = (
            op.OLD_OPERATOR_SHA if old_digest else "0" * 64
        )
        self.live_release_digest = op.OLD_RELEASE_SHA
        self.candidate_digest = hashlib.sha256(SOURCE).hexdigest()
        self.release_digest = hashlib.sha256(
            op.metadata_for(CANDIDATE, SOURCE)
        ).hexdigest()

    def __call__(
        self,
        args,
        *,
        input=None,
        stdout=None,
        stderr=None,
        check=False,
    ):
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
            else:
                rc = 5
        elif command == op.SHA256SUM:
            path = args[-1]
            digest = {
                op.TARGET: self.live_operator_digest,
                op.RELEASE: self.live_release_digest,
                op.STAGE_OPERATOR: self.candidate_digest,
                op.STAGE_RELEASE: self.release_digest,
            }[path]
            text = f"{digest}  {path}"
        elif command == op.TEST:
            rc = 1 if self.missing_staging else 0
        elif command == op.TRUE:
            pass
        elif command in (op.INSTALL, op.MV):
            self.mutations += 1
            if self.mutations == self.fail_at:
                rc = 2
            elif command == op.MV and args[-2:] == [op.STAGE_OPERATOR, op.TARGET]:
                self.live_operator_digest = self.candidate_digest
            elif command == op.MV and args[-2:] == [op.STAGE_RELEASE, op.RELEASE]:
                self.live_release_digest = self.release_digest
        else:
            rc = 9

        return subprocess.CompletedProcess(
            args,
            rc,
            stdout=text.encode(),
            stderr=b"",
        )


class ReplaceTests(unittest.TestCase):
    def test_fixed_incumbent_identity_and_non_secret_scope(self):
        self.assertEqual(
            op.OLD_MAIN,
            "6abc94ded6b1737beb322ee09ef19c57f1e95794",
        )
        self.assertEqual(
            op.OLD_OPERATOR_SHA,
            "7ebc7b3e6e79a60334242f2258e11abcef266a063899e7a69ec0f794a9bd59e8",
        )
        self.assertEqual(
            op.OLD_RELEASE_SHA,
            "3ed4805405a5767faf79fea0aef2bb0c0f33a05646532e32a3d50dd9b6f66889",
        )
        text = SCRIPT.read_text("utf-8")
        self.assertNotIn("zone-waf-writer.json", text)
        self.assertNotIn("/etc/rpi5-secrets", text)
        self.assertNotIn("api.cloudflare.com", text)
        self.assertNotIn("shell=True", text)
        self.assertNotIn("/usr/bin/rm", text)
        self.assertNotIn("/bin/bash", text)

    def test_metadata_pins_candidate_main_and_operator_digest(self):
        obj = json.loads(op.metadata_for(CANDIDATE, SOURCE))
        self.assertEqual(obj, {
            "source_sha": CANDIDATE,
            "operator_sha256": hashlib.sha256(SOURCE).hexdigest(),
        })

    def test_candidate_cannot_equal_incumbent_release(self):
        with mock.patch.object(op.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(op.ReplaceError, "invalid_candidate_main"):
                op.source_bytes(op.OLD_MAIN, runner=Runner())

    def test_preflight_rejects_incumbent_drift_and_existing_staging(self):
        for runner in (
            Runner(old_digest=False),
            Runner(missing_staging=False),
        ):
            with self.subTest(runner=runner):
                with mock.patch.object(op, "source_bytes", return_value=SOURCE):
                    with self.assertRaises(op.ReplaceError):
                        op.preflight(CANDIDATE, runner=runner)
                self.assertEqual(runner.mutations, 0)

    def test_success_stages_verifies_rechecks_then_fixed_renames(self):
        r = Runner()
        with mock.patch.object(op, "source_bytes", return_value=SOURCE):
            op.replace(CANDIDATE, runner=r)

        writes = [
            (args, payload)
            for args, payload in r.calls
            if args[:3] in (
                [op.SUDO, "-n", op.INSTALL],
                [op.SUDO, "-n", op.MV],
            )
        ]
        self.assertEqual(len(writes), 4)
        self.assertEqual(
            writes[0][0][-2:],
            ["/dev/stdin", op.STAGE_OPERATOR],
        )
        self.assertEqual(writes[0][1], SOURCE)
        self.assertEqual(
            writes[1][0][-2:],
            ["/dev/stdin", op.STAGE_RELEASE],
        )
        self.assertEqual(writes[1][1], op.metadata_for(CANDIDATE, SOURCE))
        self.assertEqual(
            writes[2][0],
            [op.SUDO, "-n", op.MV, "-T", "--", op.STAGE_OPERATOR, op.TARGET],
        )
        self.assertEqual(
            writes[3][0],
            [op.SUDO, "-n", op.MV, "-T", "--", op.STAGE_RELEASE, op.RELEASE],
        )
        self.assertEqual(r.live_operator_digest, r.candidate_digest)
        self.assertEqual(r.live_release_digest, r.release_digest)

        first_mv = next(
            i
            for i, (args, _) in enumerate(r.calls)
            if args[:3] == [op.SUDO, "-n", op.MV]
        )
        checked = [
            args[-1]
            for args, _ in r.calls[:first_mv]
            if args[:3] == [op.SUDO, "-n", op.SHA256SUM]
        ]
        self.assertEqual(
            checked[-4:],
            [op.STAGE_OPERATOR, op.STAGE_RELEASE, op.TARGET, op.RELEASE],
        )

    def test_only_fixed_install_and_mv_are_privileged_mutations(self):
        r = Runner()
        with mock.patch.object(op, "source_bytes", return_value=SOURCE):
            op.replace(CANDIDATE, runner=r)
        mutation_commands = [
            args[2]
            for args, _ in r.calls
            if args[:2] == [op.SUDO, "-n"]
            and args[2] in (op.INSTALL, op.MV)
        ]
        self.assertEqual(
            mutation_commands,
            [op.INSTALL, op.INSTALL, op.MV, op.MV],
        )
        self.assertFalse(any(
            args[:3] in (
                [op.SUDO, "-n", "/usr/bin/python3"],
                [op.SUDO, "-n", "/bin/sh"],
                [op.SUDO, "-n", "/bin/bash"],
            )
            for args, _ in r.calls
        ))

    def test_every_root_mutation_failure_stops_without_retry_or_cleanup(self):
        for n in range(1, 5):
            r = Runner(fail_at=n)
            with self.subTest(n=n):
                with mock.patch.object(op, "source_bytes", return_value=SOURCE):
                    with self.assertRaisesRegex(
                        op.ReplaceError,
                        "post_dispatch_unknown_state",
                    ):
                        op.replace(CANDIDATE, runner=r)
                self.assertEqual(r.mutations, n)
                self.assertFalse(any(
                    args[:3] == [op.SUDO, "-n", "/usr/bin/rm"]
                    for args, _ in r.calls
                ))

    def test_read_failure_after_first_stage_is_terminal_unknown(self):
        class ReadFailRunner(Runner):
            def __call__(self, args, **kwargs):
                result = super().__call__(args, **kwargs)
                argv = list(args)
                command = argv[2] if argv[:2] == [op.SUDO, "-n"] else argv[0]
                if (
                    self.mutations >= 2
                    and command == op.SHA256SUM
                    and argv[-1] == op.STAGE_OPERATOR
                ):
                    return subprocess.CompletedProcess(
                        argv, 2, stdout=b"", stderr=b""
                    )
                return result

        r = ReadFailRunner()
        with mock.patch.object(op, "source_bytes", return_value=SOURCE):
            with self.assertRaisesRegex(
                op.ReplaceError,
                "post_dispatch_unknown_state",
            ):
                op.replace(CANDIDATE, runner=r)
        self.assertEqual(r.mutations, 2)

    def test_apply_requires_exact_confirmation(self):
        with mock.patch.object(
            op,
            "replace",
            side_effect=AssertionError("must not apply"),
        ):
            self.assertEqual(
                op.main(["--expected-main", CANDIDATE, "--apply"]),
                3,
            )
        self.assertEqual(
            op.CONFIRM,
            "REPLACE-AUSMALWIESE-HOUSEHOLD-WAF-RELEASE",
        )


if __name__ == "__main__":
    unittest.main()
