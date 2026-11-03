#!/usr/bin/env python3
"""Pure, disconnected GoatCounter SIMPLE /count evidence classifier (#1352).

Input must already be sanitized by a separately reviewed, owner-authorized
producer. This module performs no I/O, network access or protected inspection.
A PASS here is NOT permission to mutate or activate any LIVE system.
"""

HOSTS = ("ausmalwiese.de", "www.ausmalwiese.de")
VHOST = "goatcounter.ausmalwiese.invalid"
LISTENER = "127.0.0.1:9194"
# Pinned GoatCounter v2.7.0 flags: Referrer=2, Session=128.
# NOT an approved LIVE setting. Excludes location, per-hit and UA storage.
PROPOSED_COLLECT = 2 | 128

def _has_exact_keys(value, keys):
    return type(value) is dict and set(value) == set(keys)

def evaluate(evidence):
    """Return only a stable public-safe PASS/STOP code; never echo evidence."""
    if not _has_exact_keys(evidence, ("schema_version", "service", "edge", "ip", "privacy")):
        return "STOP_SCHEMA"
    if type(evidence["schema_version"]) is not int or evidence["schema_version"] != 1:
        return "STOP_SCHEMA"

    service = evidence["service"]
    if not _has_exact_keys(service, ("version", "state", "listener", "vhost", "collect", "collect_provenance")):
        return "STOP_SERVICE_METADATA"
    if (service["version"] != "v2.7.0" or service["state"] != "active"
            or service["listener"] != LISTENER or service["vhost"] != VHOST):
        return "STOP_SERVICE_METADATA"
    if service["collect_provenance"] != "separately_authorized_sanitized_readback":
        return "STOP_COLLECT_PROOF"
    if type(service["collect"]) is not int or service["collect"] != PROPOSED_COLLECT:
        return "STOP_COLLECT_FLAGS"

    edge = evidence["edge"]
    if not _has_exact_keys(edge, ("remote_tunnel", "routes", "worker_routes", "worker_custom_domains")):
        return "STOP_EDGE_METADATA"
    if edge["remote_tunnel"] != "verified_exact_config":
        return "STOP_EDGE_METADATA"
    if not _has_exact_keys(edge["routes"], HOSTS):
        return "STOP_ROUTE"
    # Before activation, only an unambiguous, ABSENT /count rule is a
    # source-preflight success; a live rule is not assumed authorized.
    if any(edge["routes"][host] != "absent_safe_before_app_catchall" for host in HOSTS):
        return "STOP_ROUTE"
    if edge["worker_routes"] != "verified_no_count_interception":
        return "STOP_WORKER"
    if edge["worker_custom_domains"] != "verified_no_count_interception":
        return "STOP_WORKER"

    ip = evidence["ip"]
    if not _has_exact_keys(ip, (
        "tunnel_peer", "host_header", "forwarded_headers", "remote_addr",
        "spoof_test", "forwarded_proto")):
        return "STOP_IP_TRUST"
    if ip["tunnel_peer"] != "verified_loopback_only" or ip["host_header"] != "verified_pinned_vhost":
        return "STOP_IP_TRUST"
    if (ip["forwarded_headers"] != "trusted_proxy_overwrites_untrusted_values"
            or ip["remote_addr"] != "verified_real_client_after_v2_7_0_processing"
            or ip["spoof_test"] != "synthetic_spoof_rejected"
            or ip["forwarded_proto"] != "verified_https"):
        return "STOP_IP_TRUST"

    privacy = evidence["privacy"]
    if not _has_exact_keys(privacy, ("approved_collect", "notice", "frontend")):
        return "STOP_PRIVACY"
    if (type(privacy["approved_collect"]) is not int
            or privacy["approved_collect"] != PROPOSED_COLLECT
            or privacy["notice"] != "reviewed_actual_processing_flow"
            or privacy["frontend"] != "off"):
        return "STOP_PRIVACY"
    return "PASS_SOURCE_ONLY"
