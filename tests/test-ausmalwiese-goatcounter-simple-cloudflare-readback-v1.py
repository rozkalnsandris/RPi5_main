#!/usr/bin/env python3
"""GoatCounter SIMPLE injected Cloudflare readback and guarded GET tests (#1358)."""
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ausmalwiese_goatcounter_simple_cloudflare_readback_v1 as readback
import ausmalwiese_goatcounter_simple_cloudflare_operator_v1 as operator

ACCOUNT, ZONE = "a" * 32, "b" * 32
TUNNEL = "11111111-1111-4111-8111-111111111111"
BASE = "/accounts/" + ACCOUNT
ZONE_PATH = "/zones/" + ZONE
LIST = BASE + "/cfd_tunnel?name=rpi5-tunnel&is_deleted=false&per_page=100"
CONFIG = BASE + "/cfd_tunnel/" + TUNNEL + "/configurations"
ROUTES = ZONE_PATH + "/workers/routes"
APEX = BASE + "/workers/domains?hostname=ausmalwiese.de"
WWW = BASE + "/workers/domains?hostname=www.ausmalwiese.de"


def response(result, info=None):
    obj = {"success": True, "errors": [], "result": result}
    if info is not None:
        obj["result_info"] = info
    return obj


def page(count=0, total=None, pages=1):
    return {"page": 1, "per_page": 20, "count": count,
            "total_count": count if total is None else total,
            "total_pages": pages}


def domain(name, zone=ZONE):
    return {"id": "c" * 32, "hostname": name, "zone_id": zone,
            "zone_name": "ausmalwiese.de", "enabled": True,
            "previews_enabled": False, "service": "private-canary"}


def fixture():
    return {
        ZONE_PATH: response({"id": ZONE, "name": "ausmalwiese.de",
                             "status": "active", "account": {"id": ACCOUNT}}),
        LIST: response([{"id": TUNNEL, "name": "rpi5-tunnel",
                         "config_src": "cloudflare", "deleted_at": None,
                         "account_id": ACCOUNT}],
                       {"page": 1, "total_pages": 1, "count": 1, "total_count": 1}),
        CONFIG: response({"version": 9, "config": {"ingress": [
            {"hostname": "ausmalwiese.de", "service": "http://127.0.0.1:9191"},
            {"hostname": "www.ausmalwiese.de", "service": "http://127.0.0.1:9191"},
            {"service": "http_status:404"}]}}),
        ROUTES: response([{"id": "d" * 32, "pattern": "ausmalwiese.de/api/*",
                           "script": "private-canary"}]),
        APEX: response([], page()), WWW: response([], page()),
    }


class Stub:
    def __init__(self, data):
        self.data = data
        self.requests = []
    def __call__(self, path):
        self.requests.append(path)
        if path not in self.data:
            raise RuntimeError("SECRET_CANARY from provider")
        return self.data[path]


class Tests(unittest.TestCase):
    def setUp(self):
        pin = patch.object(readback, "ACCOUNT_SHA256",
                           hashlib.sha256(ACCOUNT.encode()).hexdigest())
        pin.start()
        self.addCleanup(pin.stop)

    def check(self, data=None, account=ACCOUNT, zone=ZONE):
        caller = Stub(fixture() if data is None else data)
        value = readback.collect_once(trusted_get=caller,
                                      account_id=account, zone_id=zone)
        self.assertEqual(len(caller.requests), len(set(caller.requests)))
        self.assertLessEqual(len(caller.requests), 6)
        self.assertNotIn("private-canary", repr(value))
        self.assertNotIn("SECRET_CANARY", repr(value))
        self.assertNotIn(ACCOUNT, repr(value))
        self.assertNotIn(ZONE, repr(value))
        return value, caller

    def bad(self, data, status):
        val, _ = self.check(data)
        self.assertEqual(val, (status, None))

    def test_exact_gets_and_no_sensitive_output(self):
        val, stub = self.check()
        self.assertEqual(stub.requests,
                         [ZONE_PATH, LIST, CONFIG, ROUTES, APEX, WWW])
        self.assertEqual(val[0], "PASS_EDGE_SOURCE_ONLY")
        self.assertEqual(val[1]["worker_custom_domains"],
                         "verified_no_count_interception")
        self.assertEqual(val[1]["worker_routes"],
                         "verified_no_count_interception")

    def test_wrong_identity_stops_before_get(self):
        for acc, zone in ((None, ZONE), ("c" * 32, ZONE),
                          (ACCOUNT, "wrong"), (ACCOUNT, False)):
            with self.subTest(account=acc, zone=zone):
                val, stub = self.check(account=acc, zone=zone)
                self.assertEqual(val, ("STOP_IDENTITY", None))
                self.assertEqual(stub.requests, [])

    def test_tunnel_guards(self):
        data = fixture()
        data[LIST]["result"][0]["config_src"] = "local"
        self.bad(data, "STOP_TUNNEL")
        data = fixture()
        data[CONFIG]["result"]["config"]["originRequest"] = {"tls": "canary"}
        self.bad(data, "STOP_ROUTE")
        data = fixture()
        data[CONFIG]["result"]["config"]["ingress"].insert(0, {
            "hostname": "*.ausmalwiese.de", "service": "http://127.0.0.1:9000"})
        self.bad(data, "STOP_ROUTE")

    def test_worker_route_ambiguous_and_scriptless(self):
        for pattern in ("ausmalwiese.de/count", "ausmalwiese.de/count*",
                        "www.ausmalwiese.de/*", "*",
                        "*.ausmalwiese.de/count", "ausmalwiese.de/COUNT",
                        "ausmalwiese.de/count?x=1", "ausmalwiese.de/*/count"):
            data = fixture()
            data[ROUTES]["result"] = [{"id": "d" * 32,
                                       "pattern": pattern, "script": None}]
            with self.subTest(pattern=pattern):
                self.bad(data, "STOP_WORKER")
        data = fixture()
        data[ROUTES]["result_info"] = {"page": 1, "total_pages": 2}
        self.bad(data, "STOP_WORKER_PAGINATION")

    def test_domain_exact_hostname_filters(self):
        for key, name in ((APEX, "ausmalwiese.de"),
                          (WWW, "www.ausmalwiese.de")):
            data = fixture()
            data[key] = response([domain(name)], page(1))
            self.bad(data, "STOP_DOMAIN_INTERCEPTION")
        data = fixture()
        data[APEX] = response([domain("other.example")], page(1))
        self.bad(data, "STOP_DOMAIN_FILTER")
        data = fixture()
        data[WWW] = response([domain("www.ausmalwiese.de", "c" * 32)], page(1))
        self.bad(data, "STOP_DOMAIN_ZONE")

    def test_no_guessed_pagination_or_false_completeness(self):
        for change in ("missing", "multi", "total", "count", "bad-page"):
            data = fixture()
            if change == "missing":
                del data[APEX]["result_info"]
            elif change == "multi":
                data[APEX]["result_info"]["total_pages"] = 2
            elif change == "total":
                data[APEX]["result_info"]["total_count"] = 2000
            elif change == "count":
                data[APEX]["result_info"]["count"] = 1
            elif change == "bad-page":
                data[APEX]["result_info"]["page"] = 2
            with self.subTest(change=change):
                self.bad(data, "STOP_DOMAIN_PAGINATION")
        data = fixture()
        del data[WWW]
        val, stub = self.check(data)
        self.assertEqual(val, ("STOP_TRANSPORT", None))
        self.assertEqual(stub.requests.count(WWW), 1)

    def test_guarded_operator_cannot_execute_from_repo_checkout(self):
        # A source checkout does not match an exact SHA-versioned release path;
        # fail closed before any GET, regardless of caller-supplied identity.
        class Client:
            def __init__(self): self.calls = []
            def _request(self, method, path):
                self.calls.append((method, path))
                return fixture()[path]
        fake = Client()
        val = operator.run_guarded(client=fake, account_id=ACCOUNT,
                                   zone_id=ZONE, expected_source_sha="f" * 40)
        self.assertEqual(val, ("STOP_RELEASE", None))
        self.assertEqual(fake.calls, [])

    def test_getonly_transport_rejects_every_unapproved_path(self):
        class Client:
            def __init__(self): self.calls = []
            def _request(self, method, path):
                self.calls.append((method, path))
                return fixture()[path]
        with patch.object(operator, "CloudflareClient", Client):
            fake = Client()
            bounded = operator.GETOnly(fake, ACCOUNT, ZONE)
            for path in ("/user/tokens/verify", BASE + "/workers/scripts",
                         "/zones/" + ZONE + "/dns_records",
                         BASE + "/workers/domains?page=1&per_page=20",
                         BASE + "/cfd_tunnel/invalid/configurations"):
                with self.subTest(path=path):
                    with self.assertRaises(operator.Blocked):
                        bounded(path)
            self.assertEqual(fake.calls, [])
            self.assertEqual(bounded(ZONE_PATH), fixture()[ZONE_PATH])
            self.assertEqual(fake.calls, [("GET", ZONE_PATH)])
            with self.assertRaises(operator.Blocked):
                bounded(ZONE_PATH)
            self.assertEqual(len(fake.calls), 1)

    def test_synthetic_operator_end_to_end_get_only(self):
        class Client:
            def __init__(self): self.calls = []
            def _request(self, method, path):
                self.calls.append((method, path))
                return fixture()[path]
        with patch.object(operator, "CloudflareClient", Client), \
             patch.object(operator, "verified_release", return_value=None):
            fake = Client()
            val = operator.run_guarded(client=fake, account_id=ACCOUNT,
                                       zone_id=ZONE, expected_source_sha="f" * 40)
            # Only in this mock-proven synthetic test can GET be exercised.
            self.assertEqual(val[0], "PASS_EDGE_SOURCE_ONLY")
            self.assertEqual([x[1] for x in fake.calls],
                             [ZONE_PATH, LIST, CONFIG, ROUTES, APEX, WWW])
            self.assertEqual({x[0] for x in fake.calls}, {"GET"})

if __name__ == "__main__":
    unittest.main()
