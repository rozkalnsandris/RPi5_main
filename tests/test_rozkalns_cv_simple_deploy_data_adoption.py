#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/contracts/simple-deploy-rozkalns-cv-data-adoption-v1.json"
CUTOVER = ROOT / "ops/deploy/rozkalns-cv-simple-deploy-cutover-v1.json"
SCRIPT = ROOT / "scripts/adopt-simple-deploy-rozkalns-cv-data-v1.py"

spec = importlib.util.spec_from_file_location("cv_data_adoption_v1", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class CvDataAdoptionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.cutover = json.loads(CUTOVER.read_text(encoding="utf-8"))

    def test_contract_is_source_only_and_fixed_path(self) -> None:
        self.assertEqual(
            self.contract["schema"],
            "rozkalns.rpi5-main.simple-deploy-rozkalns-cv-data-adoption.v1",
        )
        self.assertEqual(self.contract["issue"], 808)
        self.assertEqual(self.contract["status"], "SOURCE_REVIEWED_NOT_LIVE")
        self.assertEqual(
            self.contract["source"]["data_path"],
            "/home/andris/docker/cv/bot/data",
        )
        self.assertEqual(
            self.contract["destination"]["data_path"],
            "/var/lib/rozkalns-simple-deployer/rozkalns-cv/data",
        )
        helper = self.contract["helper"]
        self.assertEqual(helper["options"], ["--expected-source-sha", "--apply"])
        for key in (
            "caller_selectable_source_path",
            "caller_selectable_destination_path",
            "caller_selectable_container",
            "caller_selectable_command_or_argv",
            "caller_selectable_environment",
            "docker_inspect_exec_or_logs",
        ):
            self.assertFalse(helper[key], key)

    def test_storage_implementation_is_identical_and_no_schema_migration(self) -> None:
        source = self.contract["source"]
        candidate = self.contract["candidate"]
        self.assertEqual(
            source["legacy_storage_blob"],
            "7a7ce05021223b43686cd93513208bb0a249d9bc",
        )
        self.assertEqual(
            candidate["candidate_storage_blob"],
            source["legacy_storage_blob"],
        )
        self.assertTrue(candidate["storage_implementation_identical"])
        self.assertFalse(candidate["database_schema_migration_required"])
        materialization = self.contract["materialization"]
        self.assertTrue(materialization["recursive_byte_copy"])
        self.assertFalse(materialization["database_queries"])
        self.assertFalse(materialization["database_schema_migrations"])
        self.assertFalse(materialization["database_content_transformation"])

    def test_private_env_is_separate_and_openai_secret_is_not_inferred(self) -> None:
        boundary = self.contract["private_runtime_config_boundary"]
        self.assertFalse(boundary["handled_by_this_helper"])
        self.assertTrue(boundary["required_before_first_cutover_mutation"])
        self.assertTrue(boundary["separate_exact_secret_authority_required_if_absent"])
        self.assertEqual(
            boundary["public_literals"],
            {
                "LLM_BASE_URL": "https://api.openai.com",
                "LLM_MODEL": "gpt-5.6-luna",
            },
        )
        self.assertEqual(boundary["provider_secret_key"], "LLM_API_KEY")
        self.assertFalse(boundary["legacy_provider_secret_may_be_reused_without_validation"])

    def test_cutover_stops_writer_then_adopts_data_without_restart(self) -> None:
        data = self.cutover["protected_prerequisites"]["persistent_data"]
        self.assertFalse(data["required_before_cutover"])
        self.assertTrue(data["materialized_during_cutover"])
        self.assertTrue(data["cvbot_must_be_stopped_before_copy"])
        self.assertFalse(data["cvbot_restart_on_success_path"])
        self.assertTrue(data["storage_implementation_identical"])

        steps = self.cutover["ordered_steps"]
        stop = steps.index("stop-legacy-cvbot-container")
        adopt = steps.index("materialize-persistent-data-through-reviewed-byte-copy-helper")
        remove_cv = steps.index("stop-and-remove-legacy-cv-container")
        remove_cvbot = steps.index("remove-stopped-legacy-cvbot-container")
        apply = steps.index("apply-rozkalns-cv-rpi5-through-reviewed-generic-simple-deploy")
        self.assertLess(stop, adopt)
        self.assertLess(adopt, remove_cv)
        self.assertLess(remove_cv, remove_cvbot)
        self.assertLess(remove_cvbot, apply)

    def test_copy_helper_preserves_bytes_and_rejects_symlinks(self) -> None:
        uid = os.getuid()
        gid = os.getgid()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "assistant.sqlite3").write_bytes(b"sqlite-bytes")
            nested = source / "nested"
            nested.mkdir()
            (nested / "state.bin").write_bytes(b"state-bytes")

            mod._copy_directory_contents(
                source,
                target,
                app_uid=uid,
                app_gid=gid,
                runtime_gid=gid,
            )
            self.assertEqual((target / "assistant.sqlite3").read_bytes(), b"sqlite-bytes")
            self.assertEqual((target / "nested" / "state.bin").read_bytes(), b"state-bytes")
            self.assertEqual((target / "assistant.sqlite3").stat().st_mode & 0o777, 0o600)
            self.assertEqual((target / "nested").stat().st_mode & 0o777, 0o750)

            symlink_source = root / "symlink-source"
            symlink_target = root / "symlink-target"
            symlink_source.mkdir()
            symlink_target.mkdir()
            (symlink_source / "real").write_bytes(b"x")
            (symlink_source / "link").symlink_to("real")
            with self.assertRaises(mod.AdoptionError):
                mod._copy_directory_contents(
                    symlink_source,
                    symlink_target,
                    app_uid=uid,
                    app_gid=gid,
                    runtime_gid=gid,
                )

    def test_helper_has_no_sqlite_or_generic_docker_execution_surface(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        self.assertNotIn("import sqlite3", text)
        self.assertNotIn("docker inspect", text)
        self.assertNotIn("docker exec", text)
        self.assertNotIn("docker logs", text)
        self.assertNotIn("shell=true", text)
        self.assertIn('"ps"', text)
        authority = self.contract["authority"]
        self.assertFalse(authority["merge_authorizes_live"])
        self.assertFalse(authority["protected_data_read_or_copy"])
        self.assertFalse(authority["docker_container_lifecycle"])
        self.assertFalse(authority["private_runtime_config_or_secret_access"])
        self.assertFalse(authority["cutover"])


if __name__ == "__main__":
    unittest.main()
