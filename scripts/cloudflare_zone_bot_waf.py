#!/usr/bin/env python3
"""Exact-zone, single-rule Cloudflare WAF operator. No writes without gated --apply."""
from __future__ import annotations

import argparse
import getpass
import warnings
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib import error, request

ZONE_NAME = "rozkalns.net"
PHASE = "http_request_firewall_custom"
RULE_REF = "rozkalns-zone-ai-crawlers-v1"
INSTALLED = Path("/usr/local/sbin/rpi5-cloudflare-zone-bot-waf")
RELEASE = Path("/usr/local/libexec/rpi5-cloudflare-zone-bot-waf/release.json")
SECRET = Path("/etc/rpi5-secrets/cloudflare/zone-waf-writer.json")
BASE = "https://api.cloudflare.com/client/v4"
UA_MARKERS = (
    "gptbot", "chatgpt-user", "claudebot", "claude-user",
    "bytespider", "ccbot",
    "perplexity-user", "amazonbot", "cohere-ai", "meta-externalagent",
)
HOST_SCOPE = '(lower(http.host) eq "rozkalns.net" or ends_with(lower(http.host), ".rozkalns.net"))'
EXPRESSION = f'({HOST_SCOPE} and (' + " or ".join(
    f'lower(http.user_agent) contains "{marker}"' for marker in UA_MARKERS
) + '))'
RULE = {
    "ref": RULE_REF,
    "description": "Rozkalns: block selected AI crawler/agent User-Agents (source v1)",
    "expression": EXPRESSION,
    "action": "block",
    "enabled": True,
}


class GateError(Exception):
    """Fail-closed, user-safe error. Never include provider bodies or secrets."""


def hex_id(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{32}", value) is not None


def existing_projection(rules: list) -> list[tuple]:
    if not isinstance(rules, list):
        raise GateError("invalid_existing_rules")
    result = []
    for entry in rules:
        if not isinstance(entry, dict) or not hex_id(entry.get("id")):
            raise GateError("invalid_existing_rule_identity")
        if not isinstance(entry.get("expression"), str) or not isinstance(entry.get("action"), str):
            raise GateError("invalid_existing_rule_fields")
        result.append((entry["id"], entry.get("ref"), entry["action"],
                       entry["expression"], entry.get("enabled", True)))
    if len(set(item[0] for item in result)) != len(result):
        raise GateError("duplicate_existing_rule_id")
    return result


def plan(snapshot: dict | None, zone_id: str) -> tuple[str, str, dict, list[tuple]]:
    """Return exactly one allowed POST, preserving existing rules in-place."""
    if not hex_id(zone_id):
        raise GateError("invalid_zone_id")
    prefix = f"/zones/{zone_id}/rulesets"
    if snapshot is None:
        return ("create_entrypoint", prefix, {
            "name": "Zone-level custom WAF", "kind": "zone", "phase": PHASE,
            "rules": [dict(RULE)],
        }, [])
    if not isinstance(snapshot, dict) or snapshot.get("phase") != PHASE or snapshot.get("kind") != "zone":
        raise GateError("unexpected_entrypoint")
    rid = snapshot.get("id")
    if not hex_id(rid):
        raise GateError("invalid_entrypoint_id")
    before = existing_projection(snapshot.get("rules"))
    if any(item[1] == RULE_REF or item[3] == EXPRESSION for item in before):
        raise GateError("rule_already_present_or_conflict")
    return ("append_one_rule", f"{prefix}/{rid}/rules", dict(RULE), before)


def verify(after: dict, before: list[tuple]) -> None:
    if not isinstance(after, dict) or after.get("phase") != PHASE or after.get("kind") != "zone":
        raise GateError("verification_entrypoint_mismatch")
    rules = after.get("rules")
    projection = existing_projection(rules)
    if len(projection) != len(before) + 1 or projection[:len(before)] != before:
        raise GateError("verification_preexisting_rule_drift")
    newest = rules[-1]
    if (newest.get("ref") != RULE_REF or newest.get("expression") != EXPRESSION
            or newest.get("action") != "block" or newest.get("enabled", True) is not True):
        raise GateError("verification_target_rule_mismatch")


def owned_file(path: Path, mode: int) -> bytes:
    try:
        s = path.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_uid != 0 or s.st_gid != 0 or stat.S_IMODE(s.st_mode) != mode:
            raise GateError("protected_file_metadata_mismatch")
        # No symlinks; metadata is rechecked on the open descriptor.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            s2 = os.fstat(fd)
            if not stat.S_ISREG(s2.st_mode) or s2.st_uid != 0 or s2.st_gid != 0 or stat.S_IMODE(s2.st_mode) != mode:
                raise GateError("protected_file_changed")
            with os.fdopen(fd, "rb", closefd=False) as f:
                data = f.read(8193)
            if len(data) > 8192:
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
    release = json.loads(owned_file(RELEASE, 0o400))
    if set(release) != {"source_sha", "operator_sha256"} or release["source_sha"] != expected_main:
        raise GateError("release_identity_mismatch")
    if not re.fullmatch(r"[a-f0-9]{64}", release["operator_sha256"]):
        raise GateError("invalid_release_hash")
    if hashlib.sha256(owned_file(INSTALLED, 0o500)).hexdigest() != release["operator_sha256"]:
        raise GateError("operator_hash_mismatch")


def installed_credentials(expected_main: str) -> tuple[str, str]:
    verified_installed_release(expected_main)
    secret = json.loads(owned_file(SECRET, 0o600))
    if set(secret) != {"zone_id", "zone_name", "api_token"}:
        raise GateError("secret_schema_mismatch")
    if not hex_id(secret["zone_id"]) or secret["zone_name"] != ZONE_NAME:
        raise GateError("zone_identity_mismatch")
    if not isinstance(secret["api_token"], str) or not (16 <= len(secret["api_token"]) <= 512):
        raise GateError("secret_invalid")
    return secret["zone_id"], secret["api_token"]


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api_call(token: str, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    if not re.fullmatch(r"/zones/[0-9a-f]{32}(?:/rulesets(?:/phases/http_request_firewall_custom/entrypoint|/[0-9a-f]{32}/rules)?)?", path):
        raise GateError("unexpected_api_path")
    if method not in {"GET", "POST"}:
        raise GateError("unexpected_api_method")
    body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
    req = request.Request(BASE + path, data=body, method=method, headers={
        "Authorization": "Bearer " + token, "Content-Type": "application/json",
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
    if not isinstance(doc, dict) or doc.get("success") is not True or not isinstance(doc.get("result"), dict):
        raise GateError("provider_unsuccessful")
    return code, doc["result"]



def provision_secret(expected_main: str) -> None:
    """Future owner-gated provisioning, only on the installed root operator.

    Credentials are taken exclusively from the local controlling terminal.
    File creation is exclusive; after that first mutation, errors require STOP.
    """
    verified_installed_release(expected_main)
    try:
        parent = SECRET.parent.lstat()
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0
                or parent.st_gid != 0 or stat.S_IMODE(parent.st_mode) & 0o077):
            raise GateError("secret_directory_not_private")
        # No symlink, file, or dangling symlink may preexist.
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
        raise GateError("controlling_tty_or_private_directory_unavailable") from None

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            zone = getpass.getpass("Dedicated rozkalns.net Zone ID (hidden): ")
            token = getpass.getpass("Dedicated Zone Read + Zone WAF Edit token (hidden): ")
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning, OSError):
        raise GateError("secure_local_tty_input_failed") from None
    if not hex_id(zone) or not isinstance(token, str) or not (16 <= len(token) <= 512):
        raise GateError("credential_shape_invalid")

    # A successful GET proves zone identity and read capability, NOT permission
    # to mutate. Cloudflare token scope is owner-verified separately before apply.
    _, target = api_call(token, "GET", f"/zones/{zone}")
    if target.get("id") != zone or target.get("name") != ZONE_NAME:
        raise GateError("provider_zone_identity_mismatch")
    entrypoint = f"/zones/{zone}/rulesets/phases/{PHASE}/entrypoint"
    code, snapshot = api_call(token, "GET", entrypoint)
    plan(None if code == 404 else snapshot, zone)

    payload = (json.dumps({"zone_id": zone, "zone_name": ZONE_NAME, "api_token": token},
                          separators=(",", ":")) + "\n").encode()
    # FIRST MUTATION; never delete, retry or auto-repair after open succeeds.
    try:
        fd = os.open(SECRET, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except OSError:
        raise GateError("dedicated_secret_create_blocked") from None
    try:
        try:
            os.fchmod(fd, 0o600)
            view = memoryview(payload)
            while view:
                n = os.write(fd, view)
                if n < 1:
                    raise OSError("short write")
                view = view[n:]
            os.fsync(fd)
        finally:
            os.close(fd)
        if hashlib.sha256(owned_file(SECRET, 0o600)).digest() != hashlib.sha256(payload).digest():
            raise GateError("secret_post_write_mismatch")
    except (OSError, GateError):
        raise GateError("secret_post_mutation_unknown_state") from None


def main() -> int:
    parser = argparse.ArgumentParser(description="Rozkalns zone-wide named AI crawler WAF rule")
    parser.add_argument("--plan", action="store_true", help="offline rule preview (default)")
    parser.add_argument("--preflight", action="store_true", help="read-only installed operator API check")
    parser.add_argument("--provision-secret", action="store_true", help="separately owner-gated local TTY provisioning")
    parser.add_argument("--apply", action="store_true", help="one owner-gated Cloudflare write")
    parser.add_argument("--expected-main", default="")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    if sum((args.plan, args.preflight, args.apply, args.provision_secret)) > 1:
        raise GateError("conflicting_modes")
    if not args.apply and not args.preflight and not args.provision_secret:
        if args.confirm or args.expected_main:
            raise GateError("offline_preview_has_no_authorization")
        print(json.dumps({"status": "source_only", "phase": PHASE, "rule": RULE}, indent=2))
        return 0
    if args.apply and args.confirm != "CREATE-ROZKALNS-BOT-WAF-RULE":
        raise GateError("exact_apply_confirmation_required")
    if args.preflight and args.confirm:
        raise GateError("preflight_must_be_read_only")
    if args.provision_secret:
        if args.confirm != "PROVISION-ROZKALNS-ZONE-WAF-SECRET":
            raise GateError("provision_confirmation_required")
        provision_secret(args.expected_main)
        print(json.dumps({"status": "provisioned", "zone": ZONE_NAME, "files_created": 1}))
        return 0
    zone, token = installed_credentials(args.expected_main)
    _, zone_data = api_call(token, "GET", f"/zones/{zone}")
    if zone_data.get("name") != ZONE_NAME or zone_data.get("id") != zone:
        raise GateError("provider_zone_identity_mismatch")
    endpoint = f"/zones/{zone}/rulesets/phases/{PHASE}/entrypoint"
    code, snapshot = api_call(token, "GET", endpoint)
    mode, path, payload, before = plan(None if code == 404 else snapshot, zone)
    if args.preflight:
        print(json.dumps({"status": "ready_for_separate_live_gate", "operation": mode,
                          "existing_rules": len(before), "zone": ZONE_NAME, "writes": 0}))
        return 0
    # After first POST, any error is STOP. No retry, cleanup, or rollback.
    api_call(token, "POST", path, payload)
    _, after = api_call(token, "GET", endpoint)
    verify(after, before)
    print(json.dumps({"status": "verified", "zone": ZONE_NAME, "writes_attempted": 1}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (GateError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print("STOP: " + (str(exc) if isinstance(exc, GateError) else "invalid_local_metadata"), file=sys.stderr)
        sys.exit(2)
