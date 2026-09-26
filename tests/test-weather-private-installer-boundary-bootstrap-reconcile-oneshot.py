#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "ops/bin/rpi5-weathernext-private-installer-boundary-bootstrap-reconcile-oneshot"


def load_bridge():
    loader = SourceFileLoader("bootstrap_reconcile_oneshot", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError("bridge spec unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def blob_sha(raw: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()


class FakeClient:
    def __init__(self, bridge, source_sha: str, files: dict[str, bytes]):
        self.bridge = bridge
        self.source_sha = source_sha
        self.files = files
        self.paths: list[str] = []
        self.blobs = {path: blob_sha(raw) for path, raw in files.items()}

    def get_json(self, path: str):
        self.paths.append(path)
        if path.endswith("/branches/main"):
            return {"commit": {"sha": self.source_sha}}
        if path.endswith(f"/git/commits/{self.source_sha}"):
            return {"sha": self.source_sha, "tree": {"sha": "1" * 40}}
        if "/git/trees/" in path:
            return {
                "truncated": False,
                "tree": [
                    {"path": name, "type": "blob", "mode": "100644", "sha": self.blobs[name]}
                    for name in (self.bridge.PLAN_PATH, self.bridge.RUNTIME_PATH)
                ],
            }
        for name, raw in self.files.items():
            if f"/contents/{name}?ref={self.source_sha}" in path:
                return {
                    "type": "file",
                    "path": name,
                    "sha": self.blobs[name],
                    "encoding": "base64",
                    "content": base64.b64encode(raw).decode(),
                }
        raise AssertionError(f"unexpected path {path}")


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.bridge = load_bridge()

    def tearDown(self):
        sys.modules.pop("bootstrap_reconcile_oneshot", None)
        for name in (self.bridge.PLAN_MODULE, self.bridge.RUNTIME_MODULE):
            sys.modules.pop(name, None)

    def test_fixed_reachability_identity_and_no_new_privileged_surface(self):
        b = self.bridge
        self.assertEqual(b.TRUSTED_HEAD, "79372e48ac53bf6d00142578b6543bc33a72a692")
        self.assertEqual(b.REPOSITORY, "rozkalnsandris/RPi5_main")
        self.assertEqual(
            {b.PLAN_PATH, b.RUNTIME_PATH},
            {
                "ops/lib/deploy_executor/weather_private_installer_boundary_bootstrap_reconcile.py",
                "ops/lib/deploy_executor/weather_private_installer_boundary_bootstrap_reconcile_runtime.py",
            },
        )
        source = SCRIPT.read_text()
        self.assertNotRegex(source, r"/home/[A-Za-z0-9._-]+/RPi5_main")
        for forbidden in (
            "deploy-authorizations",
            "github-app.pem",
            "git fetch",
            "git reset",
            "git checkout",
            "git clean",
            "shell=True",
        ):
            self.assertNotIn(forbidden, source)

    def test_execute_orders_current_source_load_before_existing_runtime_auth(self):
        b = self.bridge
        events = []
        b.os.geteuid = lambda: 0
        b._trusted_checkout = lambda: events.append("trusted")
        b._exact_current_modules = lambda client: events.append("modules") or ("a" * 40, {})
        b._load_reconcile_runtime = lambda modules: events.append("load") or (
            lambda issue: events.append(("runtime", issue)) or {"ok": issue}
        )
        self.assertEqual(b.execute(743), {"ok": 743})
        self.assertEqual(events, ["trusted", "modules", "load", ("runtime", 743)])

    def test_malformed_current_main_stops_before_module_bytes(self):
        b = self.bridge
        client = FakeClient(
            b,
            "bad",
            {b.PLAN_PATH: b"X=1\n", b.RUNTIME_PATH: b"Y=1\n"},
        )
        with self.assertRaisesRegex(b.OneShotReachabilityError, "current main identity"):
            b._exact_current_modules(client)
        self.assertEqual(client.paths, [f"/repos/{b.REPOSITORY}/branches/main"])

    def test_only_fixed_current_main_module_paths_are_fetched_and_blob_verified(self):
        b = self.bridge
        sha = "a" * 40
        files = {
            b.PLAN_PATH: b"X=1\n",
            b.RUNTIME_PATH: b"IMPLEMENTATION_ISSUE=743\ndef run_privileged_bootstrap_reconcile(issue): return {'ok': issue}\n",
        }
        client = FakeClient(b, sha, files)
        observed_sha, loaded = b._exact_current_modules(client)
        self.assertEqual(observed_sha, sha)
        self.assertEqual(loaded[b.PLAN_MODULE], files[b.PLAN_PATH])
        self.assertEqual(loaded[b.RUNTIME_MODULE], files[b.RUNTIME_PATH])
        self.assertEqual(
            [path for path in client.paths if "/contents/" in path],
            [
                f"/repos/{b.REPOSITORY}/contents/{b.PLAN_PATH}?ref={sha}",
                f"/repos/{b.REPOSITORY}/contents/{b.RUNTIME_PATH}?ref={sha}",
            ],
        )

    def test_loader_exposes_only_fixed_runtime_entrypoint(self):
        b = self.bridge
        old_path = list(sys.path)
        old_modules = {
            name: module
            for name, module in sys.modules.items()
            if name == "deploy_executor" or name.startswith("deploy_executor.")
        }
        try:
            for name in list(sys.modules):
                if name == "deploy_executor" or name.startswith("deploy_executor."):
                    sys.modules.pop(name, None)
            sys.path.insert(0, str(REPO_ROOT / "ops/lib"))
            entry = b._load_reconcile_runtime(
                {
                    b.PLAN_MODULE: b"X=1\n",
                    b.RUNTIME_MODULE: (
                        b"IMPLEMENTATION_ISSUE=743\n"
                        b"def run_privileged_bootstrap_reconcile(issue): return {'ok': issue}\n"
                    ),
                }
            )
            self.assertEqual(entry(17), {"ok": 17})
        finally:
            for name in list(sys.modules):
                if name == "deploy_executor" or name.startswith("deploy_executor."):
                    sys.modules.pop(name, None)
            sys.modules.update(old_modules)
            sys.path[:] = old_path

    def test_runtime_error_becomes_post_entry_fail_closed(self):
        b = self.bridge
        b.os.geteuid = lambda: 0
        b._trusted_checkout = lambda: None
        b._exact_current_modules = lambda client: ("a" * 40, {})
        b._load_reconcile_runtime = lambda modules: (
            lambda issue: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        with self.assertRaises(b.RuntimeEnteredError):
            b.execute(743)

    def test_current_runtime_imports_against_trusted_predecessor_dependencies(self):
        b = self.bridge
        with tempfile.TemporaryDirectory() as td:
            archive = subprocess.run(
                ["git", "archive", b.TRUSTED_HEAD, "ops/lib/deploy_executor"],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout
            tar_path = Path(td) / "deps.tar"
            tar_path.write_bytes(archive)
            with tarfile.open(tar_path) as tf:
                tf.extractall(td, filter="data")
            old_path = list(sys.path)
            old_modules = {
                name: module
                for name, module in sys.modules.items()
                if name == "deploy_executor" or name.startswith("deploy_executor.")
            }
            try:
                for name in list(sys.modules):
                    if name == "deploy_executor" or name.startswith("deploy_executor."):
                        sys.modules.pop(name, None)
                sys.path.insert(0, str(Path(td) / "ops/lib"))
                entry = b._load_reconcile_runtime(
                    {
                        b.PLAN_MODULE: (REPO_ROOT / b.PLAN_PATH).read_bytes(),
                        b.RUNTIME_MODULE: (REPO_ROOT / b.RUNTIME_PATH).read_bytes(),
                    }
                )
                self.assertTrue(callable(entry))
            finally:
                for name in list(sys.modules):
                    if name == "deploy_executor" or name.startswith("deploy_executor."):
                        sys.modules.pop(name, None)
                sys.modules.update(old_modules)
                sys.path[:] = old_path


if __name__ == "__main__":
    unittest.main()
