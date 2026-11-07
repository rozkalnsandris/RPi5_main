#!/usr/bin/env python3
"""Pure, disconnected GoatCounter SIMPLE /count evidence classifier (#1352/#1415).

Input must already be sanitized by a separately reviewed, owner-authorized
producer. This module performs no I/O, network access or protected inspection.
A PASS here is NOT permission to mutate or activate any LIVE system.
"""
import ipaddress

HOSTS = ("ausmalwiese.de", "www.ausmalwiese.de")
VHOST = "goatcounter.ausmalwiese.invalid"
LISTENER = "127.0.0.1:9194"
PROPOSED_COLLECT = 2 | 128


def _has_exact_keys(value, keys):
    return type(value) is dict and set(value) == set(keys)


def _trusted_client_ip(ip):
    if not _has_exact_keys(ip, (
            "tunnel_peer", "host_header", "forwarded_headers", "remote_addr",
            "spoof_test", "forwarded_proto")):
        return False
    if ip["tunnel_peer"] != "verified_loopback_only" or ip["host_header"] != "verified_pinned_vhost":
        return False
    return (
        ip["forwarded_headers"] == "trusted_proxy_overwrites_untrusted_values"
        and ip["remote_addr"] == "verified_real_client_after_v2_7_0_processing"
        and ip["spoof_test"] == "synthetic_spoof_rejected"
        and ip["forwarded_proto"] == "verified_https"
    )


def _exact_public_ip(value):
    if type(value) is not str or not value or "/" in value or "%" in value:
        return False
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    return addr.is_global and str(addr) == value


def exact_ignore_ips_valid(values):
    """Validate an in-memory exact-IP candidate without returning address data."""
    if type(values) is not list or not values:
        return False
    if len(values) != len(set(values)):
        return False
    return all(_exact_public_ip(v) for v in values)


def exact_ignore_ips_cover(observed, configured):
    """Check exact string coverage without emitting either address list."""
    if not exact_ignore_ips_valid(observed) or not exact_ignore_ips_valid(configured):
        return False
    return set(observed).issubset(set(configured))


def evaluate_household_exclusion(evidence):
    """Classify sanitized household-exclusion readiness; never echo IP values."""
    if not _has_exact_keys(evidence, ("schema_version", "ip", "egress", "mutation")):
        return "STOP_HOUSEHOLD_SCHEMA"
    if type(evidence["schema_version"]) is not int or evidence["schema_version"] != 1:
        return "STOP_HOUSEHOLD_SCHEMA"

    if not _trusted_client_ip(evidence["ip"]):
        return "STOP_IP_TRUST"

    egress = evidence["egress"]
    if not _has_exact_keys(egress, ("ipv4", "ipv6")):
        return "STOP_EGRESS"
    ipv4 = egress["ipv4"]
    ipv6 = egress["ipv6"]
    if ipv4 not in ("shared_stable_exact", "absent", "dynamic_or_unknown"):
        return "STOP_EGRESS"
    if ipv6 not in ("stable_exact_set", "absent", "rotating_or_unknown"):
        return "STOP_EGRESS"
    if ipv4 == "dynamic_or_unknown":
        return "STOP_DYNAMIC_IPV4"
    if ipv6 == "rotating_or_unknown":
        return "STOP_DYNAMIC_IPV6"
    if ipv4 == "absent" and ipv6 == "absent":
        return "STOP_NO_EGRESS"

    mutation = evidence["mutation"]
    if not _has_exact_keys(mutation, (
            "target", "field", "preserve_other_settings", "direct_db_edit")):
        return "STOP_MUTATION_CONTRACT"
    if (mutation["target"] != "goatcounter_site_settings"
            or mutation["field"] != "ignore_ips"
            or mutation["preserve_other_settings"] is not True
            or mutation["direct_db_edit"] is not False):
        return "STOP_MUTATION_CONTRACT"

    return "PASS_HOUSEHOLD_EXCLUSION_SOURCE_ONLY"


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
    if any(edge["routes"][host] != "absent_safe_before_app_catchall" for host in HOSTS):
        return "STOP_ROUTE"
    if edge["worker_routes"] != "verified_no_count_interception":
        return "STOP_WORKER"
    if edge["worker_custom_domains"] != "verified_no_count_interception":
        return "STOP_WORKER"

    if not _trusted_client_ip(evidence["ip"]):
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
