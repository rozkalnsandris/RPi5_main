#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import traceback
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "lib"))

from deploy_executor.transport import (  # noqa: E402
    ACCEPT_HEADER,
    API_VERSION,
    AUTHORIZATION_REPOSITORY,
    AUTHORIZATION_REPOSITORY_ID,
    CacheIntegrityError,
    DisabledResultWriter,
    GitHubRestClient,
    HTTPResponse,
    IdentityError,
    InstallationToken,
    NetworkFailure,
    PaginationError,
    PersistentETagStore,
    RateLimitError,
    RedirectError,
    ResponseError,
    ResultReportingDisabled,
    TokenError,
)

DATE = "Thu, 27 Aug 2026 21:30:00 GMT"
NOW = datetime(2026, 8, 27, 21, 30, 0, tzinfo=timezone.utc)
TOKEN = "ghs_4537106_stateless_example_token_with_variable_length_abcdefghijklmnopqrstuvwxyz"


def response(status=200, payload=None, headers=None):
    merged = {"Date": DATE}
    if headers:
        merged.update(headers)
    if payload is None:
        body = b""
    elif isinstance(payload, bytes):
        body = payload
    else:
        body = json.dumps(payload).encode("utf-8")
    return HTTPResponse(status=status, headers=merged, body=body)


class FakeTokenProvider:
    def __init__(self, token=None, error=None):
        self.token = token or InstallationToken(TOKEN, NOW + timedelta(minutes=30))
        self.error = error

    def get_installation_token(self):
        if self.error is not None:
            raise self.error
        return self.token


class FakeSender:
    def __init__(self, sequence):
        self.sequence = list(sequence)
        self.calls = []

    def send(self, *, method, url, headers):
        self.calls.append((method, url, dict(headers)))
        if not self.sequence:
            raise AssertionError("unexpected sender call")
        item = self.sequence.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class ListLogger:
    def __init__(self):
        self.events = []

    def emit(self, event, **fields):
        self.events.append((event, fields))


def client(sequence, *, tmp=None, logger=None, token_provider=None, attempts=3):
    sender = FakeSender(sequence)
    store = PersistentETagStore(Path(tmp) / "etag.json") if tmp is not None else None
    logger = logger or ListLogger()
    sleeps = []
    gh = GitHubRestClient(
        token_provider=token_provider or FakeTokenProvider(),
        sender=sender,
        etag_store=store,
        logger=logger,
        sleeper=sleeps.append,
        clock=lambda: NOW,
        max_transport_attempts=attempts,
        backoff_seconds=(1.0, 2.0, 4.0, 8.0),
    )
    return gh, sender, logger, sleeps


class P2TransportTests(unittest.TestCase):
    def test_exact_version_headers_and_opaque_token(self):
        gh, sender, logger, _ = client([response(payload={"ok": True})])
        self.assertEqual(gh.get_json("/meta").value, {"ok": True})
        headers = sender.calls[0][2]
        self.assertEqual(headers["Accept"], ACCEPT_HEADER)
        self.assertEqual(headers["X-GitHub-Api-Version"], API_VERSION)
        self.assertEqual(headers["Authorization"], f"Bearer {TOKEN}")
        self.assertNotIn(TOKEN, repr(FakeTokenProvider().token))
        self.assertTrue(all(TOKEN not in repr(event) for event in logger.events))

    def test_conditional_etag_persists_and_304_is_poll_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            gh, sender, _, _ = client(
                [
                    response(payload=[{"id": 1}], headers={"ETag": '"abc"'}),
                    response(status=304, headers={"ETag": '"abc"'}),
                ],
                tmp=tmp,
            )
            first = gh.conditional_get_json("/repos/rozkalnsandris/ops-workflows/issues?state=open")
            self.assertFalse(first.not_modified)
            second = gh.conditional_get_json("/repos/rozkalnsandris/ops-workflows/issues?state=open")
            self.assertTrue(second.not_modified)
            self.assertIsNone(second.value)
            self.assertEqual(sender.calls[1][2]["If-None-Match"], '"abc"')
            self.assertNotIn(TOKEN, (Path(tmp) / "etag.json").read_text())

    def test_fresh_get_never_uses_if_none_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PersistentETagStore(Path(tmp) / "etag.json")
            store.put("https://api.github.com/meta", '"abc"')
            sender = FakeSender([response(payload={"ok": True})])
            gh = GitHubRestClient(
                token_provider=FakeTokenProvider(), sender=sender, etag_store=store,
                clock=lambda: NOW, backoff_seconds=(1.0, 2.0),
            )
            gh.get_json("/meta")
            self.assertNotIn("If-None-Match", sender.calls[0][2])

    def test_etag_cache_corruption_and_growth_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "etag.json"
            path.write_text("{bad json", encoding="utf-8")
            with self.assertRaises(CacheIntegrityError):
                PersistentETagStore(path)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "etag.json"
            payload = {
                "schema": PersistentETagStore.SCHEMA,
                "entries": {f"{i:064x}": '"x"' for i in range(1025)},
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(CacheIntegrityError):
                PersistentETagStore(path)

    def test_redirect_boundary_rejects_foreign_host(self):
        gh, sender, logger, _ = client(
            [response(status=302, headers={"Location": "https://evil.example/steal"})]
        )
        with self.assertRaises(RedirectError):
            gh.get_json("/meta")
        self.assertEqual(len(sender.calls), 1)
        self.assertTrue(all(TOKEN not in repr(event) for event in logger.events))

    def test_same_host_redirect_is_bounded_and_drops_old_etag(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PersistentETagStore(Path(tmp) / "etag.json")
            store.put("https://api.github.com/meta", '"abc"')
            sender = FakeSender(
                [
                    response(status=301, headers={"Location": "https://api.github.com/meta2"}),
                    response(payload={"ok": 2}),
                ]
            )
            gh = GitHubRestClient(
                token_provider=FakeTokenProvider(), sender=sender, etag_store=store,
                clock=lambda: NOW, backoff_seconds=(1.0, 2.0),
            )
            self.assertEqual(gh.conditional_get_json("/meta").value, {"ok": 2})
            self.assertIn("If-None-Match", sender.calls[0][2])
            self.assertNotIn("If-None-Match", sender.calls[1][2])

    def test_retry_after_rate_limit_never_retries_inline(self):
        gh, sender, _, sleeps = client(
            [response(status=429, payload={"message": "rate limit"}, headers={"Retry-After": "17"})]
        )
        with self.assertRaises(RateLimitError) as caught:
            gh.get_json("/meta")
        self.assertEqual(caught.exception.retry_after_seconds, 17)
        self.assertEqual(len(sender.calls), 1)
        self.assertEqual(sleeps, [])

    def test_primary_and_secondary_rate_limit_delays(self):
        reset = int(NOW.timestamp()) + 45
        gh, _, _, _ = client(
            [response(status=403, payload={"message": "API rate limit exceeded"}, headers={
                "X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset)
            })]
        )
        with self.assertRaises(RateLimitError) as caught:
            gh.get_json("/meta")
        self.assertEqual(caught.exception.retry_after_seconds, 45)
        gh, _, _, _ = client(
            [response(status=403, payload={"message": "You have exceeded a secondary rate limit."})]
        )
        with self.assertRaises(RateLimitError) as caught:
            gh.get_json("/meta")
        self.assertEqual(caught.exception.retry_after_seconds, 60)

    def test_transient_transport_retry_has_hard_ceiling(self):
        gh, sender, _, sleeps = client(
            [response(status=503), response(status=502), response(payload={"ok": True})]
        )
        self.assertEqual(gh.get_json("/meta").value, {"ok": True})
        self.assertEqual(len(sender.calls), 3)
        self.assertEqual(sleeps, [1.0, 2.0])

    def test_network_and_token_errors_do_not_log_or_trace_secret_text(self):
        logger = ListLogger()
        gh, _, _, sleeps = client(
            [NetworkFailure(f"secret={TOKEN}"), response(payload={"ok": True})], logger=logger
        )
        self.assertEqual(gh.get_json("/meta").value, {"ok": True})
        self.assertEqual(sleeps, [1.0])
        self.assertTrue(all(TOKEN not in repr(item) for item in logger.events))

        logger = ListLogger()
        provider = FakeTokenProvider(error=RuntimeError(f"token was {TOKEN}"))
        gh, sender, _, _ = client([], logger=logger, token_provider=provider)
        try:
            gh.get_json("/meta")
        except TokenError as exc:
            rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            self.assertNotIn(TOKEN, rendered)
        else:
            self.fail("expected TokenError")
        self.assertEqual(sender.calls, [])
        self.assertTrue(all(TOKEN not in repr(item) for item in logger.events))

        logger = ListLogger()
        gh, sender, _, _ = client(
            [NetworkFailure(f"secret={TOKEN}")], logger=logger, attempts=1
        )
        try:
            gh.get_json("/meta")
        except NetworkFailure as exc:
            rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            self.assertNotIn(TOKEN, rendered)
        else:
            self.fail("expected NetworkFailure")
        self.assertEqual(len(sender.calls), 1)
        self.assertTrue(all(TOKEN not in repr(item) for item in logger.events))

    def test_token_is_opaque_but_expiry_and_controls_are_checked(self):
        expired = FakeTokenProvider(InstallationToken(TOKEN, NOW - timedelta(seconds=1)))
        gh, sender, _, _ = client([], token_provider=expired)
        with self.assertRaises(TokenError):
            gh.get_json("/meta")
        self.assertEqual(sender.calls, [])
        bad = FakeTokenProvider(InstallationToken("ghs_bad\nheader", NOW + timedelta(minutes=5)))
        gh, sender, _, _ = client([], token_provider=bad)
        with self.assertRaises(TokenError):
            gh.get_json("/meta")
        self.assertEqual(sender.calls, [])

    def test_pagination_follows_link_and_rejects_foreign_or_loops(self):
        next_url = "https://api.github.com/repos/rozkalnsandris/ops-workflows/issues?page=2"
        gh, sender, _, _ = client([
            response(payload=[1, 2], headers={"Link": f'<{next_url}>; rel="next"'}),
            response(payload=[3]),
        ])
        self.assertEqual(
            gh.get_paginated("/repos/rozkalnsandris/ops-workflows/issues", max_pages=3, max_items=10),
            [1, 2, 3],
        )
        self.assertEqual(sender.calls[1][1], next_url)
        gh, _, _, _ = client([
            response(payload=[1], headers={"Link": '<https://evil.example/page2>; rel="next"'})
        ])
        with self.assertRaises(RedirectError):
            gh.get_paginated("/repos/rozkalnsandris/ops-workflows/issues")
        same = "https://api.github.com/repos/rozkalnsandris/ops-workflows/issues"
        gh, _, _, _ = client([response(payload=[1], headers={"Link": f'<{same}>; rel="next"'})])
        with self.assertRaises(PaginationError):
            gh.get_paginated(same, max_pages=3, max_items=10)

    def test_pagination_item_limit_is_enforced(self):
        page2 = "https://api.github.com/repos/rozkalnsandris/ops-workflows/issues?page=2"
        gh, _, _, _ = client([
            response(payload=[1, 2], headers={"Link": f'<{page2}>; rel="next"'}),
            response(payload=[3, 4]),
        ])
        with self.assertRaises(PaginationError):
            gh.get_paginated("/repos/rozkalnsandris/ops-workflows/issues", max_pages=2, max_items=3)

    def test_missing_date_malformed_json_and_oversize_fail_closed(self):
        gh, _, _, _ = client([HTTPResponse(200, {}, b"{}")])
        with self.assertRaises(ResponseError):
            gh.get_json("/meta")
        gh, _, _, _ = client([response(payload=b"{not json")])
        with self.assertRaises(ResponseError):
            gh.get_json("/meta")
        huge = b'["' + (b"x" * (2 * 1024 * 1024)) + b'"]'
        gh, _, _, _ = client([response(payload=huge)])
        with self.assertRaises(ResponseError):
            gh.get_json("/meta")

    def test_live_auth_read_binds_stable_repo_and_real_p1_protocol(self):
        fixture = ROOT / "tests" / "fixtures" / "deploy_executor" / "live_auth_valid.json"
        issue = json.loads(fixture.read_text(encoding="utf-8"))
        issue["number"] = 7
        issue["created_at"] = "2026-08-27T21:29:30Z"
        issue["repository_url"] = f"https://api.github.com/repos/{AUTHORIZATION_REPOSITORY}"
        gh, _, _, _ = client([
            response(payload={"id": AUTHORIZATION_REPOSITORY_ID, "full_name": AUTHORIZATION_REPOSITORY}),
            response(payload=issue),
        ])
        accepted = gh.read_live_auth(
            7, governance_ok=True, approved_operator_app_ids=frozenset({1144995})
        )
        self.assertEqual(accepted.repository_id, AUTHORIZATION_REPOSITORY_ID)
        self.assertEqual(accepted.issue_number, 7)
        self.assertEqual(accepted.target_alias, "hermes-tech-production")
        gh, _, _, _ = client([
            response(payload={"id": AUTHORIZATION_REPOSITORY_ID + 1, "full_name": AUTHORIZATION_REPOSITORY})
        ])
        with self.assertRaises(IdentityError):
            gh.read_live_auth(7, governance_ok=True)

    def test_issue_repository_url_mismatch_rejected_before_protocol(self):
        issue = {"id": 1, "number": 7, "repository_url": "https://api.github.com/repos/other/repo"}
        gh, _, _, _ = client([
            response(payload={"id": AUTHORIZATION_REPOSITORY_ID, "full_name": AUTHORIZATION_REPOSITORY}),
            response(payload=issue),
        ])
        with self.assertRaises(IdentityError):
            gh.read_live_auth(7, governance_ok=True)

    def test_result_writer_is_deliberately_disabled(self):
        with self.assertRaises(ResultReportingDisabled):
            DisabledResultWriter().write_result({"status": "ok"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
