#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/reconcile-simple-deploy-coloring-pages-v1.py"
CONTRACT_PATH = ROOT / "ops/contracts/simple-deploy-coloring-pages-reconciliation-v1.json"
REGISTRY_SOURCE = ROOT / "ops/deploy/simple-deploy-targets-v1.json"
COMPOSE_SOURCE = ROOT / "ops/deploy/simple-deploy-compose/coloring-pages-public.yml"

spec = importlib.util.spec_from_file_location("reconcile_coloring_pages_v1", MODULE_PATH)
assert spec and spec.loader
reconcile = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reconcile
spec.loader.exec_module(reconcile)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class Fixture:
    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "etc/rozkalns-simple-deployer"
        self.compose_root = self.root / "compose"
        self.compose_root.mkdir(parents=True, mode=0o755)
        os.chmod(self.root, 0o755)
        os.chmod(self.compose_root, 0o755)

        self.registry = self.root / "targets.json"
        self.identity = self.root / "identity.json"
        self.compose = self.compose_root / "coloring-pages-public.yml"
        self.registry_stage = self.root / ".targets.json.coloring-pages-v1.staged"
        self.identity_stage = self.root / ".identity.json.coloring-pages-v1.staged"
        self.compose_stage = self.compose_root / ".coloring-pages-public.yml.reconcile-v1.staged"
        self.sentinel = self.root / "sentinel.txt"

        self.baseline_registry = b'{"baseline":"registry"}\n'
        self.baseline_identity = b'{"baseline":"identity"}\n'
        self.baseline_compose = b"services:\n  baseline: true\n"

        self.registry.write_bytes(self.baseline_registry)
        self.identity.write_bytes(self.baseline_identity)
        self.compose.write_bytes(self.baseline_compose)
        self.sentinel.write_text("unchanged\n", encoding="utf-8")
        os.chmod(self.registry, 0o444)
        os.chmod(self.identity, 0o444)
        os.chmod(self.compose, 0o644)

        self.paths = reconcile.InstallPaths(
            root=self.root,
            registry=self.registry,
            identity=self.identity,
            compose_root=self.compose_root,
            coloring_compose=self.compose,
            registry_stage=self.registry_stage,
            identity_stage=self.identity_stage,
            coloring_compose_stage=self.compose_stage,
        )
        self.baseline = reconcile.Baseline(
            registry_sha256=sha256(self.baseline_registry),
            identity_sha256=sha256(self.baseline_identity),
            coloring_compose_sha256=sha256(self.baseline_compose),
        )
        self.source_sha = "a" * 40
        self.desired = reconcile.Desired(
            registry=REGISTRY_SOURCE.read_bytes(),
            identity=reconcile._identity_bytes(self.source_sha),
            coloring_compose=COMPOSE_SOURCE.read_bytes(),
        )
        self.uid = os.getuid()
        self.gid = os.getgid()

    def preflight(self) -> reconcile.InstalledSnapshot:
        return reconcile._preflight(
            self.paths,
            self.desired,
            baseline=self.baseline,
            uid=self.uid,
            gid=self.gid,
        )

    def close(self) -> None:
        self.temp.cleanup()


class ColoringPagesReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = Fixture()

    def tearDown(self) -> None:
        self.fx.close()

    def test_source_hashes_and_target_semantics_are_frozen(self) -> None:
        registry = REGISTRY_SOURCE.read_bytes()
        compose = COMPOSE_SOURCE.read_bytes()
        self.assertEqual(sha256(registry), reconcile.DESIRED_REGISTRY_SHA256)
        self.assertEqual(
            sha256(compose),
            reconcile.DESIRED_COLORING_COMPOSE_SHA256,
        )
        reconcile._validate_desired_registry(registry)

    def test_exact_baseline_reconciles_only_three_fixed_files(self) -> None:
        sentinel_before = self.fx.sentinel.read_bytes()
        snapshot = self.fx.preflight()
        progress = reconcile._apply(
            self.fx.paths,
            self.fx.desired,
            snapshot,
            uid=self.fx.uid,
            gid=self.fx.gid,
        )

        self.assertTrue(progress.mutation_started)
        self.assertEqual(progress.staged_files_created, 3)
        self.assertEqual(progress.installed_files_replaced, 3)
        self.assertEqual(self.fx.compose.read_bytes(), self.fx.desired.coloring_compose)
        self.assertEqual(self.fx.registry.read_bytes(), self.fx.desired.registry)
        self.assertEqual(self.fx.identity.read_bytes(), self.fx.desired.identity)
        self.assertEqual(self.fx.sentinel.read_bytes(), sentinel_before)
        self.assertFalse(self.fx.compose_stage.exists())
        self.assertFalse(self.fx.registry_stage.exists())
        self.assertFalse(self.fx.identity_stage.exists())
        self.assertEqual(self.fx.compose.stat().st_mode & 0o777, 0o644)
        self.assertEqual(self.fx.registry.stat().st_mode & 0o777, 0o444)
        self.assertEqual(self.fx.identity.stat().st_mode & 0o777, 0o444)

    def test_registry_baseline_drift_fails_before_mutation(self) -> None:
        os.chmod(self.fx.registry, 0o644)
        self.fx.registry.write_bytes(b"drift\n")
        os.chmod(self.fx.registry, 0o444)
        with self.assertRaisesRegex(
            reconcile.ReconcileError,
            "target registry does not match the reviewed baseline",
        ):
            self.fx.preflight()
        self.assertFalse(self.fx.compose_stage.exists())
        self.assertFalse(self.fx.registry_stage.exists())
        self.assertFalse(self.fx.identity_stage.exists())

    def test_identity_baseline_drift_fails_before_mutation(self) -> None:
        os.chmod(self.fx.identity, 0o644)
        self.fx.identity.write_bytes(b"drift\n")
        os.chmod(self.fx.identity, 0o444)
        with self.assertRaisesRegex(
            reconcile.ReconcileError,
            "identity does not match the reviewed baseline",
        ):
            self.fx.preflight()
        self.assertFalse(self.fx.compose_stage.exists())

    def test_compose_baseline_drift_fails_before_mutation(self) -> None:
        self.fx.compose.write_bytes(b"drift\n")
        with self.assertRaisesRegex(
            reconcile.ReconcileError,
            "compose does not match the reviewed baseline",
        ):
            self.fx.preflight()
        self.assertFalse(self.fx.compose_stage.exists())

    def test_existing_staging_file_fails_before_mutation(self) -> None:
        self.fx.registry_stage.write_text("stale\n", encoding="utf-8")
        with self.assertRaisesRegex(
            reconcile.ReconcileError,
            "fixed staging path must be absent",
        ):
            self.fx.preflight()
        self.assertEqual(self.fx.registry.read_bytes(), self.fx.baseline_registry)
        self.assertEqual(self.fx.compose.read_bytes(), self.fx.baseline_compose)

    def test_identity_is_exact_authorized_source_marker(self) -> None:
        payload = json.loads(self.fx.desired.identity.decode("utf-8"))
        self.assertEqual(
            payload,
            {
                "repository": "rozkalnsandris/RPi5_main",
                "schema": "rozkalns.rpi5-main.simple-deploy.identity.v1",
                "source_sha": self.fx.source_sha,
            },
        )

    def test_apply_replaces_identity_last(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        compose_index = source.index(
            "paths.coloring_compose_stage,\n            paths.coloring_compose,"
        )
        registry_index = source.index(
            "_replace(paths.registry_stage, paths.registry, paths.root, progress)"
        )
        identity_index = source.index(
            "_replace(paths.identity_stage, paths.identity, paths.root, progress)"
        )
        self.assertLess(compose_index, registry_index)
        self.assertLess(registry_index, identity_index)

    def test_cli_has_no_arbitrary_runtime_authority(self) -> None:
        parser = reconcile._build_parser()
        options = {option for action in parser._actions for option in action.option_strings}
        self.assertEqual(
            options,
            {"-h", "--help", "--expected-source-sha", "--apply"},
        )
        source = MODULE_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "--path",
            "--command",
            "--environment",
            "--target",
            "--repository",
            "shell=True",
            "systemctl",
            "docker run",
            "docker pull",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_machine_contract_matches_three_file_boundary(self) -> None:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(contract["issue"], 860)
        self.assertEqual(
            contract["baseline"]["registry"]["sha256"],
            reconcile.BASELINE_REGISTRY_SHA256,
        )
        self.assertEqual(
            contract["baseline"]["identity"]["sha256"],
            reconcile.BASELINE_IDENTITY_SHA256,
        )
        self.assertEqual(
            contract["baseline"]["coloring_pages_compose"]["sha256"],
            reconcile.BASELINE_COLORING_COMPOSE_SHA256,
        )
        self.assertEqual(
            contract["desired"]["registry_sha256"],
            reconcile.DESIRED_REGISTRY_SHA256,
        )
        self.assertEqual(
            contract["desired"]["coloring_pages_compose_sha256"],
            reconcile.DESIRED_COLORING_COMPOSE_SHA256,
        )
        self.assertEqual(
            [item["path"] for item in contract["installed_delta"]],
            [
                "/etc/rozkalns-simple-deployer/compose/coloring-pages-public.yml",
                "/etc/rozkalns-simple-deployer/targets.json",
                "/etc/rozkalns-simple-deployer/identity.json",
            ],
        )
        self.assertTrue(
            contract["installed_delta"][2]["final_provenance_marker"]
        )
        self.assertFalse(contract["authority"]["docker"])
        self.assertFalse(contract["authority"]["systemd"])
        self.assertFalse(contract["authority"]["database_or_application_data"])
        self.assertFalse(contract["authority"]["production_content_import"])
        self.assertFalse(contract["authority"]["cloudflare_or_network"])
        self.assertEqual(
            contract["failure"]["post_first_mutation"],
            "STOP_FAIL_CLOSED",
        )


if __name__ == "__main__":
    unittest.main()
