#!/usr/bin/env python3
"""Source-only, pure Cloudflare /count ingress transformer (RPi5_main #1350).

No network, credentials, privileged entrypoint, or runtime configuration access.
"""
from copy import deepcopy
from fnmatch import fnmatchcase
import re

HOSTS = ("ausmalwiese.de", "www.ausmalwiese.de")
PATH = "^/count$"
BACKEND = "http://127.0.0.1:9194"
SITE_HOST = "goatcounter.ausmalwiese.invalid"


class RouteError(ValueError):
    """Route is not safely eligible for this exact change."""


def entry(host):
    if host not in HOSTS:
        raise RouteError("UNKNOWN_HOST")
    return {"hostname": host, "path": PATH, "service": BACKEND,
            "originRequest": {"httpHostHeader": SITE_HOST}}


def prepare(config):
    """Return (copy with only two additions, changed); fail closed on ambiguity."""
    if type(config) is not dict or config.get("originRequest", {}) != {}:
        raise RouteError("GLOBAL_ORIGIN_SETTINGS_REQUIRE_REVIEW")
    rules = config.get("ingress")
    if (type(rules) is not list or len(rules) < 3
            or any(type(rule) is not dict for rule in rules)
            or rules[-1] != {"service": "http_status:404"}):
        raise RouteError("INGRESS_SHAPE_INVALID")

    # Any earlier generic or matching wildcard rule could intercept /count.
    for rule in rules[:-1]:
        hostname = rule.get("hostname")
        if (type(hostname) is not str or not hostname
                or hostname != hostname.lower().rstrip(".")):
            raise RouteError("HOST_MATCH_AMBIGUOUS")
        if hostname not in HOSTS and any(fnmatchcase(host, hostname) for host in HOSTS):
            raise RouteError("HOST_MATCH_AMBIGUOUS")

    installed = []
    for host in HOSTS:
        matches = [(i, rule) for i, rule in enumerate(rules)
                   if rule.get("hostname") == host]
        fallback = [(i, rule) for i, rule in matches if "path" not in rule]
        if len(fallback) != 1:
            raise RouteError("APP_FALLBACK_INVALID")
        service = fallback[0][1].get("service")
        m = re.fullmatch(r"http://(?:127\.0\.0\.1|localhost):([0-9]{2,5})",
                         service) if type(service) is str else None
        if not m or int(m[1]) > 65535 or int(m[1]) in (9193, 9194):
            raise RouteError("APP_FALLBACK_INVALID")
        scoped = [(i, rule) for i, rule in matches if "path" in rule]
        if scoped and (len(scoped) != 1 or scoped[0][1] != entry(host)
                       or scoped[0][0] >= fallback[0][0]):
            raise RouteError("EXISTING_PATH_CONFLICT")
        installed.append(bool(scoped))

    if any(installed) and not all(installed):
        raise RouteError("PARTIAL_ROUTE_STATE")
    desired = deepcopy(config)
    if all(installed):
        return desired, False
    updated = []
    for rule in desired["ingress"]:
        if rule.get("hostname") in HOSTS and "path" not in rule:
            updated.append(entry(rule["hostname"]))
        updated.append(rule)
    desired["ingress"] = updated
    return desired, True
