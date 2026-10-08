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
MODULE_PATH = ROOT / "scripts/align-simple-deploy-coloring-pages-v1.py"
CONTRACT_PATH = ROOT / "ops/contracts/simple-deploy-coloring-pages-alignment-v1.json"
REGISTRY_SOURCE = ROOT / "ops/deploy/simple-deploy-targets-v1.json"
COMPOSE_SOURCE = ROOT / "ops/deploy/simple-deploy-compose/coloring-pages-public.yml"

spec = importlib.util.spec_from_file_location("align_coloring_pages_v1", MODULE_PATH)
assert spec and spec.loader
align = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = align
spec.loader.exec_module(align)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ColoringPagesAlignmentTests(unittest.TestCase):
    def test_helper_stays_small_and_fixed_scope(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertLess(len(source.splitlines()), 280)
        self.assertNotIn("dataclass", source)
        self.assertNotIn("docker ", source)
        self.assertNotIn("systemctl", source)
        options = {
            option
            for action in align.parser()._actions
            for option in action.option_strings
        }
        self.assertEqual(options, {"-h", "--help", "--expected-source-sha", "--apply"})

    def test_historical_alignment_pin_rejects_new_weather_registry(self) -> None:
        registry = REGISTRY_SOURCE.read_bytes()
        compose = COMPOSE_SOURCE.read_bytes()

        # #860's fixed desired registry belongs to the historical
        # Coloring Pages alignment operation. #915 changes the global
        # registry for Weather, not that operator's authorized target.
        self.assertEqual(
            align.DESIRED_REGISTRY,
            "88c3acbf304ab9676a6a767e5f3055351f20fd88ca9bf1bf4a2cb1210ef3617f",
        )
        self.assertNotEqual(digest(registry), align.DESIRED_REGISTRY)
        self.assertEqual(digest(compose), align.DESIRED_COMPOSE)
        with self.assertRaisesRegex(
            align.AlignError, "desired registry source hash drifted"
        ):
            align.validate_registry(registry)

    def test_contract_has_exact_three_file_boundary(self) -> None:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(contract["issue"], 860)
        self.assertEqual(len(contract["baseline"]), 3)
        self.assertEqual(
            contract["replacement_order"],
            [
                "/etc/rozkalns-simple-deployer/compose/coloring-pages-public.yml",
                "/etc/rozkalns-simple-deployer/targets.json",
                "/etc/rozkalns-simple-deployer/identity.json",
            ],
        )
        self.assertEqual(contract["fixed_modes"], ["0644", "0444", "0444"])
        for key in ("live", "docker", "systemd", "content_import", "network_cloudflare", "secrets"):
            self.assertFalse(contract["authority"][key])
        self.assertEqual(contract["failure"]["post_first_mutation"], "STOP")
        self.assertFalse(contract["failure"]["retry"])
        self.assertFalse(contract["failure"]["cleanup"])
        self.assertFalse(contract["failure"]["rollback"])

    def test_identity_is_exact_authorized_sha(self) -> None:
        sha = "a" * 40
        self.assertEqual(
            json.loads(align.identity_bytes(sha)),
            {
                "repository": "rozkalnsandris/RPi5_main",
                "schema": "rozkalns.rpi5-main.simple-deploy.identity.v1",
                "source_sha": sha,
            },
        )

    def test_alignment_changes_only_three_fixed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "etc/rozkalns-simple-deployer"
            compose_root = root / "compose"
            compose_root.mkdir(parents=True)
            os.chmod(root, 0o755)
            os.chmod(compose_root, 0o755)

            registry = root / "targets.json"
            identity = root / "identity.json"
            compose = compose_root / "coloring-pages-public.yml"
            sentinel = root / "sentinel"

            old_registry = b"old-registry\n"
            old_identity = b"old-identity\n"
            old_compose = b"old-compose\n"
            registry.write_bytes(old_registry)
            identity.write_bytes(old_identity)
            compose.write_bytes(old_compose)
            sentinel.write_bytes(b"unchanged\n")
            os.chmod(registry, 0o444)
            os.chmod(identity, 0o444)
            os.chmod(compose, 0o644)

            registry_stage = root / ".targets.json.coloring-pages.staged"
            identity_stage = root / ".identity.json.coloring-pages.staged"
            compose_stage = compose_root / ".coloring-pages-public.yml.staged"

            saved = (
                align.BASELINE_REGISTRY,
                align.BASELINE_IDENTITY,
                align.BASELINE_COMPOSE,
            )
            align.BASELINE_REGISTRY = digest(old_registry)
            align.BASELINE_IDENTITY = digest(old_identity)
            align.BASELINE_COMPOSE = digest(old_compose)
            try:
                current = align.preflight(
                    uid=os.getuid(),
                    gid=os.getgid(),
                    registry=registry,
                    identity=identity,
                    compose=compose,
                    registry_stage=registry_stage,
                    identity_stage=identity_stage,
                    compose_stage=compose_stage,
                )
                wanted = (
                    REGISTRY_SOURCE.read_bytes(),
                    align.identity_bytes("b" * 40),
                    COMPOSE_SOURCE.read_bytes(),
                )
                align.apply(
                    wanted,
                    current,
                    uid=os.getuid(),
                    gid=os.getgid(),
                    registry=registry,
                    identity=identity,
                    compose=compose,
                    registry_stage=registry_stage,
                    identity_stage=identity_stage,
                    compose_stage=compose_stage,
                )
            finally:
                (
                    align.BASELINE_REGISTRY,
                    align.BASELINE_IDENTITY,
                    align.BASELINE_COMPOSE,
                ) = saved

            self.assertEqual(registry.read_bytes(), wanted[0])
            self.assertEqual(identity.read_bytes(), wanted[1])
            self.assertEqual(compose.read_bytes(), wanted[2])
            self.assertEqual(sentinel.read_bytes(), b"unchanged\n")
            self.assertFalse(registry_stage.exists())
            self.assertFalse(identity_stage.exists())
            self.assertFalse(compose_stage.exists())

    def test_replacement_order_keeps_identity_last(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        compose = source.index("os.replace(compose_stage, compose)")
        registry = source.index("os.replace(registry_stage, registry)")
        identity = source.index("os.replace(identity_stage, identity)")
        self.assertLess(compose, registry)
        self.assertLess(registry, identity)


if __name__ == "__main__":
    unittest.main()
