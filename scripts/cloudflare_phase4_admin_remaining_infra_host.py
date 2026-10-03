#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import socket
import subprocess
from pathlib import Path
from typing import Any

REPOSITORY = "rozkalnsandris/RPi5_main"
ISSUE_NUMBER = 819
ADMIN_PATH = Path("ops/contracts/admin-zone-verification-v1.json")
VERIFIER_PATH = Path("ops/contracts/admin-zone-remaining-infra-verifier-v1.json")


class VerifyError(RuntimeError):
    pass


def _run(args: list[str]) -> str:
    proc = subprocess.run(
        args,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=10,
    )
    if proc.returncode != 0:
        raise VerifyError("read_only_command_failed")
    return proc.stdout


def _verify_exact_source(expected_main: str) -> None:
    head = _run(["git", "rev-parse", "HEAD"]).strip()
    if head != expected_main:
        raise VerifyError("exact_main_mismatch")
    for args in (
        ["git", "diff", "--quiet"],
        ["git", "diff", "--cached", "--quiet"],
    ):
        proc = subprocess.run(
            args,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        if proc.returncode != 0:
            raise VerifyError("tracked_source_dirty")


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VerifyError("contract_shape_invalid")
    return value


def _primary_lan_address() -> str:
    raw = _run(["ip", "-j", "-4", "route", "get", "1.1.1.1"])
    decoded = json.loads(raw)
    if not isinstance(decoded, list) or len(decoded) != 1 or not isinstance(decoded[0], dict):
        raise VerifyError("lan_route_shape_invalid")
    address = decoded[0].get("prefsrc") or decoded[0].get("src")
    if not isinstance(address, str) or not address:
        raise VerifyError("lan_address_unavailable")
    return address


def _split_local_endpoint(value: str) -> tuple[str, int] | None:
    text = value.strip()
    if text.startswith("[") and "]:" in text:
        host, port = text[1:].rsplit("]:", 1)
    elif ":" in text:
        host, port = text.rsplit(":", 1)
    else:
        return None
    try:
        return host, int(port)
    except ValueError:
        return None


def _listeners_by_port(ss_text: str) -> dict[int, set[str]]:
    result: dict[int, set[str]] = {}
    for line in ss_text.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        endpoint = _split_local_endpoint(parts[3])
        if endpoint is None:
            continue
        host, port = endpoint
        result.setdefault(port, set()).add(host)
    return result


def _classify_bind(addresses: set[str], lan_address: str) -> str:
    if not addresses:
        return "none"

    classes: set[str] = set()
    for address in addresses:
        normalized = address.strip("[]")
        if normalized in {"127.0.0.1", "::1"}:
            classes.add("loopback")
        elif normalized in {"0.0.0.0", "::", "*"}:
            classes.add("wildcard")
        elif normalized == lan_address:
            classes.add("lan")
        else:
            classes.add("other")

    if len(classes) == 1:
        return next(iter(classes))
    return "mixed"


def _lan_path_class(lan_address: str, port: int) -> str:
    try:
        with socket.create_connection((lan_address, port), timeout=1.5):
            return "present"
    except (ConnectionRefusedError, TimeoutError, socket.timeout, OSError):
        return "absent"


def _recovery_ref_present(value: Any) -> bool:
    if not isinstance(value, str) or not value or value.startswith("/"):
        return False
    path = Path(value)
    return ".." not in path.parts and path.is_file()


def _validate_contracts(
    admin: dict[str, Any],
    verifier: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if admin.get("schema") != "rozkalns.rpi5-main.admin-zone-verification.v1":
        raise VerifyError("admin_contract_invalid")
    if verifier.get("schema") != "rozkalns.rpi5-main.phase4-admin-remaining-infra-verifier.v1":
        raise VerifyError("remaining_infra_contract_invalid")

    projections = admin.get("service_projections")
    targets = verifier.get("host_probe_targets")
    if not isinstance(projections, list) or not isinstance(targets, list):
        raise VerifyError("contract_shape_invalid")

    projected = {
        item.get("service_id"): item
        for item in projections
        if isinstance(item, dict)
    }
    target_map = {
        item.get("service_id"): item
        for item in targets
        if isinstance(item, dict)
    }
    if set(projected) != set(target_map) or len(projected) != 8:
        raise VerifyError("host_target_set_mismatch")

    for service_id, target in target_map.items():
        if target.get("hostname") != projected[service_id].get("hostname"):
            raise VerifyError("host_target_hostname_mismatch")
        port = target.get("probe_port")
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise VerifyError("host_target_port_invalid")
    return projected


def build_report(
    *,
    expected_main: str,
    admin: dict[str, Any],
    verifier: dict[str, Any],
    listeners: dict[int, set[str]],
    lan_address: str,
) -> dict[str, Any]:
    projected = _validate_contracts(admin, verifier)
    targets = {
        item["service_id"]: item
        for item in verifier["host_probe_targets"]
    }
    bind_policy = verifier["listener_policy"]
    lan_policy = verifier["lan_path_policy"]

    services: list[dict[str, Any]] = []
    for service_id, projection in projected.items():
        target = targets[service_id]
        port = target["probe_port"]
        bind_class = _classify_bind(listeners.get(port, set()), lan_address)
        lan_path = _lan_path_class(lan_address, port)
        owner_matches = projection.get("runtime_owner") == REPOSITORY
        recovery_present = _recovery_ref_present(projection.get("recovery_ref"))

        expected_origin = projection.get("expected_origin_class")
        if expected_origin == "loopback":
            bind_ok = bind_class in bind_policy["loopback_origin_allowed_bind_classes"]
        elif expected_origin == "lan":
            bind_ok = bind_class in bind_policy["lan_origin_allowed_bind_classes"]
        else:
            bind_ok = False

        break_glass = projection.get("lan_break_glass")
        allowed_lan_states = lan_policy.get(break_glass, [])
        lan_ok = lan_path in allowed_lan_states

        result = "PASS" if bind_ok and lan_ok and owner_matches and recovery_present else "FAIL"
        services.append({
            "service_id": service_id,
            "hostname": projection["hostname"],
            "listener_bind_class": bind_class,
            "lan_path_class": lan_path,
            "runtime_owner_matches": owner_matches,
            "recovery_ref_present": recovery_present,
            "result": result,
        })

    overall = "PASS" if all(item["result"] == "PASS" for item in services) else "BLOCKED"
    return {
        "schema_version": 1,
        "audit": "phase4-admin-remaining-infra-host",
        "canonical_issue": ISSUE_NUMBER,
        "verification_class": "unauthenticated-infrastructure",
        "observed_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "source_main_sha": expected_main,
        "result": overall,
        "mutation_performed": False,
        "services": services,
        "privacy": {
            "lan_address_emitted": False,
            "listener_address_emitted": False,
            "port_emitted": False,
            "process_identity_emitted": False,
            "container_identity_emitted": False,
            "raw_command_output_emitted": False,
            "protected_runtime_content_read": False,
        },
    }


def _blocked(reason: str, expected_main: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "audit": "phase4-admin-remaining-infra-host",
        "canonical_issue": ISSUE_NUMBER,
        "source_main_sha": expected_main,
        "result": "BLOCKED",
        "mutation_performed": False,
        "reason": reason,
        "privacy": {
            "lan_address_emitted": False,
            "listener_address_emitted": False,
            "port_emitted": False,
            "process_identity_emitted": False,
            "container_identity_emitted": False,
            "raw_command_output_emitted": False,
            "protected_runtime_content_read": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-main", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    expected_main = args.expected_main
    if len(expected_main) != 40 or any(ch not in "0123456789abcdef" for ch in expected_main):
        print(json.dumps(_blocked("expected_main_invalid", expected_main), indent=2, sort_keys=True))
        return 2

    try:
        _verify_exact_source(expected_main)
        admin = _load_json(ADMIN_PATH)
        verifier = _load_json(VERIFIER_PATH)
        lan_address = _primary_lan_address()
        listeners = _listeners_by_port(_run(["ss", "-H", "-lnt"]))
        report = build_report(
            expected_main=expected_main,
            admin=admin,
            verifier=verifier,
            listeners=listeners,
            lan_address=lan_address,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["result"] == "PASS" else 3
    except (VerifyError, json.JSONDecodeError, OSError, subprocess.SubprocessError):
        print(json.dumps(_blocked("read_only_host_verification_failed", expected_main), indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
