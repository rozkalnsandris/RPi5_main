#!/usr/bin/env python3
"""Source-only #1211 adapter for the protected Stats Worker transport.

This module has no CLI, credential reader, HTTP client or installer. A future
root-owned launcher may inject only the already reviewed CloudflareTransport
from ausmalwiese_stats_worker_runtime_v1 after exact installed-release checks.
"""
from __future__ import annotations

import re

TARGET_ZONE = "ausmalwiese.de"
OTHER_ZONE = "rozkalns.net"
CODE_SHA = "47f7490918d25e8f1dcc683cebe3c4d3d9a75230f33ae5a1d26cbd6bd3ec1173"
PRE_CONFIRM = "OWNER-AUTHORIZED-STATS-ZONE-BINDING-PREFLIGHT"
APPLY_CONFIRM = "OWNER-AUTHORIZED-STATS-ZONE-BINDING-APPLY"
ID32 = re.compile(r"[0-9a-f]{32}\\Z")


class Stop(Exception):
    """Fixed public-safe failure category only."""


def need(condition, code):
    if not condition:
        raise Stop(code)


class TrustedZoneBindingAdapter:
    """Narrow bridge to one already-authenticated reviewed transport instance."""

    def __init__(self, transport):
        zones = getattr(transport, "zones", None)
        need(
            type(zones) is dict
            and set(zones) == {TARGET_ZONE, OTHER_ZONE}
            and all(type(value) is str and ID32.fullmatch(value) for value in zones.values())
            and len(set(zones.values())) == 2,
            "ZONE_ALLOWLIST_INVALID",
        )
        need(
            getattr(transport, "allow_deploy_existing", None) is False
            and getattr(transport, "candidate_code_sha256", None) == CODE_SHA,
            "TRANSPORT_MODE_INVALID",
        )
        need(
            getattr(transport, "uploads", None) == 0
            and getattr(transport, "deploys", None) == 0,
            "WRITE_BUDGET_NOT_FRESH",
        )
        self._transport = transport
        self._zones = dict(zones)

    def _stable_transport(self):
        need(
            getattr(self._transport, "zones", None) == self._zones,
            "ZONE_ALLOWLIST_DRIFT",
        )
        uploads = getattr(self._transport, "uploads", None)
        deploys = getattr(self._transport, "deploys", None)
        need(
            type(uploads) is int
            and type(deploys) is int
            and 0 <= deploys <= uploads <= 1,
            "WRITE_BUDGET_DRIFT",
        )

    def verified_zone_id(self, name):
        need(name == TARGET_ZONE, "ZONE_NAME_NOT_ALLOWED")
        self._stable_transport()
        path = (
            "/client/v4/zones?name=ausmalwiese.de&status=active"
            "&match=all&page=1&per_page=2"
        )
        try:
            result = self._transport._get(path)
        except Exception:
            raise Stop("PROVIDER_ZONE_LOOKUP_STOP") from None
        need(type(result) is list and len(result) == 1, "ZONE_LOOKUP_CARDINALITY")
        item = result[0]
        need(
            type(item) is dict
            and type(item.get("id")) is str
            and ID32.fullmatch(item["id"]) is not None
            and item.get("name") == TARGET_ZONE
            and item.get("status") == "active",
            "ZONE_LOOKUP_IDENTITY",
        )
        need(item["id"] == self._zones[TARGET_ZONE], "ZONE_ALLOWLIST_MISMATCH")
        return item["id"]

    def read_snapshot(self, **kwargs):
        self._stable_transport()
        try:
            return self._transport.read_snapshot(**kwargs)
        except Exception:
            raise Stop("PROVIDER_SNAPSHOT_STOP") from None

    def upload_version_once(self, **kwargs):
        self._stable_transport()
        need(
            self._transport.uploads == 0 and self._transport.deploys == 0,
            "UPLOAD_BUDGET_NOT_FRESH",
        )
        try:
            return self._transport.upload_version_once(**kwargs)
        except Exception:
            raise Stop("UPLOAD_OUTCOME_UNKNOWN_STOP") from None

    def deploy_version_once(self, **kwargs):
        self._stable_transport()
        need(
            self._transport.uploads == 1 and self._transport.deploys == 0,
            "DEPLOY_BUDGET_NOT_READY",
        )
        try:
            return self._transport.deploy_version_once(**kwargs)
        except Exception:
            raise Stop("DEPLOY_OUTCOME_UNKNOWN_STOP") from None


def preflight(protocol, core, transport, source, confirm):
    need(confirm == PRE_CONFIRM, "PREFLIGHT_CONFIRMATION_INVALID")
    return protocol.preflight(core, TrustedZoneBindingAdapter(transport), source)


def apply_once(protocol, core, transport, source, approval, confirm):
    need(confirm == APPLY_CONFIRM, "APPLY_CONFIRMATION_INVALID")
    return protocol.apply_once(
        core, TrustedZoneBindingAdapter(transport), source, approval
    )
