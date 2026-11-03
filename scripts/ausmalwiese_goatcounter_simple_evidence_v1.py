#!/usr/bin/env python3
"""Offline-only sanitized evidence assembler for GoatCounter SIMPLE (#1354).

All inputs are injected by a FUTURE separately authorized trusted reader.
This module has no host/Cloudflare/database/network I/O and performs no
public hit. Status strings are not cryptographic attestations of LIVE state.
"""
from fnmatch import fnmatchcase
import re

from ausmalwiese_goatcounter_simple_readiness_v1 import (
    HOSTS, LISTENER, VHOST, PROPOSED_COLLECT, evaluate,
)
from ausmalwiese_goatcounter_simple_route_v1 import (
    RouteError, prepare as prepare_count_route,
)

def _shape(value, fields):
    return type(value) is dict and set(value) == set(fields)

def _stop(code):
    return code, None

def _worker_route_matches(pattern):
    """Conservative tiny supported route subset. None means unknown -> STOP."""
    if (type(pattern) is not str or not 1 <= len(pattern) <= 255
            or pattern != pattern.lower()
            or re.fullmatch(r"(?:https?://)?[a-z0-9.*-]+(?:/[a-z0-9_.*~-]*)?", pattern) is None):
        return None
    for host in HOSTS:
        for request in (host + "/count", "http://" + host + "/count",
                        "https://" + host + "/count"):
            if fnmatchcase(request, pattern):
                return True
    return False

def produce(*, service=None, tunnel=None, worker_routes=None,
            worker_domains=None, ip=None, privacy=None):
    """Return (stable status, allowlisted summary or None).

    NEVER hand arbitrary caller-supplied data to a LIVE gate. A trusted future
    wrapper must independently verify provenance and owner permissions.
    """
    try:
        if any(x is None for x in
               (service, tunnel, worker_routes, worker_domains, ip, privacy)):
            return _stop("STOP_UNVERIFIED")
        if not _shape(service, (
            "source", "version", "state", "listener", "vhost",
            "collect", "collect_provenance")):
            return _stop("STOP_SERVICE")
        if service["source"] != "authorized_sanitized_host_readback":
            return _stop("STOP_UNVERIFIED")
        if (service["version"] != "v2.7.0"
                or service["state"] != "active"
                or service["listener"] != LISTENER
                or service["vhost"] != VHOST):
            return _stop("STOP_SERVICE")
        if service["collect_provenance"] != "separately_authorized_sanitized_readback":
            return _stop("STOP_UNVERIFIED")
        if type(service["collect"]) is not int or service["collect"] != PROPOSED_COLLECT:
            return _stop("STOP_COLLECT")

        if not _shape(tunnel, (
            "source", "tunnel_name", "config_src", "version",
            "owned_hosts_verified", "config")):
            return _stop("STOP_TUNNEL")
        if tunnel["source"] != "authorized_cloudflare_tunnel_read":
            return _stop("STOP_UNVERIFIED")
        if (tunnel["tunnel_name"] != "rpi5-tunnel"
                or tunnel["config_src"] != "cloudflare"
                or type(tunnel["version"]) is not int or tunnel["version"] < 0
                or tunnel["owned_hosts_verified"] is not True):
            return _stop("STOP_TUNNEL")
        # Existing source validator rejects inherited origin settings,
        # ambiguous wildcard routes, conflicts and partial /count states.
        # Its deep-copied desired config is discarded without serialization.
        try:
            _, absent = prepare_count_route(tunnel["config"])
        except RouteError:
            return _stop("STOP_ROUTE")
        if absent is not True:
            return _stop("STOP_ROUTE")

        if not _shape(worker_routes, ("source", "complete", "routes")):
            return _stop("STOP_WORKER")
        if worker_routes["source"] != "authorized_cloudflare_worker_routes_read":
            return _stop("STOP_UNVERIFIED")
        if worker_routes["complete"] is not True or type(worker_routes["routes"]) is not list:
            return _stop("STOP_WORKER")
        for route in worker_routes["routes"]:
            if not _shape(route, ("pattern", "script")) or type(route["script"]) not in (str, type(None)):
                return _stop("STOP_WORKER")
            # Even an exclusion route is not proof: reject every /count match.
            if _worker_route_matches(route["pattern"]) is not False:
                return _stop("STOP_WORKER")

        if not _shape(worker_domains, ("source", "complete", "domains")):
            return _stop("STOP_WORKER")
        if worker_domains["source"] != "authorized_cloudflare_worker_domains_read":
            return _stop("STOP_UNVERIFIED")
        if worker_domains["complete"] is not True or type(worker_domains["domains"]) is not list:
            return _stop("STOP_WORKER")
        for hostname in worker_domains["domains"]:
            if (type(hostname) is not str or not 1 <= len(hostname) <= 253
                    or hostname != hostname.lower().rstrip(".")
                    or re.fullmatch(r"[a-z0-9.-]+", hostname) is None):
                return _stop("STOP_WORKER")
            if hostname in HOSTS:
                return _stop("STOP_WORKER")

        if not _shape(ip, (
            "source", "pinned_version", "peer", "host_header",
            "forwarded_headers", "remote_addr", "spoof_rejected", "proto")):
            return _stop("STOP_IP_TRUST")
        if ip["source"] != "independently_authorized_spoof_negative_proof":
            return _stop("STOP_UNVERIFIED")
        if (ip["pinned_version"] != "v2.7.0"
                or ip["peer"] != "verified_loopback_only"
                or ip["host_header"] != "verified_pinned_vhost"
                or ip["forwarded_headers"] != "trusted_proxy_overwrites_untrusted_values"
                or ip["remote_addr"] != "verified_real_client_after_v2_7_0_processing"
                or ip["spoof_rejected"] is not True
                or ip["proto"] != "verified_https"):
            return _stop("STOP_IP_TRUST")

        if not _shape(privacy, ("source", "approved_collect", "notice", "frontend")):
            return _stop("STOP_PRIVACY")
        if privacy["source"] != "separate_owner_privacy_approval":
            return _stop("STOP_UNVERIFIED")
        if (type(privacy["approved_collect"]) is not int
                or privacy["approved_collect"] != PROPOSED_COLLECT
                or privacy["notice"] != "reviewed_actual_processing_flow"
                or privacy["frontend"] != "off"):
            return _stop("STOP_PRIVACY")

        # Synthesize from known constants ONLY; never expose raw values.
        summary = {
            "schema_version": 1,
            "service": {
                "version": "v2.7.0", "state": "active",
                "listener": LISTENER, "vhost": VHOST,
                "collect": PROPOSED_COLLECT,
                "collect_provenance": "separately_authorized_sanitized_readback",
            },
            "edge": {
                "remote_tunnel": "verified_exact_config",
                "routes": {host: "absent_safe_before_app_catchall" for host in HOSTS},
                "worker_routes": "verified_no_count_interception",
                "worker_custom_domains": "verified_no_count_interception",
            },
            "ip": {
                "tunnel_peer": "verified_loopback_only",
                "host_header": "verified_pinned_vhost",
                "forwarded_headers": "trusted_proxy_overwrites_untrusted_values",
                "remote_addr": "verified_real_client_after_v2_7_0_processing",
                "spoof_test": "synthetic_spoof_rejected",
                "forwarded_proto": "verified_https",
            },
            "privacy": {
                "approved_collect": PROPOSED_COLLECT,
                "notice": "reviewed_actual_processing_flow",
                "frontend": "off",
            },
        }
        verdict = evaluate(summary)
        return (verdict, summary) if verdict == "PASS_SOURCE_ONLY" else _stop(verdict)
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError, RecursionError):
        return _stop("STOP_UNVERIFIED")
