#!/usr/bin/env python3
"""Source-only bounded Cloudflare legacy 301 write path for #1114.

No CLI, credential reader, installation, owner-auth issuer, or LIVE invocation
is provided. A future separately reviewed installed caller must supply an exact
zone ID, an in-memory Dynamic URL Redirects Write credential, an owner-bound
baseline digest, and explicit LIVE authority.
"""
from __future__ import annotations

import copy
import json
import re
import urllib.request
from typing import Any

import ausmalwiese_redirect_get_adapter as get_adapter
import ausmalwiese_redirect_inventory as inventory

ZONE_NAME = "rozkalns.net"
LEGACY_HOST = "coloring.rozkalns.net"
PHASE = "http_request_dynamic_redirect"
MATCH_EXPRESSION = 'http.host eq "coloring.rozkalns.net"'
TARGET_EXPRESSION = 'concat("https://ausmalwiese.de", http.request.uri.path)'
RULE_REF = "ausmalwiese_legacy_301"
RULE_DESCRIPTION = "Ausmalwiese legacy hostname permanent redirect"
RULESET_NAME = "Ausmalwiese legacy redirect rules"
API_ORIGIN = get_adapter.API_ORIGIN
ID_RE = re.compile(r"^[0-9a-f]{32}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_WRITE_BODY_BYTES = 16384


class WriteBlocked(Exception):
    """Stable non-sensitive failure code only."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise WriteBlocked(code)


def desired_rule() -> dict[str, Any]:
    return {
        "ref": RULE_REF,
        "description": RULE_DESCRIPTION,
        "expression": MATCH_EXPRESSION,
        "action": "redirect",
        "action_parameters": {
            "from_value": {
                "target_url": {"expression": TARGET_EXPRESSION},
                "status_code": 301,
                "preserve_query_string": True,
            }
        },
        "enabled": True,
    }


def create_ruleset_body() -> dict[str, Any]:
    return {
        "name": RULESET_NAME,
        "kind": "zone",
        "phase": PHASE,
        "rules": [desired_rule()],
    }


def _canonical(value: Any) -> bytes:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError):
        raise WriteBlocked("INVALID_JSON_SHAPE") from None
    need(0 < len(raw) <= MAX_WRITE_BODY_BYTES, "WRITE_BODY_SIZE")
    return raw


def _stable_rule(rule: Any) -> dict[str, Any]:
    need(type(rule) is dict, "RULE_SHAPE")
    value = copy.deepcopy(rule)
    value.pop("version", None)
    value.pop("last_updated", None)
    return value


def _desired_semantics(rule: Any) -> bool:
    if type(rule) is not dict:
        return False
    return (
        rule.get("ref") == RULE_REF
        and rule.get("description") == RULE_DESCRIPTION
        and rule.get("expression") == MATCH_EXPRESSION
        and rule.get("action") == "redirect"
        and rule.get("action_parameters") == desired_rule()["action_parameters"]
        and rule.get("enabled", True) is True
    )


class _RecordingRead:
    def __init__(self, transport: Any, zone_id: str):
        self.transport = transport
        self.phase_path = (
            f"/zones/{zone_id}/rulesets/phases/{PHASE}/entrypoint"
        )
        self.phase_status: int | None = None
        self.phase_payload: dict[str, Any] | None = None

    def __call__(self, method: str, path: str) -> tuple[int, dict[str, Any]]:
        status, payload = self.transport.read(method, path)
        need(type(status) is int and type(payload) is dict, "READ_RESULT_SHAPE")
        if path == self.phase_path:
            self.phase_status = status
            self.phase_payload = copy.deepcopy(payload)
        return status, payload


def _entrypoint(
    record: _RecordingRead, snapshot: dict[str, Any]
) -> dict[str, Any] | None:
    if snapshot["entrypoint"] == "absent":
        need(record.phase_status == 404, "ENTRYPOINT_ABSENCE_DRIFT")
        return None
    need(
        record.phase_status == 200
        and type(record.phase_payload) is dict
        and record.phase_payload.get("success") is True
        and type(record.phase_payload.get("result")) is dict,
        "ENTRYPOINT_CAPTURE_MISSING",
    )
    entry = record.phase_payload["result"]
    need(
        entry.get("kind") == "zone"
        and entry.get("phase") == PHASE
        and type(entry.get("id")) is str
        and ID_RE.fullmatch(entry["id"]) is not None
        and type(entry.get("rules")) is list,
        "ENTRYPOINT_SHAPE",
    )
    return entry


def _analyze(
    entry: dict[str, Any] | None, snapshot: dict[str, Any]
) -> dict[str, Any]:
    need(
        snapshot.get("zone_name") == ZONE_NAME
        and snapshot.get("phase") == PHASE
        and snapshot.get("safe_to_apply") is False
        and snapshot.get("account_level_checked") is False
        and type(snapshot.get("baseline_sha256")) is str
        and SHA256_RE.fullmatch(snapshot["baseline_sha256"]) is not None,
        "SNAPSHOT_SHAPE",
    )
    need(
        snapshot.get("active_ambiguous_positions") == [],
        "AMBIGUOUS_ACTIVE_RULE",
    )
    need(
        snapshot.get("disabled_scope_unknown_count") == 0,
        "AMBIGUOUS_DISABLED_RULE",
    )
    if entry is None:
        need(
            snapshot.get("active_exact_legacy_positions") == [],
            "LEGACY_STATE_DRIFT",
        )
        return {
            "operation": "CREATE_RULESET",
            "ruleset_id": None,
            "rule_id": None,
            "unrelated": [],
        }

    legacy: list[dict[str, Any]] = []
    unrelated: list[dict[str, Any]] = []
    for rule in entry["rules"]:
        need(type(rule) is dict, "RULE_SHAPE")
        # Reuse the existing #996 anchored-host classifier rather than creating
        # a second redirect-scope parser.
        if inventory._scope(rule) == "legacy_host":
            legacy.append(rule)
        else:
            unrelated.append(_stable_rule(rule))
    need(len(legacy) <= 1, "DUPLICATE_LEGACY_RULE")
    if legacy:
        rule = legacy[0]
        rule_id = rule.get("id")
        need(
            type(rule_id) is str and ID_RE.fullmatch(rule_id) is not None,
            "LEGACY_RULE_ID",
        )
        return {
            "operation": "NOOP" if _desired_semantics(rule) else "UPDATE_RULE",
            "ruleset_id": entry["id"],
            "rule_id": rule_id,
            "unrelated": unrelated,
        }
    return {
        "operation": "ADD_RULE",
        "ruleset_id": entry["id"],
        "rule_id": None,
        "unrelated": unrelated,
    }


def _snapshot(
    transport: Any, zone_id: str
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    need(
        type(zone_id) is str and ID_RE.fullmatch(zone_id) is not None,
        "ZONE_ID",
    )
    recorder = _RecordingRead(transport, zone_id)
    try:
        snapshot = inventory.inspect_redirect_inventory(recorder, zone_id)
    except inventory.InventoryBlocked as exc:
        raise WriteBlocked("INVENTORY_" + str(exc).upper()) from None
    entry = _entrypoint(recorder, snapshot)
    analysis = _analyze(entry, snapshot)
    return snapshot, entry, analysis


def preflight(transport: Any, zone_id: str) -> dict[str, Any]:
    snapshot, _entry, analysis = _snapshot(transport, zone_id)
    return {
        "schema": "rozkalns.rpi5-main.redirect-write-preflight.v1",
        "zone_name": ZONE_NAME,
        "phase": PHASE,
        "legacy_hostname": LEGACY_HOST,
        "baseline_sha256": snapshot["baseline_sha256"],
        "operation": analysis["operation"],
        "mutation_required": analysis["operation"] != "NOOP",
        "safe_to_apply": False,
    }


def _write_plan(
    zone_id: str, analysis: dict[str, Any]
) -> tuple[str, str, dict[str, Any]]:
    operation = analysis["operation"]
    if operation == "CREATE_RULESET":
        return "POST", f"/zones/{zone_id}/rulesets", create_ruleset_body()
    if operation == "ADD_RULE":
        ruleset_id = analysis["ruleset_id"]
        need(
            type(ruleset_id) is str
            and ID_RE.fullmatch(ruleset_id) is not None,
            "RULESET_ID",
        )
        return (
            "POST",
            f"/zones/{zone_id}/rulesets/{ruleset_id}/rules",
            desired_rule(),
        )
    if operation == "UPDATE_RULE":
        ruleset_id = analysis["ruleset_id"]
        rule_id = analysis["rule_id"]
        need(
            type(ruleset_id) is str
            and ID_RE.fullmatch(ruleset_id) is not None
            and type(rule_id) is str
            and ID_RE.fullmatch(rule_id) is not None,
            "RULE_IDS",
        )
        return (
            "PATCH",
            f"/zones/{zone_id}/rulesets/{ruleset_id}/rules/{rule_id}",
            desired_rule(),
        )
    raise WriteBlocked("NO_MUTATION_PLAN")


def _postverify(
    operation: str,
    before_snapshot: dict[str, Any],
    before_entry: dict[str, Any] | None,
    before_analysis: dict[str, Any],
    after_snapshot: dict[str, Any],
    after_entry: dict[str, Any] | None,
    after_analysis: dict[str, Any],
) -> None:
    need(after_entry is not None, "POST_ENTRYPOINT_ABSENT")
    need(
        after_analysis["operation"] == "NOOP",
        "POST_DESIRED_RULE_UNPROVEN",
    )
    need(
        after_snapshot["active_ambiguous_positions"] == [],
        "POST_AMBIGUOUS_RULE",
    )
    need(
        after_analysis["unrelated"] == before_analysis["unrelated"],
        "POST_UNRELATED_RULE_DRIFT",
    )
    if operation == "NOOP":
        need(
            after_snapshot["baseline_sha256"]
            == before_snapshot["baseline_sha256"],
            "NOOP_BASELINE_DRIFT",
        )
        return
    need(
        after_snapshot["baseline_sha256"]
        != before_snapshot["baseline_sha256"],
        "POST_BASELINE_UNCHANGED",
    )
    if before_entry is not None:
        need(
            after_entry["id"] == before_entry["id"],
            "POST_RULESET_ID_DRIFT",
        )
    if operation == "UPDATE_RULE":
        need(
            after_analysis["rule_id"] == before_analysis["rule_id"],
            "POST_RULE_ID_DRIFT",
        )


def run_once(
    transport: Any,
    zone_id: str,
    expected_baseline_sha256: str,
) -> dict[str, Any]:
    need(
        type(expected_baseline_sha256) is str
        and SHA256_RE.fullmatch(expected_baseline_sha256) is not None,
        "EXPECTED_BASELINE",
    )
    before_snapshot, before_entry, before_analysis = _snapshot(
        transport, zone_id
    )
    need(
        before_snapshot["baseline_sha256"] == expected_baseline_sha256,
        "BASELINE_DRIFT",
    )
    operation = before_analysis["operation"]
    if operation != "NOOP":
        method, path, payload = _write_plan(zone_id, before_analysis)
        try:
            transport.write_once(method, path, payload)
        except WriteBlocked:
            raise
        except Exception:
            raise WriteBlocked("WRITE_OUTCOME_UNKNOWN_STOP") from None

    after_snapshot, after_entry, after_analysis = _snapshot(transport, zone_id)
    _postverify(
        operation,
        before_snapshot,
        before_entry,
        before_analysis,
        after_snapshot,
        after_entry,
        after_analysis,
    )
    return {
        "schema": "rozkalns.rpi5-main.redirect-write-result.v1",
        "status": "PASS",
        "operation": operation,
        "mutation_started": operation != "NOOP",
        "pre_baseline_sha256": before_snapshot["baseline_sha256"],
        "post_baseline_sha256": after_snapshot["baseline_sha256"],
    }


class FixedZoneRedirectWriteTransport:
    """In-memory credential transport with fixed GETs and one exact write.

    This source has no CLI or credential source. A future installed caller must
    expose only preflight/run_once under separate owner LIVE authority.
    """

    def __init__(
        self, zone_id: str, in_memory_write_token: str, *, opener=None
    ):
        need(
            type(zone_id) is str and ID_RE.fullmatch(zone_id) is not None,
            "ZONE_ID",
        )
        try:
            self._get = get_adapter.FixedZoneGetAdapter(
                zone_id, in_memory_write_token, opener=opener
            )
        except Exception:
            raise WriteBlocked("TRANSPORT_INIT") from None
        self._zone_id = zone_id
        self._token = in_memory_write_token
        self._opener = self._get._opener
        self._writes = 0
        self._phase_seen = False
        self._phase_absent = False
        self._entrypoint_id: str | None = None
        self._legacy_rule_ids: list[str] = []

    def read(
        self, method: str, path: str
    ) -> tuple[int, dict[str, Any]]:
        try:
            status, payload = self._get(method, path)
        except Exception:
            raise WriteBlocked("READ_FAILED") from None
        phase_path = (
            f"/zones/{self._zone_id}/rulesets/phases/{PHASE}/entrypoint"
        )
        if path == phase_path:
            self._phase_seen = True
            if status == 404:
                self._phase_absent = True
                self._entrypoint_id = None
                self._legacy_rule_ids = []
            elif status == 200:
                result = payload.get("result")
                need(type(result) is dict, "READ_PHASE_SHAPE")
                ruleset_id = result.get("id")
                rules = result.get("rules")
                need(
                    type(ruleset_id) is str
                    and ID_RE.fullmatch(ruleset_id) is not None
                    and type(rules) is list,
                    "READ_PHASE_SHAPE",
                )
                legacy_ids: list[str] = []
                for rule in rules:
                    need(type(rule) is dict, "READ_RULE_SHAPE")
                    if inventory._scope(rule) == "legacy_host":
                        rule_id = rule.get("id")
                        need(
                            type(rule_id) is str
                            and ID_RE.fullmatch(rule_id) is not None,
                            "READ_RULE_ID",
                        )
                        legacy_ids.append(rule_id)
                self._phase_absent = False
                self._entrypoint_id = ruleset_id
                self._legacy_rule_ids = legacy_ids
            else:
                raise WriteBlocked("READ_PHASE_STATUS")
        return status, payload

    def _validate_write(
        self, method: str, path: str, payload: Any
    ) -> None:
        prefix = f"/zones/{self._zone_id}"
        need(self._phase_seen, "WRITE_BASELINE_NOT_SEEN")
        if method == "POST" and path == prefix + "/rulesets":
            need(self._phase_absent, "WRITE_ENTRYPOINT_STATE_DRIFT")
            need(
                payload == create_ruleset_body(),
                "WRITE_BODY_DRIFT",
            )
            return
        add = re.fullmatch(
            re.escape(prefix) + r"/rulesets/([0-9a-f]{32})/rules",
            path,
        )
        if method == "POST" and add is not None:
            need(
                not self._phase_absent
                and self._entrypoint_id is not None
                and add.group(1) == self._entrypoint_id,
                "WRITE_RULESET_ID_DRIFT",
            )
            need(payload == desired_rule(), "WRITE_BODY_DRIFT")
            return
        update = re.fullmatch(
            re.escape(prefix)
            + r"/rulesets/([0-9a-f]{32})/rules/([0-9a-f]{32})",
            path,
        )
        if method == "PATCH" and update is not None:
            need(
                not self._phase_absent
                and self._entrypoint_id is not None
                and update.group(1) == self._entrypoint_id
                and len(self._legacy_rule_ids) == 1
                and update.group(2) == self._legacy_rule_ids[0],
                "WRITE_RULE_IDENTITY_DRIFT",
            )
            need(payload == desired_rule(), "WRITE_BODY_DRIFT")
            return
        raise WriteBlocked("WRITE_PATH_NOT_ALLOWED")

    def write_once(
        self, method: str, path: str, payload: Any
    ) -> None:
        need(self._writes == 0, "SECOND_WRITE_FORBIDDEN")
        self._validate_write(method, path, payload)
        body = _canonical(payload)
        expected_url = API_ORIGIN + path
        request = urllib.request.Request(
            expected_url,
            data=body,
            headers={
                "Authorization": "Bearer " + self._token,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method=method,
        )
        # Consume the one-write budget immediately before dispatch. Any
        # exception from this point is terminal for this transport instance.
        self._writes = 1
        try:
            with self._opener.open(
                request, timeout=get_adapter.TIMEOUT_SECONDS
            ) as response:
                if (
                    response.status != 200
                    or response.geturl() != expected_url
                ):
                    raise WriteBlocked("WRITE_RESPONSE_UNEXPECTED")
                raw = response.read(get_adapter.MAX_BODY_BYTES + 1)
        except WriteBlocked:
            raise
        except Exception:
            raise WriteBlocked("WRITE_OUTCOME_UNKNOWN_STOP") from None
        need(
            len(raw) <= get_adapter.MAX_BODY_BYTES,
            "WRITE_RESPONSE_OVERSIZE",
        )
        try:
            value = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=get_adapter._json_no_duplicates,
            )
        except Exception:
            raise WriteBlocked("WRITE_RESPONSE_INVALID") from None
        need(
            type(value) is dict
            and value.get("success") is True
            and type(value.get("result")) is dict,
            "WRITE_RESPONSE_INVALID",
        )


# No __main__, argparse, env/stdin credential source, install path, or auth issuer.
