"""Source-only Gateway synthetic vision ingress/HTTP boundary tests.

No provider SDK, sockets, production host, Telegram, database, Hermes config
or real images. A fake handle_request delegate is never an actual HTTP call.
"""

from __future__ import annotations

import json
import socket
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from hermes_gateway_vision_guard_v1 import (  # noqa: E402
    BoundaryRejected, ENDPOINT, NotReady, OfflineSingleDispatchHttpTransport,
    UPSTREAM_BLOBS, UPSTREAM_COMMIT, gateway_ingress_envelope,
    require_fixed_http_request, require_live_transport_readiness,
    verify_source_pin,
)
from hermes_synthetic_vision_probe_v1 import (  # noqa: E402
    FIXTURE_REF, IMAGE_MODE, MODEL, PROVIDER, synthetic_request,
)


def allowed() -> dict:
    return dict(
        image_refs=(FIXTURE_REF,), image_mode=IMAGE_MODE,
        provider=PROVIDER, model=MODEL,
        installed_revision=UPSTREAM_COMMIT, installed_blobs=dict(UPSTREAM_BLOBS),
    )


def fake_http_request(**changes):
    payload = json.dumps(synthetic_request()).encode("utf-8")
    return SimpleNamespace(method="POST", url=ENDPOINT, content=payload, **changes)


class SourceIdentityTests(unittest.TestCase):
    def test_source_pin_requires_all_four_exact_git_blobs(self):
        verify_source_pin(UPSTREAM_COMMIT, dict(UPSTREAM_BLOBS))
        for changes in (
            ("unverified", dict(UPSTREAM_BLOBS)),
            (UPSTREAM_COMMIT, None),
            (UPSTREAM_COMMIT, {"gateway/run_inbound.py": "0" * 40}),
            (UPSTREAM_COMMIT, {**UPSTREAM_BLOBS, "gateway/run_inbound.py": "0" * 40}),
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(NotReady):
                    verify_source_pin(*changes)

    def test_gateway_metadata_fixture_only_before_media_access(self):
        with patch("builtins.open", side_effect=AssertionError("READ_ATTEMPT")), (
            patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK"))):
            req = gateway_ingress_envelope(**allowed())
        self.assertEqual(req, synthetic_request())
        self.assertEqual(req["extra_body"]["provider"]["max_price"],
                         {"prompt": 0, "completion": 0, "image": 0, "request": 0})
        self.assertIs(req["extra_body"]["provider"]["allow_fallbacks"], False)

    def test_deny_real_media_native_fanout_and_paid_route(self):
        alternatives = [
            {"image_refs": ("/private/photo.jpg",)},
            {"image_refs": ("https://example.org/image.png",)},
            {"image_refs": ("data:image/png;base64,AAAA",)},
            {"image_refs": (FIXTURE_REF, FIXTURE_REF)},
            {"image_refs": tuple()},
            {"image_refs": [FIXTURE_REF]},
            {"image_mode": "native"},
            {"provider": "nous"},
            {"model": "nvidia/nemotron-3.5-super-vl"},
            {"model": "openrouter/free"},
            {"model": "google/gemma-4-31b-it:free"},
        ]
        with patch("builtins.open", side_effect=AssertionError("READ_ATTEMPT")):
            for delta in alternatives:
                with self.subTest(case=delta):
                    with self.assertRaises(BoundaryRejected):
                        gateway_ingress_envelope(**{**allowed(), **delta})

    def test_unverified_installed_source_fails_before_any_fanout(self):
        with self.assertRaises(NotReady):
            gateway_ingress_envelope(**{**allowed(), "installed_revision": "unknown"})


class HttpBoundaryTests(unittest.TestCase):
    def test_exact_fixed_http_body_only(self):
        require_fixed_http_request(fake_http_request())
        self.assertEqual(len(fake_http_request().content), len(
            json.dumps(synthetic_request()).encode("utf-8")))

    def test_denies_other_urls_body_models_and_paid_fallback(self):
        body = synthetic_request()
        cases = [
            ("GET", ENDPOINT, body),
            ("POST", "https://example.invalid/api/v1/chat/completions", body),
            ("POST", ENDPOINT + "?other=1", body),
            ("POST", ENDPOINT, {**body, "model": "nvidia/nemotron-3.5-super-vl"}),
            ("POST", ENDPOINT, {**body, "extra_body": {"provider": {"allow_fallbacks": True}}}),
            ("POST", ENDPOINT, {**body, "messages": []}),
            ("POST", ENDPOINT, {**body, "temperature": 0}),
        ]
        for method, url, payload in cases:
            with self.subTest(method=method, url=url):
                request = SimpleNamespace(method=method, url=url,
                    content=json.dumps(payload).encode("utf-8"))
                with self.assertRaises(BoundaryRejected):
                    require_fixed_http_request(request)
        for payload in (b"{}wrong", b"\xff", b"x" * 24001, None):
            with self.subTest(payload_length=len(payload) if payload else 0):
                req = SimpleNamespace(method="POST", url=ENDPOINT, content=payload)
                with self.assertRaises(BoundaryRejected):
                    require_fixed_http_request(req)

    def test_single_httpx_entry_and_reentry_rejected(self):
        sent = Mock()
        sent.handle_request.return_value = SimpleNamespace(status_code=200)
        transport = OfflineSingleDispatchHttpTransport(sent)
        # The adapter must call a real duck-typed handle_request method,
        # never a higher level completions.create wrapper.
        with self.assertRaises(NotReady):
            OfflineSingleDispatchHttpTransport(Mock(), transport_class="LIVE")
        request = fake_http_request()
        with patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK")), (
            patch("builtins.open", side_effect=AssertionError("FS_WRITE"))):
            result = transport.handle_request(request)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(transport.transport_entries, 1)
        sent.handle_request.assert_called_once_with(request)
        with self.assertRaisesRegex(BoundaryRejected, "SECOND_HTTP_DISPATCH"):
            transport.handle_request(request)
        sent.handle_request.assert_called_once_with(request)

    def test_timeout_error_and_empty_result_never_retry(self):
        for response in (TimeoutError(), RuntimeError("size error"),
                         RuntimeError("429"), None, "",
                         SimpleNamespace(status_code=500)):
            with self.subTest(response=type(response).__name__):
                if isinstance(response, Exception):
                    delegate = Mock()
                    delegate.handle_request.side_effect = response
                else:
                    delegate = Mock()
                    delegate.handle_request.return_value = response
                transport = OfflineSingleDispatchHttpTransport(delegate)
                if isinstance(response, Exception):
                    with self.assertRaises(Exception):
                        transport.handle_request(fake_http_request())
                else:
                    transport.handle_request(fake_http_request())
                self.assertEqual(transport.transport_entries, 1)
                with self.assertRaisesRegex(BoundaryRejected, "SECOND_HTTP_DISPATCH"):
                    transport.handle_request(fake_http_request())
                self.assertEqual(delegate.handle_request.call_count, 1)

    def test_bad_payload_does_not_dispatch(self):
        delegate = Mock()
        transport = OfflineSingleDispatchHttpTransport(delegate)
        with self.assertRaises(BoundaryRejected):
            transport.handle_request(SimpleNamespace(
                method="POST", url=ENDPOINT, content=b"{}"))
        delegate.handle_request.assert_not_called()
        self.assertEqual(transport.transport_entries, 0)

    def test_reentrant_delegate_cannot_call_transport_twice(self):
        delegate = Mock()
        transport = OfflineSingleDispatchHttpTransport(delegate)

        def sender(request):
            with self.assertRaisesRegex(BoundaryRejected, "SECOND_HTTP_DISPATCH"):
                transport.handle_request(request)
            return SimpleNamespace(status_code=200)

        delegate.handle_request.side_effect = sender
        transport.handle_request(fake_http_request())
        self.assertEqual(delegate.handle_request.call_count, 1)

    def test_live_proof_remains_not_ready(self):
        for verified in (False, True):
            with self.subTest(verified=verified):
                with self.assertRaisesRegex(NotReady, "INTEGRATION_NOT_INSTALLED"):
                    require_live_transport_readiness(
                        installed_provenance_verified=verified,
                        outbound_sdk_retry_setting=0,
                        http_transport_retries=0,
                        gateway_retry_suppressed=True,
                    )

    def test_makefile_wiring(self):
        content = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("python3 ./tests/test-hermes-gateway-vision-guard-v1.py", content)


if __name__ == "__main__":
    unittest.main()
