#!/usr/bin/env python3
"""Ausmalwiese household /count Cloudflare WAF operator.

Create mode is the reviewed #1420 flow. Update mode (#1427) can only extend the
one existing household rule with additive IPv6 material while preserving the
incumbent source set and exact host/path/block scope.
"""
from __future__ import annotations

import getpass
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib import error, request
import warnings

ZONE_NAME = "ausmalwiese.de"
HOSTS = ("ausmalwiese.de", "www.ausmalwiese.de")
PATH = "/count"
PHASE = "http_request_firewall_custom"
RULE_REF = "ausmalwiese-household-goatcounter-exclusion-v1"
RULE_DESCRIPTION = "Ausmalwiese: exclude owner household from GoatCounter /count"
MAX_FREE_RULES = 5
MAX_SOURCES = 8
MIN_IPV4_PREFIX = 24
MIN_IPV6_PREFIX = 48

INSTALLED = Path("/usr/local/sbin/rpi5-ausmalwiese-household-waf")
RELEASE = Path("/usr/local/libexec/rpi5-ausmalwiese-household-waf/release.json")
SECRET = Path("/etc/rpi5-secrets/cloudflare/ausmalwiese-zone-waf-writer.json")
BASE = "https://api.cloudflare.com/client/v4"
MAX_PROTECTED_DATA_BYTES = 8192
MAX_INSTALLED_OPERATOR_BYTES = 131072

CREATE_CONFIRM = "CREATE-AUSMALWIESE-HOUSEHOLD-COUNT-WAF"
UPDATE_CONFIRM = "UPDATE-AUSMALWIESE-HOUSEHOLD-COUNT-WAF"


class GateError(Exception):
    """Fail-closed fixed reasons only; never include raw addresses or provider bodies."""


def hex_id(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{32}", value) is not None


def _global_ip(ip: ipaddress._BaseAddress) -> bool:
    return bool(ip.is_global and not (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
        or ip.is_unspecified or ip.is_reserved
    ))


def normalize_source(value: str) -> str:
    """Return canonical public exact IP/CIDR or fail with a fixed code."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise GateError("invalid_household_source")
    if "%" in value:
        raise GateError("invalid_household_source")

    if "/" not in value:
        try:
            addr = ipaddress.ip_address(value)
        except ValueError:
            raise GateError("invalid_household_source") from None
        if str(addr) != value or not _global_ip(addr):
            raise GateError("invalid_household_source")
        return str(addr)

    try:
        network = ipaddress.ip_network(value, strict=True)
    except ValueError:
        raise GateError("invalid_household_source") from None
    if str(network) != value:
        raise GateError("noncanonical_household_source")
    if not _global_ip(network.network_address) or not _global_ip(network[-1]):
        raise GateError("invalid_household_source")
    if network.version == 4 and network.prefixlen < MIN_IPV4_PREFIX:
        raise GateError("overbroad_household_source")
    if network.version == 6 and network.prefixlen < MIN_IPV6_PREFIX:
        raise GateError("overbroad_household_source")
    return str(network)


def normalize_sources(values: list[str]) -> tuple[str, ...]:
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_SOURCES:
        raise GateError("household_source_count_invalid")
    normalized = tuple(normalize_source(value) for value in values)
    if len(set(normalized)) != len(normalized):
        raise GateError("duplicate_household_source")
    return tuple(sorted(normalized, key=lambda x: (
        ipaddress.ip_network(
            x if "/" in x else x + ("/32" if ":" not in x else "/128"),
            strict=False,
        ).version,
        x,
    )))


def _source_version(value: str) -> int:
    return ipaddress.ip_network(
        value if "/" in value else value + ("/32" if ":" not in value else "/128"),
        strict=False,
    ).version


def source_shape(values: tuple[str, ...]) -> dict[str, int]:
    exact_v4 = exact_v6 = cidr_v4 = cidr_v6 = 0
    for value in values:
        if "/" in value:
            net = ipaddress.ip_network(value)
            if net.version == 4:
                cidr_v4 += 1
            else:
                cidr_v6 += 1
        else:
            addr = ipaddress.ip_address(value)
            if addr.version == 4:
                exact_v4 += 1
            else:
                exact_v6 += 1
    return {
        "exact_ipv4": exact_v4,
        "exact_ipv6": exact_v6,
        "cidr_ipv4": cidr_v4,
        "cidr_ipv6": cidr_v6,
        "total": len(values),
    }


def _expression_prefix() -> str:
    hosts = " or ".join(f'http.host eq "{host}"' for host in HOSTS)
    return f'(({hosts}) and http.request.uri.path eq "{PATH}" and ip.src in {{'


def build_expression(values: tuple[str, ...]) -> str:
    if not values:
        raise GateError("household_source_count_invalid")
    return _expression_prefix() + " ".join(values) + "})"


def target_rule(values: tuple[str, ...]) -> dict:
    return {
        "ref": RULE_REF,
        "description": RULE_DESCRIPTION,
        "expression": build_expression(values),
        "action": "block",
        "enabled": True,
    }


def existing_projection(rules: list) -> list[tuple]:
    if not isinstance(rules, list):
        raise GateError("invalid_existing_rules")
    result = []
    for entry in rules:
        if not isinstance(entry, dict) or not hex_id(entry.get("id")):
            raise GateError("invalid_existing_rule_identity")
        if not isinstance(entry.get("expression"), str) or not isinstance(entry.get("action"), str):
            raise GateError("invalid_existing_rule_fields")
        result.append((
            entry["id"],
            entry.get("ref"),
            entry.get("description", ""),
            entry["action"],
            entry["expression"],
            entry.get("enabled", True),
        ))
    if len(set(item[0] for item in result)) != len(result):
        raise GateError("duplicate_existing_rule_id")
    return result


def target_sources(rule: dict) -> tuple[str, ...]:
    """Recover only an exact rule generated by this operator."""
    if not isinstance(rule, dict) or not hex_id(rule.get("id")):
        raise GateError("target_rule_identity_drift")
    if (
        rule.get("ref") != RULE_REF
        or rule.get("description") != RULE_DESCRIPTION
        or rule.get("action") != "block"
        or rule.get("enabled", True) is not True
        or not isinstance(rule.get("expression"), str)
    ):
        raise GateError("target_rule_scope_drift")

    expression = rule["expression"]
    prefix = _expression_prefix()
    suffix = "})"
    if not expression.startswith(prefix) or not expression.endswith(suffix):
        raise GateError("target_rule_expression_drift")
    inner = expression[len(prefix):-len(suffix)]
    if not inner or inner != inner.strip() or "  " in inner:
        raise GateError("target_rule_expression_drift")
    raw = tuple(inner.split(" "))
    normalized = normalize_sources(list(raw))
    if normalized != raw or build_expression(normalized) != expression:
        raise GateError("target_rule_expression_drift")
    return normalized


def _entrypoint(snapshot: dict) -> tuple[str, list, list[tuple]]:
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("phase") != PHASE
        or snapshot.get("kind") != "zone"
    ):
        raise GateError("unexpected_entrypoint")
    ruleset_id = snapshot.get("id")
    if not hex_id(ruleset_id):
        raise GateError("invalid_entrypoint_id")
    rules = snapshot.get("rules")
    before = existing_projection(rules)
    return ruleset_id, rules, before


def plan(snapshot: dict | None, zone_id: str,
         values: tuple[str, ...]) -> tuple[str, str, dict, list[tuple]]:
    """Return exactly one allowed create POST, preserving prior rules."""
    if not hex_id(zone_id):
        raise GateError("invalid_zone_id")
    values = normalize_sources(list(values))
    rule = target_rule(values)
    prefix = f"/zones/{zone_id}/rulesets"
    if snapshot is None:
        return ("create_entrypoint", prefix, {
            "name": "Zone-level custom WAF",
            "kind": "zone",
            "phase": PHASE,
            "rules": [rule],
        }, [])

    ruleset_id, _, before = _entrypoint(snapshot)
    if len(before) >= MAX_FREE_RULES:
        raise GateError("custom_rule_capacity_exhausted")
    expression = rule["expression"]
    if any(item[1] == RULE_REF or item[4] == expression for item in before):
        raise GateError("rule_already_present_or_conflict")
    return (
        "append_one_rule",
        f"{prefix}/{ruleset_id}/rules",
        rule,
        before,
    )


def verify(after: dict, before: list[tuple], values: tuple[str, ...]) -> None:
    _, rules, projection = _entrypoint(after)
    if len(projection) != len(before) + 1 or projection[:len(before)] != before:
        raise GateError("verification_preexisting_rule_drift")
    expected = target_rule(normalize_sources(list(values)))
    newest = rules[-1]
    if (
        newest.get("ref") != RULE_REF
        or newest.get("description") != RULE_DESCRIPTION
        or newest.get("expression") != expected["expression"]
        or newest.get("action") != "block"
        or newest.get("enabled", True) is not True
    ):
        raise GateError("verification_target_rule_mismatch")


def plan_update(snapshot: dict, zone_id: str, values: tuple[str, ...]) -> tuple[
        str, str, dict, list[tuple], int, tuple[str, ...]]:
    """Plan one exact PATCH that preserves incumbent sources and adds only IPv6."""
    if not hex_id(zone_id):
        raise GateError("invalid_zone_id")
    desired = normalize_sources(list(values))
    ruleset_id, rules, before = _entrypoint(snapshot)
    target_indexes = [
        index for index, rule in enumerate(rules)
        if isinstance(rule, dict) and rule.get("ref") == RULE_REF
    ]
    if len(target_indexes) != 1:
        raise GateError("target_rule_count_invalid")
    target_index = target_indexes[0]
    incumbent = target_sources(rules[target_index])

    if not any(_source_version(value) == 4 for value in incumbent):
        raise GateError("incumbent_ipv4_missing")
    if not set(incumbent).issubset(set(desired)):
        raise GateError("incumbent_source_drop_forbidden")

    additions = set(desired) - set(incumbent)
    if not additions:
        raise GateError("additive_update_required")
    if any(_source_version(value) != 6 for value in additions):
        raise GateError("update_additions_must_be_ipv6")

    rule_id = rules[target_index]["id"]
    return (
        "update_existing_target",
        f"/zones/{zone_id}/rulesets/{ruleset_id}/rules/{rule_id}",
        target_rule(desired),
        before,
        target_index,
        incumbent,
    )


def verify_update(after: dict, before: list[tuple], target_index: int,
                  values: tuple[str, ...]) -> None:
    _, rules, projection = _entrypoint(after)
    if len(projection) != len(before):
        raise GateError("verification_rule_count_drift")
    if not 0 <= target_index < len(before):
        raise GateError("verification_target_index_invalid")

    expected = target_rule(normalize_sources(list(values)))
    expected_target = (
        before[target_index][0],
        RULE_REF,
        RULE_DESCRIPTION,
        "block",
        expected["expression"],
        True,
    )
    for index, item in enumerate(projection):
        if index == target_index:
            if item != expected_target:
                raise GateError("verification_target_rule_mismatch")
        elif item != before[index]:
            raise GateError("verification_unrelated_rule_drift")
    if target_sources(rules[target_index]) != normalize_sources(list(values)):
        raise GateError("verification_target_rule_mismatch")


def owned_file(path: Path, mode: int) -> bytes:
    limit = (
        MAX_INSTALLED_OPERATOR_BYTES
        if path == INSTALLED and mode == 0o500
        else MAX_PROTECTED_DATA_BYTES
    )
    try:
        s = path.lstat()
        if (
            not stat.S_ISREG(s.st_mode)
            or s.st_uid != 0
            or s.st_gid != 0
            or stat.S_IMODE(s.st_mode) != mode
        ):
            raise GateError("protected_file_metadata_mismatch")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            s2 = os.fstat(fd)
            if (
                not stat.S_ISREG(s2.st_mode)
                or s2.st_uid != 0
                or s2.st_gid != 0
                or stat.S_IMODE(s2.st_mode) != mode
            ):
                raise GateError("protected_file_changed")
            with os.fdopen(fd, "rb", closefd=False) as f:
                data = f.read(limit + 1)
            if len(data) > limit:
                raise GateError("protected_file_too_large")
            return data
        finally:
            os.close(fd)
    except OSError:
        raise GateError("protected_file_unavailable") from None


def verified_installed_release(expected_main: str) -> None:
    if os.geteuid() != 0 or Path(__file__).resolve() != INSTALLED:
        raise GateError("installed_root_operator_required")
    if not re.fullmatch(r"[0-9a-f]{40}", expected_main):
        raise GateError("invalid_expected_main")
    try:
        release = json.loads(owned_file(RELEASE, 0o400))
    except (ValueError, TypeError):
        raise GateError("release_metadata_invalid") from None
    if (
        set(release) != {"source_sha", "operator_sha256"}
        or release["source_sha"] != expected_main
    ):
        raise GateError("release_identity_mismatch")
    if not re.fullmatch(r"[a-f0-9]{64}", release["operator_sha256"]):
        raise GateError("invalid_release_hash")
    if (
        hashlib.sha256(owned_file(INSTALLED, 0o500)).hexdigest()
        != release["operator_sha256"]
    ):
        raise GateError("operator_hash_mismatch")


def installed_credentials(expected_main: str) -> tuple[str, str]:
    verified_installed_release(expected_main)
    try:
        secret = json.loads(owned_file(SECRET, 0o600))
    except (ValueError, TypeError):
        raise GateError("secret_schema_mismatch") from None
    if set(secret) != {"zone_id", "zone_name", "api_token"}:
        raise GateError("secret_schema_mismatch")
    if not hex_id(secret["zone_id"]) or secret["zone_name"] != ZONE_NAME:
        raise GateError("zone_identity_mismatch")
    if (
        not isinstance(secret["api_token"], str)
        or not 16 <= len(secret["api_token"]) <= 512
    ):
        raise GateError("secret_invalid")
    return secret["zone_id"], secret["api_token"]


def read_household_sources() -> tuple[str, ...]:
    """Read hidden local-TTY input only; never CLI/env/stdin."""
    verified = []
    try:
        tty = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY | os.O_NOFOLLOW)
        try:
            if not os.isatty(tty):
                raise GateError("controlling_tty_required")
        finally:
            os.close(tty)
        for index in range(1, MAX_SOURCES + 1):
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                value = getpass.getpass(
                    f"Household public IP/CIDR #{index} (hidden; blank to finish): "
                )
            if value == "":
                break
            verified.append(value)
    except (EOFError, KeyboardInterrupt, OSError, getpass.GetPassWarning):
        raise GateError("secure_local_tty_input_failed") from None
    return normalize_sources(verified)


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api_call(token: str, method: str, path: str,
             payload: dict | None = None) -> tuple[int, dict]:
    pattern = (
        r"/zones/[0-9a-f]{32}"
        r"(?:/rulesets"
        r"(?:/phases/http_request_firewall_custom/entrypoint"
        r"|/[0-9a-f]{32}/rules(?:/[0-9a-f]{32})?)?"
        r")?"
    )
    if not re.fullmatch(pattern, path):
        raise GateError("unexpected_api_path")
    if method not in {"GET", "POST", "PATCH"}:
        raise GateError("unexpected_api_method")
    body = (
        json.dumps(payload, separators=(",", ":")).encode()
        if payload is not None else None
    )
    req = request.Request(BASE + path, data=body, method=method, headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    opener = request.build_opener(request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(req, timeout=15) as response:
            code = response.status
            raw = response.read(131073)
    except error.HTTPError as exc:
        if method == "GET" and path.endswith("/entrypoint") and exc.code == 404:
            return 404, {}
        raise GateError("provider_http_error") from None
    except (OSError, ValueError):
        raise GateError("provider_transport_error") from None
    if code not in (200, 201) or len(raw) > 131072:
        raise GateError("provider_status_or_size_error")
    try:
        doc = json.loads(raw)
    except (ValueError, TypeError):
        raise GateError("provider_json_error") from None
    if (
        not isinstance(doc, dict)
        or doc.get("success") is not True
        or not isinstance(doc.get("result"), dict)
    ):
        raise GateError("provider_unsuccessful")
    return code, doc["result"]


def provision_secret(expected_main: str) -> None:
    """Separately owner-gated dedicated credential provisioning."""
    verified_installed_release(expected_main)
    try:
        parent = SECRET.parent.lstat()
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != 0
            or parent.st_gid != 0
            or stat.S_IMODE(parent.st_mode) & 0o077
        ):
            raise GateError("secret_directory_not_private")
        try:
            SECRET.lstat()
        except FileNotFoundError:
            pass
        else:
            raise GateError("dedicated_secret_already_exists")
        tty = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY | os.O_NOFOLLOW)
        try:
            if not os.isatty(tty):
                raise GateError("controlling_tty_required")
        finally:
            os.close(tty)
    except OSError:
        raise GateError(
            "controlling_tty_or_private_directory_unavailable"
        ) from None

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            zone = getpass.getpass("Dedicated ausmalwiese.de Zone ID (hidden): ")
            token = getpass.getpass(
                "Dedicated Zone Read + Zone WAF Write token (hidden): "
            )
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning, OSError):
        raise GateError("secure_local_tty_input_failed") from None

    if not hex_id(zone) or not isinstance(token, str) or not 16 <= len(token) <= 512:
        raise GateError("credential_shape_invalid")

    _, zone_data = api_call(token, "GET", f"/zones/{zone}")
    if zone_data.get("id") != zone or zone_data.get("name") != ZONE_NAME:
        raise GateError("provider_zone_identity_mismatch")

    endpoint = f"/zones/{zone}/rulesets/phases/{PHASE}/entrypoint"
    code, snapshot = api_call(token, "GET", endpoint)
    if code == 200:
        _entrypoint(snapshot)
    elif code != 404:
        raise GateError("unexpected_entrypoint_status")

    payload = (json.dumps({
        "zone_id": zone,
        "zone_name": ZONE_NAME,
        "api_token": token,
    }, separators=(",", ":")) + "\n").encode()

    try:
        fd = os.open(
            SECRET,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
    except OSError:
        raise GateError("dedicated_secret_create_blocked") from None
    try:
        try:
            os.fchmod(fd, 0o600)
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                if written < 1:
                    raise OSError("short write")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        if owned_file(SECRET, 0o600) != payload:
            raise GateError("secret_post_write_mismatch")
    except (OSError, GateError):
        raise GateError("secret_post_mutation_unknown_state") from None


def execute_create(expected_main: str, apply: bool) -> dict:
    zone, token = installed_credentials(expected_main)
    values = read_household_sources()
    _, zone_data = api_call(token, "GET", f"/zones/{zone}")
    if zone_data.get("name") != ZONE_NAME or zone_data.get("id") != zone:
        raise GateError("provider_zone_identity_mismatch")
    endpoint = f"/zones/{zone}/rulesets/phases/{PHASE}/entrypoint"
    code, snapshot = api_call(token, "GET", endpoint)
    mode, path, payload, before = plan(
        None if code == 404 else snapshot,
        zone,
        values,
    )
    summary = source_shape(values)
    if not apply:
        return {
            "status": "ready_for_separate_live_gate",
            "operation": mode,
            "existing_rules": len(before),
            "source_shape": summary,
            "writes": 0,
        }
    api_call(token, "POST", path, payload)
    _, after = api_call(token, "GET", endpoint)
    verify(after, before, values)
    return {
        "status": "verified",
        "operation": mode,
        "source_shape": summary,
        "writes_attempted": 1,
    }


def execute_update(expected_main: str, apply: bool) -> dict:
    zone, token = installed_credentials(expected_main)
    values = read_household_sources()
    _, zone_data = api_call(token, "GET", f"/zones/{zone}")
    if zone_data.get("name") != ZONE_NAME or zone_data.get("id") != zone:
        raise GateError("provider_zone_identity_mismatch")
    endpoint = f"/zones/{zone}/rulesets/phases/{PHASE}/entrypoint"
    code, snapshot = api_call(token, "GET", endpoint)
    if code != 200:
        raise GateError("existing_entrypoint_required")

    mode, path, payload, before, target_index, incumbent = plan_update(
        snapshot,
        zone,
        values,
    )
    result = {
        "status": "ready_for_separate_live_gate",
        "operation": mode,
        "existing_rules": len(before),
        "incumbent_source_shape": source_shape(incumbent),
        "source_shape": source_shape(values),
        "writes": 0,
    }
    if not apply:
        return result

    try:
        api_call(token, "PATCH", path, payload)
    except GateError:
        raise GateError("patch_outcome_unknown") from None
    try:
        _, after = api_call(token, "GET", endpoint)
        verify_update(after, before, target_index, values)
    except GateError:
        raise GateError("post_patch_verification_failed") from None
    result["status"] = "verified"
    result["writes_attempted"] = 1
    result.pop("writes")
    return result


def offline_plan() -> dict:
    return {
        "status": "source_only",
        "zone": ZONE_NAME,
        "hosts": list(HOSTS),
        "path": PATH,
        "phase": PHASE,
        "action": "block",
        "rule_ref": RULE_REF,
        "household_input": "hidden_local_tty_only",
        "maximum_sources": MAX_SOURCES,
        "minimum_ipv4_cidr_prefix": MIN_IPV4_PREFIX,
        "minimum_ipv6_cidr_prefix": MIN_IPV6_PREFIX,
        "create_confirmation": CREATE_CONFIRM,
        "update_confirmation": UPDATE_CONFIRM,
        "update_semantics": "preserve-incumbent-add-ipv6-only",
        "writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Ausmalwiese household GoatCounter edge exclusion"
    )
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--provision-secret", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--update-preflight", action="store_true")
    parser.add_argument("--update-apply", action="store_true")
    parser.add_argument("--expected-main", default="")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)

    modes = (
        args.plan,
        args.preflight,
        args.provision_secret,
        args.apply,
        args.update_preflight,
        args.update_apply,
    )
    if sum(modes) > 1:
        raise GateError("conflicting_modes")

    if not any(modes):
        if args.confirm or args.expected_main:
            raise GateError("offline_preview_has_no_authorization")
        print(json.dumps(offline_plan(), sort_keys=True))
        return 0

    if args.plan:
        if args.confirm or args.expected_main:
            raise GateError("offline_preview_has_no_authorization")
        print(json.dumps(offline_plan(), sort_keys=True))
        return 0

    if args.preflight and args.confirm:
        raise GateError("preflight_must_be_read_only")

    if args.provision_secret:
        if args.confirm != "PROVISION-AUSMALWIESE-ZONE-WAF-SECRET":
            raise GateError("provision_confirmation_required")
        provision_secret(args.expected_main)
        print(json.dumps({
            "status": "provisioned",
            "zone": ZONE_NAME,
            "files_created": 1,
        }, sort_keys=True))
        return 0

    if args.update_preflight:
        if args.confirm:
            raise GateError("preflight_must_be_read_only")
        result = execute_update(args.expected_main, False)
    elif args.update_apply:
        if args.confirm != UPDATE_CONFIRM:
            raise GateError("exact_update_confirmation_required")
        result = execute_update(args.expected_main, True)
    else:
        if args.apply and args.confirm != CREATE_CONFIRM:
            raise GateError("exact_apply_confirmation_required")
        result = execute_create(args.expected_main, args.apply)

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (GateError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        print("STOP: bounded_household_waf_gate", file=sys.stderr)
        sys.exit(2)
