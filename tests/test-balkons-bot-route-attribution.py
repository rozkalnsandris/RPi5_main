#!/usr/bin/env python3
"""Offline adversarial tests for #1478 sanitized route attribution."""
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
TOOL = ROOT / "ops/bin/balkons-bot-route-attribution"
PARSER = ROOT / "ops/bin/balkons-bot-preflight"


def load(name: str, path: Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


m = load("balkons_route_1478", TOOL)
legacy = load("balkons_existing_parser_1478", PARSER)


def show(script: str, *, encrypted: str = "", plaintext: str = "",
         active: bool = True, pid: str = "2435") -> dict[str, str]:
    return {
        "LoadState": "loaded",
        "ActiveState": "active" if active else "inactive",
        "SubState": "running" if active else "dead",
        "MainPID": pid,
        "ExecStart": (
            "{ path=/usr/bin/python3 ; argv[]=/usr/bin/python3 "
            + script + " ; ignore_errors=no ; start_time=[timestamp] }"
        ),
        "LoadCredentialEncrypted": encrypted,
        "LoadCredential": plaintext,
    }


class RouteAttributionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.public = self.root / "public.py"
        self.fake_source = b'# public reviewed source fixture\n'
        self.sha = m.digest(self.fake_source)
        self.uid = os.geteuid()

    def collect(self, props: dict[str, str], **kwargs):
        return m.collect(properties=props,
                         parser=legacy.parse_exec_start,
                         target=self.public, owner=self.uid, sha=self.sha,
                         **kwargs)

    def test_legacy_source_private_filename_not_assumed_public(self):
        # Private legacy Python file must NEVER be opened, no matter its
        # basename. Prior ad-hoc scripts falsely insisted on "balkon".
        private = "/opt/private-fixture/opaque-worker.py"
        props = show(private)
        before = sorted(self.root.iterdir())
        report = self.collect(
            props, legacy_path_sha=m.digest(private.encode("utf-8")))
        self.assertEqual(report["configured_entrypoint_class"],
                         "HISTORICAL_LEGACY_PATH_FINGERPRINT_MATCH")
        self.assertEqual(report["canonical_public_target"], "ABSENT")
        self.assertFalse(report["process_entrypoint_verified"])
        self.assertFalse(report["broker_subscription_verified"])
        self.assertFalse(report["telegram_delivery_verified"])
        self.assertFalse(report["private_legacy_source_read"])
        self.assertFalse(report["credential_content_read"])
        self.assertFalse(report["writes_performed"])
        self.assertEqual(sorted(self.root.iterdir()), before)
        encoded = json.dumps(report)
        self.assertNotIn(private, encoded)
        self.assertNotIn("opaque-worker", encoded)

    def test_arbitrary_path_is_unattributed_without_bypassing_contract(self):
        props = show("/opt/private/daily-bridge.py")
        result = self.collect(props)
        self.assertEqual(result["configured_entrypoint_class"],
                         "OTHER_PRIVATE_SOURCE_UNATTRIBUTED")
        self.assertFalse(result["configured_source_has_reviewed_mqtt_topic"])

    def test_reviewed_public_source_only_with_exacting_file_provenance(self):
        self.public.write_bytes(self.fake_source)
        self.public.chmod(0o644)
        encrypted = " ".join(
            credential + ":/etc/credstore.encrypted/test-" + str(index)
            for index, credential in enumerate(m.CREDENTIAL_IDS)
        )
        result = self.collect(show(str(m.PUBLIC_TARGET), encrypted=encrypted))
        self.assertEqual(result["configured_entrypoint_class"],
                         "REVIEWED_PUBLIC_SOURCE_CONFIGURED")
        self.assertEqual(result["canonical_public_target"], "REVIEWED_HASH_MATCH")
        self.assertTrue(result["configured_source_has_reviewed_mqtt_topic"])
        self.assertEqual(result["credential_declaration"],
                         "FIVE_ENCRYPTED_IDS_DECLARED")
        self.assertFalse(result["broker_subscription_verified"])
        self.assertFalse(result["telegram_delivery_verified"])
        self.assertFalse(result["process_entrypoint_verified"])
        self.assertNotIn("/etc/credstore", json.dumps(result))

    def test_public_target_missing_or_wrong_hash_blocks_configured_public(self):
        self.block(show(str(m.PUBLIC_TARGET)), "configured_public_source_not_reviewed")
        self.public.write_bytes(b'unexpected bot source')
        self.public.chmod(0o644)
        self.block(show(str(m.PUBLIC_TARGET)), "configured_public_source_not_reviewed")

    def test_unsafe_symlink_public_target_blocks_without_opening_private(self):
        secret_bearing = self.root / "secret-bearing-fixture.py"
        secret_bearing.write_text("FAKE_SECRET_UNSAFE_TEST")
        self.public.symlink_to(secret_bearing)
        self.block(show("/opt/hidden-bot.py"), "public_target_metadata_unsafe")
        self.assertEqual(secret_bearing.read_text(), "FAKE_SECRET_UNSAFE_TEST")

    def test_other_public_target_metadata_blocks(self):
        self.public.write_bytes(self.fake_source)
        self.public.chmod(0o666)
        self.block(show("/opt/hidden-bot.py"), "public_target_metadata_unsafe")

    def test_no_service_or_invalid_pid_blocks(self):
        self.block(show("/opt/hidden-bot.py", active=False), "service_not_active")
        self.block(show("/opt/hidden-bot.py", pid="0"), "service_mainpid_invalid")
        self.block(show("/opt/hidden-bot.py", pid="invalid"), "service_mainpid_invalid")

    def test_invalid_execstart_never_prints_raw(self):
        for raw in (
            "",
            "{ path=/tmp/python3 ; argv[]=/tmp/python3 /tmp/a.py ; ignore_errors=no }",
            "{ path=/usr/bin/python3 ; argv[]=/usr/bin/python3 ; ignore_errors=no }",
            "{ path=/usr/bin/python3 ; argv[]=/usr/bin/python3 /a.py /b.py ; ignore_errors=no }",
        ):
            props = show("/tmp/placeholder.py")
            props["ExecStart"] = raw
            self.block(props, "execstart_invalid")

    def test_metadata_duplicate_missing_and_extra_blocks(self):
        props = show("/opt/private/bot.py")
        text = "\n".join(k + "=" + v for k, v in props.items()) + "\n"
        self.assertEqual(m.parse_properties(text), props)
        for item in (text + "MainPID=2\n",
                     text.replace("MainPID=2435\n", ""),
                     text + "Environment=SECRET_SYNTHETIC\n"):
            with self.assertRaises(m.Blocked):
                m.parse_properties(item)

    def test_credential_class_must_not_imply_valid_credentials(self):
        props = show("/opt/private/worker.py", plaintext="token:/private/SHOULD_NOT_OUTPUT")
        out = self.collect(props)
        self.assertEqual(out["credential_declaration"],
                         "OTHER_OR_PLAINTEXT_MAPPING_PRESENT")
        self.assertNotIn("SHOULD_NOT_OUTPUT", json.dumps(out))
        props = show("/opt/private/worker.py", encrypted="telegram-token:/secure/path")
        self.assertEqual(self.collect(props)["credential_declaration"],
                         "PARTIAL_OR_UNEXPECTED_DECLARATION")

    def test_script_never_reads_private_code_or_process_argv(self):
        code = TOOL.read_text()
        self.assertNotIn("process_argv", code)
        self.assertNotIn("/proc/", code)
        self.assertNotIn("os.environ[", code)
        self.assertNotIn("shell=True", code)
        self.assertNotIn("os.system(", code)
        self.assertNotIn("write_bytes(", code)
        self.assertNotIn("write_text(", code)
        self.assertIn("stderr=subprocess.DEVNULL", code)
        self.assertIn("private_legacy_source_read", code)

    def block(self, props, code):
        with self.assertRaises(m.Blocked) as caught:
            self.collect(props)
        self.assertEqual(str(caught.exception), code)


if __name__ == "__main__":
    unittest.main()
