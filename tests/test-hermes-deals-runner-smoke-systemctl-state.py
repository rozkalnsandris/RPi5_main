#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor import hermes_deals_runner_smoke_broker_bootstrap as bootstrap_v1
from deploy_executor import hermes_deals_runner_smoke_broker_bootstrap_v2 as bootstrap_v2

V1_SOURCE_CONTRACT = ROOT / "ops/deploy/rpi5-main-runner-smoke-broker-bootstrap-source-trusted-checkout-bootstrap.json"
V2_SOURCE_CONTRACT = ROOT / "ops/deploy/rpi5-main-runner-smoke-broker-bootstrap-v2-source-trusted-checkout-bootstrap.json"
V2_HOST_CONTRACT = ROOT / "ops/deploy/hermes-deals-runner-smoke-broker-bootstrap-v2.json"
ENTRYPOINT = ROOT / "ops/bin/rpi5-hermes-deals-runner-smoke-broker-bootstrap"


class RunnerSmokeSystemctlStateTests(unittest.TestCase):
    def test_absent_fixed_socket_unit_normalizes_to_not_found(self) -> None:
        result = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr=(
                "Failed to get unit file state for "
                f"{bootstrap_v1.SOCKET_UNIT}: No such file or directory\n"
            ),
        )
        with mock.patch.object(bootstrap_v1.subprocess, "run", return_value=result) as run:
            self.assertEqual(
                bootstrap_v1._systemctl_state("is-enabled", bootstrap_v1.SOCKET_UNIT),
                "not-found",
            )
        run.assert_called_once()
        self.assertEqual(
            run.call_args.args[0],
            ["/usr/bin/systemctl", "is-enabled", bootstrap_v1.SOCKET_UNIT],
        )
        self.assertEqual(run.call_args.kwargs["env"]["LC_ALL"], "C.UTF-8")

    def test_unexpected_is_enabled_error_stays_fail_closed(self) -> None:
        result = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="Failed to connect to bus: No medium found\n",
        )
        with mock.patch.object(bootstrap_v1.subprocess, "run", return_value=result):
            with self.assertRaises(bootstrap_v1.RunnerSmokeBrokerBootstrapError):
                bootstrap_v1._systemctl_state("is-enabled", bootstrap_v1.SOCKET_UNIT)

    def test_v1_checkout_is_preserved_but_v2_is_the_only_current_authority(self) -> None:
        self.assertEqual(
            bootstrap_v1.TRUSTED_CHECKOUT_NAME,
            "RPi5_main-runner-smoke-broker-bootstrap-trusted",
        )
        self.assertEqual(
            bootstrap_v2.HISTORICAL_TRUSTED_CHECKOUT_NAME,
            bootstrap_v1.TRUSTED_CHECKOUT_NAME,
        )
        self.assertEqual(
            bootstrap_v2.TRUSTED_CHECKOUT_NAME,
            "RPi5_main-runner-smoke-broker-bootstrap-v2-trusted",
        )
        ready = bootstrap_v2.source_readiness()
        self.assertEqual(ready["checkout_isolation_issue"], 584)
        self.assertEqual(ready["trusted_checkout_name"], bootstrap_v2.TRUSTED_CHECKOUT_NAME)
        self.assertEqual(
            ready["historical_trusted_checkout_name"],
            bootstrap_v1.TRUSTED_CHECKOUT_NAME,
        )
        self.assertEqual(ready["source_delivery_contract"], str(bootstrap_v2.SOURCE_DELIVERY_CONTRACT))
        self.assertFalse(ready["source_merge_authorizes_live"])
        self.assertTrue(ready["rdc_no_new_privileges_must_remain"])

        entrypoint = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn("hermes_deals_runner_smoke_broker_bootstrap_v2", entrypoint)
        self.assertNotIn(
            "from deploy_executor.hermes_deals_runner_smoke_broker_bootstrap import (",
            entrypoint,
        )

        sha = "a" * 40
        with tempfile.TemporaryDirectory() as temp_dir:
            v2_checkout = Path(temp_dir) / bootstrap_v2.TRUSTED_CHECKOUT_NAME
            v2_checkout.mkdir()

            def fake_git(_: Path, *args: str) -> str:
                values = {
                    ("rev-parse", "--show-toplevel"): f"{v2_checkout.resolve()}\n",
                    ("config", "--get", "remote.origin.url"): f"{bootstrap_v2.REVIEWED_ORIGIN}\n",
                    ("rev-parse", "--abbrev-ref", "HEAD"): "HEAD\n",
                    ("status", "--porcelain=v1", "--untracked-files=all"): "",
                    ("rev-parse", "HEAD"): f"{sha}\n",
                    ("rev-parse", "refs/remotes/origin/main"): f"{sha}\n",
                }
                return values[args]

            with mock.patch.object(bootstrap_v1, "_git", side_effect=fake_git):
                self.assertEqual(bootstrap_v2.validate_trusted_checkout(v2_checkout), sha)

            v1_checkout = Path(temp_dir) / bootstrap_v1.TRUSTED_CHECKOUT_NAME
            v1_checkout.mkdir()
            with self.assertRaises(bootstrap_v1.RunnerSmokeBrokerBootstrapError):
                bootstrap_v2.validate_trusted_checkout(v1_checkout)

    def test_v2_source_delivery_is_bounded_and_preserves_v1(self) -> None:
        v1 = json.loads(V1_SOURCE_CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(v1["issue"], 576)
        self.assertEqual(
            v1["trusted_checkout"]["name"],
            "RPi5_main-runner-smoke-broker-bootstrap-trusted",
        )

        v2 = json.loads(V2_SOURCE_CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(v2["issue"], 584)
        self.assertTrue(v2["source_only"])
        self.assertFalse(v2["source_merge_enables_live"])
        self.assertEqual(v2["trusted_checkout"]["name"], bootstrap_v2.TRUSTED_CHECKOUT_NAME)
        self.assertEqual(
            v2["trusted_checkout"]["derivation"],
            "RPi5_CHECKOUT_PARENT/RPi5_main-runner-smoke-broker-bootstrap-v2-trusted",
        )
        preserved = v2["preserved_checkout_namespaces"]
        v1_preserved = next(
            item for item in preserved
            if item.get("name") == "RPi5_main-runner-smoke-broker-bootstrap-trusted"
        )
        self.assertFalse(v1_preserved["mutation_allowed"])
        self.assertFalse(v1_preserved["cleanup_allowed"])
        self.assertFalse(v1_preserved["authority_source"])
        self.assertEqual(set(v2["preflight_states"]), {"ABSENT", "EXACT_CLEAN", "CONFLICT"})

        mutations = v2["allowed_git_mutations"]
        self.assertEqual(len(mutations), 2)
        self.assertEqual(mutations[0]["argv"], ["git", "fetch", "origin", "main"])
        self.assertEqual(mutations[0]["max_operations"], 1)
        self.assertEqual(
            mutations[1]["argv"],
            [
                "git",
                "worktree",
                "add",
                "--detach",
                v2["trusted_checkout"]["derivation"],
                v2["trusted_checkout"]["expected_sha_authority"],
            ],
        )
        self.assertEqual(mutations[1]["max_operations"], 1)
        forbidden = set(v2["forbidden_git_operations"])
        for operation in (
            "reset", "rebase", "clean", "checkout", "switch", "merge", "pull",
            "worktree remove", "worktree prune", "worktree repair", "push", "force",
        ):
            self.assertIn(operation, forbidden)
        self.assertFalse(v2["failure"]["automatic_retry"])
        self.assertFalse(v2["failure"]["automatic_cleanup"])
        self.assertFalse(v2["failure"]["automatic_rollback"])

        host = json.loads(V2_HOST_CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(host["checkout_isolation_issue"], 584)
        self.assertEqual(host["historical_trusted_checkout_name"], bootstrap_v1.TRUSTED_CHECKOUT_NAME)
        self.assertEqual(host["trusted_checkout_name"], bootstrap_v2.TRUSTED_CHECKOUT_NAME)
        self.assertEqual(host["source_delivery_contract"], str(bootstrap_v2.SOURCE_DELIVERY_CONTRACT))
        self.assertEqual(tuple(host["activation_sequence"]), bootstrap_v1.MUTATION_SEQUENCE)
        self.assertFalse(host["authority"]["generic_sudo"])
        self.assertFalse(host["authority"]["historical_v1_checkout_authority"])
        self.assertFalse(host["activation"]["source_merge_authorizes_live"])
        self.assertFalse(host["activation"]["source_delivery_live_authorized"])
        self.assertTrue(host["activation"]["rdc_no_new_privileges_must_remain"])


if __name__ == "__main__":
    unittest.main()
