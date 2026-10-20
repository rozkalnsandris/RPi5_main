from __future__ import annotations

import base64
import hashlib
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, path: Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[name] = module
    loader.exec_module(module)
    return module


sender = load_script(
    "coloring_pages_drive_stage_sender",
    ROOT / "ops/bin/coloring-pages-drive-stage-sender",
)
wrapper = load_script(
    "coloring_pages_drive_stage_rcat",
    ROOT / "ops/libexec/coloring-pages-drive-stage-rcat",
)


def artifact(name: str, mime: str, data: bytes) -> dict[str, object]:
    return {
        "name": name,
        "mime": mime,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "data_b64": base64.b64encode(data).decode("ascii"),
    }


def manifest_v1(activity_id: str, png: bytes) -> dict[str, object]:
    return {
        "schema": sender.MANIFEST_SCHEMA_V1,
        "id": activity_id,
        "sha256": hashlib.sha256(png).hexdigest(),
        "size_bytes": len(png),
        "title": "Martinstag Laterne",
        "character": "",
        "category": "jahreszeiten",
        "age": "3-6",
        "difficulty": "easy",
        "language": "de",
        "source_kind": "chatgpt-generated-png",
        "approval_class": "explicit-owner-chat-approval",
    }


def manifest_v2(activity_id: str, pages: list[bytes]) -> dict[str, object]:
    return {
        "schema": sender.MANIFEST_SCHEMA_V2,
        "id": activity_id,
        "pages": [
            {
                "index": index,
                "file": f"{activity_id}-{index}.png",
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
            for index, data in enumerate(pages, start=1)
        ],
        "title": "Martinszug",
        "character": "",
        "category": "jahreszeiten",
        "age": "3-6",
        "difficulty": "easy",
        "language": "de",
        "source_kind": "chatgpt-generated-png-set",
        "approval_class": "explicit-owner-chat-approval",
    }


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def v1_activity(activity_id: str = "1234567") -> dict[str, object]:
    png = b"\x89PNG\r\nv1"
    manifest = json_bytes(manifest_v1(activity_id, png))
    return {
        "id": activity_id,
        "artifacts": [
            artifact(f"{activity_id}.png", "image/png", png),
            artifact(f"{activity_id}.json", "application/json", manifest),
        ],
    }


def v2_activity(activity_id: str = "7654321") -> dict[str, object]:
    pages = [b"\x89PNG\r\npage1", b"\x89PNG\r\npage2"]
    manifest = json_bytes(manifest_v2(activity_id, pages))
    artifacts = [
        artifact(f"{activity_id}-{index}.png", "image/png", data)
        for index, data in enumerate(pages, start=1)
    ]
    artifacts.append(artifact(f"{activity_id}.json", "application/json", manifest))
    return {"id": activity_id, "artifacts": artifacts}


def envelope(*activities: dict[str, object]) -> bytes:
    return json.dumps(
        {"schema": sender.ENVELOPE_SCHEMA, "activities": list(activities)}
    ).encode()


class FakePrivileged:
    def __init__(self, fail_upload_at: int | None = None):
        self.calls: list[tuple[object, ...]] = []
        self.fail_upload_at = fail_upload_at
        self.upload_count = 0

    def assert_absent(self, names):
        self.calls.append(("assert_absent", tuple(names)))

    def upload(self, item):
        self.upload_count += 1
        self.calls.append(("upload", item.name))
        if self.fail_upload_at == self.upload_count:
            raise sender.SenderError("simulated upload failure")

    def assert_exact(self, item):
        self.calls.append(("assert_exact", item.name, item.size_bytes))


class DriveStageSenderTests(unittest.TestCase):
    def tearDown(self):
        pass

    def test_valid_independent_v1_batch_is_png_then_manifest(self):
        activities = sender.load_and_validate_envelope(
            envelope(v1_activity("1234567"), v1_activity("2345678"))
        )
        try:
            backend = FakePrivileged()
            result = sender.execute_activities(activities, backend)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["artifacts_staged"], 4)
            self.assertEqual(
                backend.calls,
                [
                    (
                        "assert_absent",
                        (
                            "1234567.png",
                            "1234567.json",
                            "2345678.png",
                            "2345678.json",
                        ),
                    ),
                    ("upload", "1234567.png"),
                    ("assert_exact", "1234567.png", 8),
                    ("upload", "1234567.json"),
                    ("assert_exact", "1234567.json", mock.ANY),
                    ("upload", "2345678.png"),
                    ("assert_exact", "2345678.png", 8),
                    ("upload", "2345678.json"),
                    ("assert_exact", "2345678.json", mock.ANY),
                ],
            )
        finally:
            sender.close_activities(activities)

    def test_valid_v2_binds_ordered_pages_before_manifest(self):
        activities = sender.load_and_validate_envelope(envelope(v2_activity()))
        try:
            self.assertEqual(
                [item.name for item in activities[0].artifacts],
                ["7654321-1.png", "7654321-2.png", "7654321.json"],
            )
        finally:
            sender.close_activities(activities)

    def test_hash_mismatch_fails_before_backend(self):
        raw = v1_activity()
        raw["artifacts"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(sender.SenderError, "SHA-256"):
            sender.load_and_validate_envelope(envelope(raw))

    def test_invalid_base64_fails(self):
        raw = v1_activity()
        raw["artifacts"][0]["data_b64"] = "!!!not-base64!!!"
        with self.assertRaisesRegex(sender.SenderError, "base64"):
            sender.load_and_validate_envelope(envelope(raw))

    def test_manifest_must_be_last(self):
        raw = v1_activity()
        raw["artifacts"].reverse()
        with self.assertRaisesRegex(sender.SenderError, "manifest must be last"):
            sender.load_and_validate_envelope(envelope(raw))

    def test_duplicate_activity_id_fails(self):
        with self.assertRaisesRegex(sender.SenderError, "duplicate activity id"):
            sender.load_and_validate_envelope(
                envelope(v1_activity("1234567"), v1_activity("1234567"))
            )

    def test_v2_manifest_page_binding_mismatch_fails(self):
        raw = v2_activity()
        manifest_artifact = raw["artifacts"][-1]
        manifest = json.loads(base64.b64decode(manifest_artifact["data_b64"]))
        manifest["pages"][0]["size_bytes"] += 1
        data = json_bytes(manifest)
        raw["artifacts"][-1] = artifact("7654321.json", "application/json", data)
        with self.assertRaisesRegex(sender.SenderError, "page binding"):
            sender.load_and_validate_envelope(envelope(raw))

    def test_failure_after_first_upload_stops_all_later_artifacts(self):
        activities = sender.load_and_validate_envelope(
            envelope(v1_activity("1234567"), v1_activity("2345678"))
        )
        try:
            backend = FakePrivileged(fail_upload_at=1)
            with self.assertRaisesRegex(sender.SenderError, "simulated"):
                sender.execute_activities(activities, backend)
            self.assertEqual(
                backend.calls,
                [
                    (
                        "assert_absent",
                        (
                            "1234567.png",
                            "1234567.json",
                            "2345678.png",
                            "2345678.json",
                        ),
                    ),
                    ("upload", "1234567.png"),
                ],
            )
        finally:
            sender.close_activities(activities)

    def test_wrapper_rejects_arbitrary_names_and_sizes(self):
        with self.assertRaises(wrapper.WrapperError):
            wrapper.validate_name("../../evil.png")
        with self.assertRaises(wrapper.WrapperError):
            wrapper.validate_name("1234567.txt")
        with self.assertRaises(wrapper.WrapperError):
            wrapper.validate_size("1234567.json", str(wrapper.MAX_MANIFEST_BYTES + 1))

    def test_wrapper_rclone_command_disables_retry_classes(self):
        with mock.patch.object(wrapper, "check_runtime_metadata", return_value=None):
            command = wrapper.base_command()
        self.assertIn("--drive-root-folder-id", command)
        self.assertIn(wrapper.ROOT_FOLDER_ID, command)
        self.assertEqual(command[command.index("--retries") + 1], "1")
        self.assertEqual(command[command.index("--low-level-retries") + 1], "1")
        self.assertEqual(command[command.index("--retries-sleep") + 1], "0s")

    def test_wrapper_upload_prechecks_target_and_uses_rcat_exact_size(self):
        seen = {}

        def fake_run(argv, **kwargs):
            seen["argv"] = argv
            seen["stdin"] = kwargs.get("stdin")
            return types.SimpleNamespace(returncode=0, stdout="")

        source = io.BytesIO(b"abc")
        with mock.patch.object(wrapper, "assert_absent") as absent, \
             mock.patch.object(wrapper, "check_runtime_metadata", return_value=None), \
             mock.patch.object(wrapper.subprocess, "run", side_effect=fake_run):
            old_stdin = wrapper.sys.stdin
            try:
                wrapper.sys.stdin = types.SimpleNamespace(buffer=source)
                wrapper.upload("1234567.png", 3)
            finally:
                wrapper.sys.stdin = old_stdin

        absent.assert_called_once_with(["1234567.png"])
        self.assertIn("rcat", seen["argv"])
        self.assertIn("gdrive:pending/1234567.png", seen["argv"])
        size_pos = seen["argv"].index("--size")
        self.assertEqual(seen["argv"][size_pos + 1], "3")
        self.assertIs(seen["stdin"], source)

    def test_contract_and_installer_remain_source_only(self):
        contract_path = ROOT / "ops/contracts/coloring-pages-drive-stage-sender-v1.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        self.assertEqual(contract["issue"], 1128)
        self.assertEqual(contract["status"], "source-defined-not-installed")
        self.assertFalse(contract["installer"]["runs_rclone"])
        self.assertFalse(contract["installer"]["writes_drive"])
        self.assertFalse(contract["activation"]["source_merge_authorizes_live"])

        installer = (
            ROOT / "scripts/install-coloring-pages-drive-stage-sender-v1.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("RCLONE_EXECUTED=false", installer)
        self.assertIn("DRIVE_WRITE=false", installer)
        self.assertNotIn(" rclone ", installer.lower())


if __name__ == "__main__":
    unittest.main()
