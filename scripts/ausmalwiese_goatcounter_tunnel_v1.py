#!/usr/bin/env python3
"""Exact pageview ingress preparation; execution requires separate owner authority."""
from __future__ import annotations

import argparse
from copy import deepcopy
import fnmatch
import hashlib
import json
import os
import re
import sys
import urllib.request

from cloudflare_rdc_operator import (
    ACCOUNT_ID_RE, UUID_RE, CloudflareClient, NoRedirect, OperatorError,
    load_tunnel_credentials,
)

HOSTS = ("ausmalwiese.de", "www.ausmalwiese.de")
PATH = "^/api/pageview$"
SERVICE = "http://127.0.0.1:9193"
ACCOUNT_SHA256 = "3239859bf3aeb05fe2ca1d41545615bf689801fa347de533cc2ece45ead98b34"
READ_CONFIRM = "READ_GOATCOUNTER_TUNNEL_BASELINE"
APPLY_CONFIRM = "EXPOSE_GOATCOUNTER_PAGEVIEW_AFTER_PUBLIC_GATES"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def entry(host):
    return {"hostname": host, "path": PATH, "service": SERVICE,
            "originRequest": {"httpHostHeader": host}}


def prepare(config):
    """Copy only two additions; refuse uncertain routing or inherited settings."""
    if not isinstance(config, dict) or config.get("originRequest", {}) != {}:
        raise OperatorError("GLOBAL_ORIGIN_SETTINGS_REQUIRE_REVIEW")
    rules = config.get("ingress")
    if (not isinstance(rules, list) or len(rules) < 3
            or any(not isinstance(r, dict) for r in rules)
            or rules[-1] != {"service": "http_status:404"}):
        raise OperatorError("INGRESS_SHAPE_INVALID")
    for rule in rules[:-1]:
        host = rule.get("hostname")
        if not isinstance(host, str) or not host or host != host.lower().rstrip("."):
            raise OperatorError("HOST_MATCH_AMBIGUOUS")
        if host not in HOSTS and any(fnmatch.fnmatchcase(h, host) for h in HOSTS):
            raise OperatorError("HOST_MATCH_AMBIGUOUS")
    installed = []
    for host in HOSTS:
        matching = [r for r in rules if r.get("hostname") == host]
        fallback = [r for r in matching if "path" not in r]
        if (len(fallback) != 1 or not isinstance(fallback[0].get("service"), str)
                or not re.fullmatch(r"http://(?:127\.0\.0\.1|localhost):[0-9]{2,5}", fallback[0]["service"])
                or int(fallback[0]["service"].rsplit(":", 1)[1]) not in range(1, 65536)
                or int(fallback[0]["service"].rsplit(":", 1)[1]) in {9193, 9194}
                or fallback[0]["service"] in {SERVICE, "http://127.0.0.1:9194", "http://localhost:9193", "http://localhost:9194"}):
            raise OperatorError("APP_FALLBACK_INVALID")
        paths = [r for r in matching if "path" in r]
        if paths and (paths != [entry(host)] or rules.index(paths[0]) > rules.index(fallback[0])):
            raise OperatorError("EXISTING_PATH_CONFLICT")
        installed.append(bool(paths))
    if any(installed) and not all(installed):
        raise OperatorError("PARTIAL_ROUTE_STATE")
    desired = deepcopy(config)
    if all(installed):
        return desired, False
    result = []
    for rule in desired["ingress"]:
        if rule.get("hostname") in HOSTS:
            result.append(entry(rule["hostname"]))
        result.append(rule)
    desired["ingress"] = result
    return desired, True


def read_config(client, account, tunnel_id):
    response = client._request("GET", f"/accounts/{account}/cfd_tunnel/{tunnel_id}/configurations")
    result = response.get("result")
    if (not isinstance(result, dict) or type(result.get("version")) is not int
            or result["version"] < 0 or not isinstance(result.get("config"), dict)):
        raise OperatorError("CONFIG_RESPONSE_INVALID")
    return {"tunnel_id": tunnel_id, "version": result["version"], "config": result["config"]}


def snapshot(client, account):
    if not isinstance(account, str) or not ACCOUNT_ID_RE.fullmatch(account):
        raise OperatorError("ACCOUNT_INVALID")
    response = client._request("GET", f"/accounts/{account}/cfd_tunnel?name=rpi5-tunnel&is_deleted=false&per_page=100")
    rows = response.get("result")
    info = response.get("result_info", {})
    if (not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict)
            or not isinstance(info, dict) or info.get("total_pages", 1) != 1):
        raise OperatorError("TUNNEL_IDENTITY_INVALID")
    row = rows[0]
    if (row.get("name") != "rpi5-tunnel" or row.get("config_src") != "cloudflare"
            or not isinstance(row.get("id"), str) or not UUID_RE.fullmatch(row["id"])
            or row.get("deleted_at") is not None):
        raise OperatorError("TUNNEL_IDENTITY_INVALID")
    return read_config(client, account, row["id"])


class PostDispatchError(Exception):
    """One write was attempted: do not retry or perform recovery."""


def run(client, account, *, apply=False, expected_baseline=""):
    before = snapshot(client, account)
    desired, change = prepare(before["config"])
    baseline = digest(before)
    report = {"result": "PASS", "baseline_sha256": baseline,
              "route_state": "ABSENT" if change else "PRESENT_EXACT",
              "write_attempted": False, "mutation_verified": False,
              "public_readiness_verified": False}
    if not apply:
        return report
    if not re.fullmatch(r"[0-9a-f]{64}", expected_baseline) or expected_baseline != baseline:
        raise OperatorError("BASELINE_MISMATCH")
    if not change:
        return report
    # Re-read immediately before PUT. Cloudflare has no documented conditional
    # config update: a separate single-writer window is still mandatory.
    if read_config(client, account, before["tunnel_id"]) != before:
        raise OperatorError("PREWRITE_DRIFT")
    try:
        client._request("PUT", f"/accounts/{account}/cfd_tunnel/{before['tunnel_id']}/configurations", {"config": desired})
        after = read_config(client, account, before["tunnel_id"])
        if after["config"] != desired or after["version"] <= before["version"]:
            raise OperatorError("POSTWRITE_MISMATCH")
    except Exception as exc:
        raise PostDispatchError("WRITE_OUTCOME_REQUIRES_RECONCILIATION") from exc
    report.update(route_state="PRESENT_EXACT", write_attempted=True, mutation_verified=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-read", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-baseline", default="")
    parser.add_argument("--confirm-public-exposure", default="")
    args = parser.parse_args(argv)
    if (args.confirm_read != READ_CONFIRM or os.geteuid() != 0
            or (args.apply and (args.confirm_public_exposure != APPLY_CONFIRM
                or not re.fullmatch(r"[0-9a-f]{64}", args.expected_baseline)))):
        print('{"result":"BLOCKED","reason":"EXECUTION_GATE_MISSING","write_attempted":false}')
        return 2
    try:
        account, token = load_tunnel_credentials()
        if hashlib.sha256(account.encode()).hexdigest() != ACCOUNT_SHA256:
            raise OperatorError("ACCOUNT_BINDING_MISMATCH")
        # Explicitly reject redirects and inherited proxy configuration.
        client = CloudflareClient(token, opener=urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect))
        client.verify_active_account_token(account)
        report = run(client, account, apply=args.apply, expected_baseline=args.expected_baseline)
    except PostDispatchError:
        print('{"result":"STOP_ERROR","reason":"WRITE_OUTCOME_REQUIRES_RECONCILIATION","write_attempted":true,"mutation_verified":null}')
        return 4
    except Exception:
        print('{"result":"BLOCKED","reason":"PREFLIGHT_FAILED","write_attempted":false}')
        return 3
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
