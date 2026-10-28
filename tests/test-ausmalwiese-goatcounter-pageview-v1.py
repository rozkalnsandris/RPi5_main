"""Disconnected tests for Ausmalwiese GoatCounter #1224 source.

No RPi5 runtime, public request, production catalog, credential, database or
GoatCounter process is touched.
"""
import contextlib
import gzip
import hashlib
import importlib
import importlib.util
import io
import json
import os
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ausmalwiese_goatcounter_pageview_adapter_v1 as adapter  # noqa: E402
import ausmalwiese_goatcounter_isolated_probe_v1 as runtime  # noqa: E402


class FakeResponse:
    status = 202

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n):
        return b""


class FakeOpener:
    def __init__(self, response=None, error=None):
        self.calls = []
        self.response = response or FakeResponse()
        self.error = error

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        if self.error:
            raise self.error
        return self.response


def catalog_entry(page_id="0427183", **updates):
    item = {
        "id": page_id,
        "preview": f"/media/{page_id}/preview.webp",
        "print": f"/media/{page_id}/print.png",
    }
    item.update(updates)
    return item


class AdapterContractTests(unittest.TestCase):
    def test_machine_contract_exact(self):
        adapter.check_contract()
        data = json.loads(
            (ROOT / "ops/contracts/ausmalwiese-goatcounter-pageview-v1.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(data, adapter.expected_contract())
        self.assertFalse(data["boundaries"]["allow_live"])
        self.assertFalse(data["boundaries"]["allow_install"])
        self.assertFalse(data["boundaries"]["forward_client_headers"])

    def accept(self, body=b'{"page_id":"0427183"}', catalog=None, **updates):
        args = {
            "method": "POST",
            "request_target": "/api/pageview",
            "host": "ausmalwiese.de",
            "origin": "https://ausmalwiese.de",
            "content_type": "application/json",
            "raw_body": body,
            "catalog": [catalog_entry()] if catalog is None else catalog,
        }
        args.update(updates)
        return adapter.accept_event(**args)

    def assert_stop(self, code, **kwargs):
        with self.assertRaisesRegex(adapter.AdapterStop, "^" + code + "$"):
            self.accept(**kwargs)

    def test_exact_valid_leading_zero_event(self):
        self.assertEqual(self.accept(), "0427183")
        self.assertEqual(
            adapter.backend_body("0427183"),
            b'{"no_sessions":true,"hits":[{"path":"/coloring-page/0427183"}]}',
        )

    def test_extra_duplicate_numeric_hidden_and_unknown_inputs_fail(self):
        self.assert_stop(
            "CLIENT_SCHEMA",
            body=b'{"page_id":"0427183","ip":"203.0.113.8"}',
        )
        self.assert_stop(
            "JSON_DUPLICATE_KEY",
            body=b'{"page_id":"0427183","page_id":"1234567"}',
        )
        self.assert_stop("CLIENT_PAGE_ID", body=b'{"page_id":427183}')
        self.assert_stop(
            "CLIENT_PAGE_NOT_PUBLISHED",
            catalog=[catalog_entry(hidden=True)],
        )
        self.assert_stop(
            "CLIENT_PAGE_NOT_PUBLISHED",
            catalog=[catalog_entry("1234567")],
        )

    def test_origin_host_route_content_type_and_query_are_strict(self):
        self.assert_stop("CLIENT_ROUTE_OR_METHOD", request_target="/api/pageview?x=1")
        self.assert_stop("CLIENT_HOST", host="evil.example")
        self.assert_stop("CLIENT_ORIGIN", origin="https://www.ausmalwiese.de")
        self.assert_stop("CLIENT_CONTENT_TYPE", content_type="text/plain")
        self.assertEqual(
            self.accept(
                host="www.ausmalwiese.de",
                origin="https://www.ausmalwiese.de",
                content_type="application/json; charset=UTF-8",
            ),
            "0427183",
        )

    def test_catalog_loader_rejects_duplicate_ids_and_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "catalog.json"
            path.write_text(
                json.dumps([catalog_entry(), catalog_entry()]),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(adapter.AdapterStop, "^CATALOG_DUPLICATE_ID$"):
                adapter.published_page_ids(adapter.load_catalog(path))
            target = root / "real.json"
            target.write_text(json.dumps([catalog_entry()]), encoding="utf-8")
            link = root / "link.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(adapter.AdapterStop, "^CATALOG_UNAVAILABLE$"):
                adapter.load_catalog(link)

    def test_backend_dispatch_is_one_attempt_and_never_uses_client_metadata(self):
        opener = FakeOpener()
        adapter.dispatch_once("0427183", "synthetic-token-123456", opener=opener)
        self.assertEqual(len(opener.calls), 1)
        request, timeout = opener.calls[0]
        self.assertEqual(timeout, 5)
        self.assertEqual(
            request.full_url,
            "http://127.0.0.1:9194/api/v0/count",
        )
        self.assertEqual(request.get_header("Host"), adapter.GOATCOUNTER_HOST)
        self.assertEqual(
            json.loads(request.data),
            {
                "no_sessions": True,
                "hits": [{"path": "/coloring-page/0427183"}],
            },
        )
        for forbidden in (
            "User-agent", "Referer", "Cookie", "X-forwarded-for",
            "Cf-connecting-ip",
        ):
            self.assertNotIn(forbidden, request.headers)

    def test_ambiguous_backend_failure_is_not_retried(self):
        opener = FakeOpener(error=OSError("synthetic timeout"))
        with self.assertRaisesRegex(
            adapter.AdapterStop, "^BACKEND_RESPONSE_UNCERTAIN$"
        ):
            adapter.dispatch_once(
                "0427183", "synthetic-token-123456", opener=opener
            )
        self.assertEqual(len(opener.calls), 1)

    def test_handler_disables_builtin_request_logging(self):
        source = (ROOT / "scripts/ausmalwiese_goatcounter_pageview_adapter_v1.py").read_text()
        self.assertIn("def log_message(self, format, *args):", source)
        self.assertIn("def handle_error(self, request, client_address):", source)
        self.assertNotIn("print(self.path", source)
        handler_body = source.split("def handle_error", 1)[1].split("class Handler", 1)[0]
        self.assertNotIn("print(", handler_body)
        self.assertNotIn("sys.stderr", handler_body)

    def test_existing_public_compose_is_not_wired_to_new_services(self):
        compose = (
            ROOT / "ops/deploy/simple-deploy-compose/coloring-pages-public.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('"127.0.0.1:9191:8080"', compose)
        self.assertNotIn("9193", compose)
        self.assertNotIn("9194", compose)
        self.assertNotIn("goatcounter", compose.casefold())

    def test_systemd_sources_are_loopback_only_and_resource_bounded(self):
        for name, port in (
            ("ausmalwiese-goatcounter.service", "127.0.0.1:9194"),
            ("ausmalwiese-goatcounter-pageview.service", None),
        ):
            text = (ROOT / "ops/systemd" / name).read_text(encoding="utf-8")
            self.assertIn("IPAddressDeny=any", text)
            self.assertIn("IPAddressAllow=localhost", text)
            self.assertIn("MemoryMax=", text)
            self.assertIn("CPUQuota=", text)
            self.assertIn("TasksMax=", text)
            self.assertIn("StandardOutput=null", text)
            self.assertIn("StandardError=null", text)
            self.assertNotIn("0.0.0.0", text)
            if port:
                self.assertIn(port, text)


class InstalledAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.install = self.root / "libexec/ausmalwiese-goatcounter-v1"
        self.install.mkdir(parents=True)
        script = self.install / "pageview-adapter.py"
        script.write_text(Path(adapter.__file__).read_text(), encoding="utf-8")
        spec = importlib.util.spec_from_file_location("installed_adapter", script)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.contract = self.install / "pageview-contract.json"
        self.contract.write_text(json.dumps(adapter.expected_contract()), encoding="utf-8")

    def invoke(self, arguments):
        output = io.StringIO()
        with mock.patch.object(self.module, "QuietThreadingHTTPServer") as server:
            with contextlib.redirect_stdout(output):
                result = self.module.main(arguments)
        return result, output.getvalue(), server

    def test_unit_argv_starts_relocated_adapter_with_colocated_contract(self):
        unit = (ROOT / "ops/systemd/ausmalwiese-goatcounter-pageview.service").read_text()
        start = next(line.removeprefix("ExecStart=") for line in unit.splitlines()
                     if line.startswith("ExecStart="))
        argv = shlex.split(start)
        prefix = "/usr/local/libexec/ausmalwiese-goatcounter-v1/"
        self.assertEqual(argv[0], prefix + "pageview-adapter.py")
        self.assertIn("ConditionPathExists=" + prefix + "pageview-contract.json", unit)
        arguments = [arg.replace(prefix, str(self.install) + "/") for arg in argv[1:]]
        result, _, server = self.invoke(arguments)
        self.assertEqual(result, 0)
        server.assert_called_once_with(("127.0.0.1", 9193), self.module.Handler)
        server.return_value.serve_forever.assert_called_once_with(poll_interval=0.5)

    def test_explicit_contract_check_works_without_repository_tree(self):
        result, output, server = self.invoke(["--check-contract", "--contract", str(self.contract)])
        self.assertEqual(result, 0)
        self.assertIn("SOURCE_OK_NOT_LIVE", output)
        server.assert_not_called()

    def test_missing_contract_stops_before_binding(self):
        self.contract.unlink()
        result, output, server = self.invoke(["--serve", "--contract", str(self.contract)])
        self.assertEqual(result, 2)
        self.assertIn("CODE=CONTRACT_UNAVAILABLE", output)
        server.assert_not_called()

    def test_contract_drift_stops_before_binding(self):
        data = adapter.expected_contract()
        data["boundaries"]["allow_live"] = True
        self.contract.write_text(json.dumps(data), encoding="utf-8")
        result, output, server = self.invoke(["--serve", "--contract", str(self.contract)])
        self.assertEqual(result, 2)
        self.assertIn("CODE=CONTRACT_DRIFT", output)
        server.assert_not_called()

    def test_malformed_contract_stops_before_binding(self):
        self.contract.write_text("{", encoding="utf-8")
        result, output, server = self.invoke(["--serve", "--contract", str(self.contract)])
        self.assertEqual(result, 2)
        self.assertIn("CODE=CONTRACT_UNAVAILABLE", output)
        server.assert_not_called()


class RuntimeProofSourceTests(unittest.TestCase):
    def test_only_arm64_release_asset_is_pinned(self):
        self.assertEqual(
            runtime.RELEASE_ASSETS,
            {
                "arm64": {
                    "name": "goatcounter-v2.7.0-linux-arm64.gz",
                    "size": 12770791,
                    "sha256": (
                        "ff5b2670b858bbe48802dfdc74130b6d"
                        "cde2de9f5c1229b838eb9132769307dd"
                    ),
                }
            },
        )

    def test_runtime_host_guard_requires_nonroot_rpi5_arm64_linux(self):
        with mock.patch.object(runtime.os, "geteuid", return_value=1000),              mock.patch.object(runtime.platform, "node", return_value="rpi5"),              mock.patch.object(runtime.platform, "system", return_value="Linux"),              mock.patch.object(runtime.platform, "machine", return_value="aarch64"):
            runtime._host_guard()
        with mock.patch.object(runtime.os, "geteuid", return_value=0),              mock.patch.object(runtime.platform, "node", return_value="rpi5"):
            with self.assertRaisesRegex(runtime.RuntimeStop, "^ROOT_FORBIDDEN$"):
                runtime._host_guard()
        with mock.patch.object(runtime.os, "geteuid", return_value=1000),              mock.patch.object(runtime.platform, "node", return_value="ci"):
            with self.assertRaisesRegex(runtime.RuntimeStop, "^WRONG_TEST_HOST$"):
                runtime._host_guard()

    def test_release_archive_must_be_direct_child_of_tmp_and_is_verified(self):
        payload = b"synthetic-goatcounter-binary"
        name = "goatcounter-synthetic-arm64.gz"
        path = Path("/tmp") / name
        root_tmp = tempfile.TemporaryDirectory(prefix="goatcounter-offline-", dir="/tmp")
        self.addCleanup(root_tmp.cleanup)
        root = Path(root_tmp.name)
        try:
            with gzip.open(path, "wb") as handle:
                handle.write(payload)
            asset = {
                "name": name,
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            with mock.patch.object(
                runtime, "_release_asset_for_host", return_value=asset
            ):
                binary = runtime._verified_release_archive(str(path), root)
            self.assertEqual(binary.read_bytes(), payload)
            self.assertTrue(os.access(binary, os.X_OK))
        finally:
            path.unlink(missing_ok=True)

    def test_probe_source_has_no_downloader_or_production_paths(self):
        source = (
            ROOT / "scripts/ausmalwiese_goatcounter_isolated_probe_v1.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("urlretrieve(", source)
        self.assertNotIn('subprocess.run(["curl"', source)
        self.assertNotIn('subprocess.run(["wget"', source)
        self.assertNotIn("/srv/coloring-pages-content", source)
        self.assertNotIn("/var/lib/ausmalwiese-goatcounter", source)
        self.assertIn('dir="/tmp"', source)


if __name__ == "__main__":
    unittest.main()
