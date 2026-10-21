#!/usr/bin/env python3
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
DISPATCHER = ROOT / "ops/bin/coloring-pages-publish-request-dispatcher"
CONTRACT = ROOT / "ops/contracts/coloring-pages-publish-request-bridge-v1.json"
INSTALLER = ROOT / "scripts/install-coloring-pages-publish-request-bridge-v1.sh"
PATH_UNIT = ROOT / "ops/systemd/coloring-pages-publish-request-bridge.path"
SERVICE_UNIT = ROOT / "ops/systemd/coloring-pages-publish-request-bridge.service"
HOST_CONTRACT = ROOT / "ops/contracts/simple-deploy-host-v1.json"

LOADER = importlib.machinery.SourceFileLoader(
    "coloring_pages_publish_request_dispatcher",
    str(DISPATCHER),
)
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
bridge = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(bridge)


class PublishRequestBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = DISPATCHER.read_text(encoding="utf-8")
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.installer = INSTALLER.read_text(encoding="utf-8")
        cls.path_unit = PATH_UNIT.read_text(encoding="utf-8")
        cls.service_unit = SERVICE_UNIT.read_text(encoding="utf-8")

    def request(self, batch_id: str, activities: list[dict]) -> dict:
        return {
            "schema": bridge.REQUEST_SCHEMA,
            "batch_id": batch_id,
            "activities": activities,
        }

    def v1(self, page_id: str = "1234567", sha: str = "a" * 64, size: int = 1000):
        return {
            "kind": "v1",
            "id": page_id,
            "expected_sha256": sha,
            "expected_size": size,
        }

    def v2(self, page_id: str = "7654321"):
        return {
            "kind": "v2",
            "id": page_id,
            "expected_pages": [
                {"index": 1, "sha256": "a" * 64, "size_bytes": 1000},
                {"index": 2, "sha256": "b" * 64, "size_bytes": 1100},
            ],
        }

    def runtime_tree(self, tempdir: str):
        root = Path(tempdir) / "bridge"
        incoming = root / "incoming"
        claimed = root / "claimed"
        results = root / "results"
        for path in (root, incoming, claimed, results):
            path.mkdir(exist_ok=True)
        lock = root / ".lock"
        lock.write_bytes(b"")
        lock.chmod(0o600)
        return root, incoming, claimed, results, lock

    def write_request(self, incoming: Path, batch_id: str, activities: list[dict]):
        request = incoming / f"batch-{batch_id}.json"
        ready = incoming / f"batch-{batch_id}.ready"
        request.write_text(
            json.dumps(self.request(batch_id, activities), separators=(",", ":")),
            encoding="utf-8",
        )
        ready.write_text(batch_id + "\n", encoding="ascii")
        request.chmod(0o600)
        ready.chmod(0o600)
        return request, ready

    def patch_runtime(self, root, incoming, claimed, results, lock):
        return mock.patch.multiple(
            bridge,
            STATE_ROOT=root,
            INCOMING=incoming,
            CLAIMED=claimed,
            RESULTS=results,
            LOCK=lock,
        )

    def completed_pass(self, page_id: str, pages: int = 1):
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                "COLORING_PAGES_DRIVE_INGEST=PASS\n"
                f"ID={page_id}\n"
                f"PAGES={pages}\n"
                "COLORING_PAGES_SITEMAP=CURRENT\n"
            ),
            stderr="",
        )

    def test_sources_parse_and_contract_is_bounded(self):
        compile(self.source, str(DISPATCHER), "exec")
        completed = subprocess.run(
            ["bash", "-n", str(INSTALLER)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)

        self.assertEqual(
            self.contract["runtime"]["dispatcher_installed_path"],
            "/usr/local/bin/coloring-pages-publish-request-dispatcher",
        )
        self.assertEqual(
            self.contract["runtime"]["operator_installed_path"],
            "/usr/local/bin/coloring-pages-drive-ingest",
        )
        self.assertFalse(self.contract["runtime"]["shell_execution"])
        self.assertTrue(self.contract["runtime"]["operator_argv_only"])
        self.assertFalse(self.contract["runtime"]["automatic_retry"])
        self.assertFalse(self.contract["runtime"]["automatic_cleanup"])
        self.assertEqual(self.contract["handoff"]["maximum_activities"], 20)
        self.assertTrue(self.contract["handoff"]["request_must_be_written_before_ready_marker"])
        self.assertTrue(self.contract["handoff"]["claim_before_operator_execution"])
        self.assertTrue(self.contract["handoff"]["claimed_requests_never_requeued_automatically"])

    def test_systemd_bridge_is_non_root_and_ready_marker_driven(self):
        self.assertIn(
            "PathExistsGlob=/srv/coloring-pages-content/state/"
            "publish-request-bridge/incoming/batch-*.ready",
            self.path_unit,
        )
        self.assertIn("User=andris", self.service_unit)
        self.assertIn("Group=andris", self.service_unit)
        self.assertIn(
            "ExecStart=/usr/local/bin/coloring-pages-publish-request-dispatcher --once",
            self.service_unit,
        )
        self.assertNotIn("sudo", self.service_unit)
        self.assertNotIn("/bin/sh", self.service_unit)
        self.assertNotIn("/bin/bash", self.service_unit)

    def test_v1_and_v2_requests_build_only_fixed_operator_argv(self):
        batch = "1" * 32
        checked = bridge.validate_request(
            self.request(batch, [self.v1(), self.v2()]),
            batch,
        )
        self.assertEqual(
            bridge.operator_argv(checked[0]),
            [
                "/usr/local/bin/coloring-pages-drive-ingest",
                "--id",
                "1234567",
                "--expected-sha256",
                "a" * 64,
                "--expected-size",
                "1000",
            ],
        )
        self.assertEqual(
            bridge.operator_argv(checked[1]),
            [
                "/usr/local/bin/coloring-pages-drive-ingest",
                "--id",
                "7654321",
                "--expected-page",
                f"1:{'a' * 64}:1000",
                "--expected-page",
                f"2:{'b' * 64}:1100",
            ],
        )
        self.assertNotIn("shell=True", self.source)
        self.assertNotIn("shell = True", self.source)
        self.assertNotIn("os.system", self.source)

    def test_unknown_fields_duplicate_ids_and_bad_page_order_are_rejected(self):
        batch = "2" * 32
        bad = self.v1()
        bad["extra"] = True
        with self.assertRaises(bridge.BridgeError):
            bridge.validate_request(self.request(batch, [bad]), batch)

        with self.assertRaises(bridge.BridgeError):
            bridge.validate_request(
                self.request(batch, [self.v1(), self.v1()]),
                batch,
            )

        bad_v2 = self.v2()
        bad_v2["expected_pages"][1]["index"] = 3
        with self.assertRaises(bridge.BridgeError):
            bridge.validate_request(self.request(batch, [bad_v2]), batch)

    def test_claim_removes_ready_trigger_before_execution(self):
        batch = "3" * 32
        with tempfile.TemporaryDirectory() as tempdir:
            root, incoming, claimed, results, lock = self.runtime_tree(tempdir)
            request, ready = self.write_request(incoming, batch, [self.v1()])
            request_inode = request.stat().st_ino
            with self.patch_runtime(root, incoming, claimed, results, lock):
                claimed_value = bridge.claim_one()

            self.assertIsNotNone(claimed_value)
            self.assertFalse(ready.exists())
            self.assertFalse(request.exists())
            claimed_request = claimed / f"batch-{batch}.json"
            claimed_ready = claimed / f"batch-{batch}.ready"
            self.assertTrue(claimed_request.is_file())
            self.assertTrue(claimed_ready.is_file())
            self.assertEqual(claimed_request.stat().st_ino, request_inode)

    def test_batch_stops_on_first_failure_and_never_automatically_retries(self):
        batch = "4" * 32
        activities = [
            self.v1("1234567", "a" * 64, 1000),
            self.v1("2345678", "b" * 64, 1100),
            self.v1("3456789", "c" * 64, 1200),
        ]
        failure = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr=(
                "COLORING_PAGES_DRIVE_INGEST=FAIL "
                "error=drive object missing or ambiguous\n"
            ),
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root, incoming, claimed, results, lock = self.runtime_tree(tempdir)
            self.write_request(incoming, batch, activities)
            with self.patch_runtime(root, incoming, claimed, results, lock):
                with mock.patch.object(
                    bridge.subprocess,
                    "run",
                    side_effect=[self.completed_pass("1234567"), failure],
                ) as run:
                    first = bridge.main(["--once"])
                    second = bridge.main(["--once"])

            self.assertEqual(first, 0)
            self.assertEqual(second, 0)
            self.assertEqual(run.call_count, 2)
            result = json.loads(
                (results / f"batch-{batch}.result.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result["result"], "FAIL")
            self.assertEqual(
                result["succeeded"],
                [
                    {
                        "id": "1234567",
                        "status": "PASS",
                        "pages": 1,
                        "sitemap": "CURRENT",
                    }
                ],
            )
            self.assertEqual(result["failed_id"], "2345678")
            self.assertEqual(result["error"], "drive object missing or ambiguous")
            self.assertFalse((incoming / f"batch-{batch}.ready").exists())
            self.assertTrue((claimed / f"batch-{batch}.ready").exists())
            self.assertTrue((claimed / f"batch-{batch}.json").exists())

    def test_success_result_is_sanitized_and_exact(self):
        batch = "5" * 32
        activities = [self.v1("1234567"), self.v2("7654321")]
        with tempfile.TemporaryDirectory() as tempdir:
            root, incoming, claimed, results, lock = self.runtime_tree(tempdir)
            self.write_request(incoming, batch, activities)
            with self.patch_runtime(root, incoming, claimed, results, lock):
                with mock.patch.object(
                    bridge.subprocess,
                    "run",
                    side_effect=[
                        self.completed_pass("1234567", 1),
                        self.completed_pass("7654321", 2),
                    ],
                ):
                    rc = bridge.main(["--once"])

            self.assertEqual(rc, 0)
            result = json.loads(
                (results / f"batch-{batch}.result.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result["schema"], bridge.RESULT_SCHEMA)
            self.assertEqual(result["result"], "PASS")
            self.assertEqual([row["id"] for row in result["succeeded"]], ["1234567", "7654321"])
            self.assertIsNone(result["failed_id"])
            self.assertIsNone(result["error"])
            self.assertEqual(
                stat.S_IMODE((results / f"batch-{batch}.result.json").stat().st_mode),
                0o600,
            )

    def test_installer_is_one_time_bridge_install_only(self):
        for marker in (
            "--expected-rpi5-main-sha",
            "/usr/local/bin/coloring-pages-publish-request-dispatcher",
            "systemctl enable --now coloring-pages-publish-request-bridge.path",
            "ready marker exists before bridge activation",
            "CREDENTIALS_CHANGED=false",
            "SUDOERS_CHANGED=false",
            "DRIVE_MUTATED=false",
            "INGEST_EXECUTED=false",
            "DOCKER_EXECUTED=false",
            "NETWORK_CHANGED=false",
        ):
            self.assertIn(marker, self.installer)

        for forbidden in (
            "rclone copy",
            "rclone rcat",
            "docker run",
            "docker pull",
            "/etc/sudoers",
            "cloudflared",
        ):
            self.assertNotIn(forbidden, self.installer)

    def test_host_registry_records_bridge_without_replacing_ingest_operator(self):
        host = json.loads(HOST_CONTRACT.read_text(encoding="utf-8"))
        targets = {
            item["target_alias"]: item
            for item in host["registry"]["reviewed_targets"]
        }
        coloring = targets["coloring-pages-public-rpi5"]
        self.assertEqual(
            coloring["drive_ingest_installed_path"],
            "/usr/local/bin/coloring-pages-drive-ingest",
        )
        self.assertEqual(
            coloring["publish_request_bridge_contract"],
            "ops/contracts/coloring-pages-publish-request-bridge-v1.json",
        )
        self.assertEqual(
            coloring["publish_request_dispatcher_installed_path"],
            "/usr/local/bin/coloring-pages-publish-request-dispatcher",
        )
        self.assertEqual(
            coloring["publish_request_path_unit"],
            "coloring-pages-publish-request-bridge.path",
        )
        self.assertTrue(coloring["publish_request_bridge_requires_separate_live_authority"])


if __name__ == "__main__":
    unittest.main()
