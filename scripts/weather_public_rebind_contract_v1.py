#!/usr/bin/env python3
"""Pure Weather rebind source-contract and sanitized-evidence validator.

No host, Docker, credential, network, process, or filesystem mutation capability.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ops/contracts/weather-public-rebind-execution-v1.json"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def contract() -> dict[str, Any]:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def source_errors(spec: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if spec["schema"] != "rozkalns.rpi5-main.weather-public-rebind-execution.v1":
        errors.append("SCHEMA")
    if spec["status"] != "SOURCE_ONLY_UNEXECUTABLE":
        errors.append("AUTHORITY")
    for kind, expected in (("compose", "compose_sha256"), ("registry", "registry_sha256")):
        path = ROOT / spec["source_files"][kind]
        if hashlib.sha256(path.read_bytes()).hexdigest() != spec["desired"][expected]:
            errors.append("SOURCE_HASH_" + kind.upper())
    registry = json.loads((ROOT / spec["source_files"]["registry"]).read_text())
    matches = [x for x in registry["targets"] if x.get("target_alias") == spec["target_alias"]]
    if len(matches) != 1:
        errors.append("WEATHER_TARGET")
    else:
        item = matches[0]
        if item["compose"]["file_sha256"] != spec["desired"]["compose_sha256"]:
            errors.append("COMPOSE_PIN")
        if item["shared_workflow_sha"] != spec["desired"]["shared_workflow_sha"]:
            errors.append("WORKFLOW_PIN")
        if item["persistent_volumes"] != ["weather_data"]:
            errors.append("VOLUME")
    compose = (ROOT / spec["source_files"]["compose"]).read_text()
    if '      - "127.0.0.1:${WEATHER_PORT:-9180}:8000"' not in compose:
        errors.append("LOOPBACK")
    if spec["authority"]["this_contract_authorizes_host"] is not False:
        errors.append("LIVE_AUTHORITY")
    baseline = spec["baseline"]
    if baseline.get("registry_source_revision") != "fe69b6e325fa9edec04e8963b5010f946ac4d83c":
        errors.append("INSTALLED_REGISTRY_PROVENANCE")
    if baseline.get("registry_sha256_from_readonly_host") != "88c3acbf304ab9676a6a767e5f3055351f20fd88ca9bf1bf4a2cb1210ef3617f":
        errors.append("INSTALLED_REGISTRY_PIN")
    if baseline.get("registry_and_identity_sources_differ") is not True:
        errors.append("MIXED_SOURCE_PROVENANCE")
    if baseline.get("protected_env_file") != {
        "owner": "root", "group": "rozkalns-simple-deployer",
        "mode": "0640", "metadata_only": True,
    }:
        errors.append("PROTECTED_ENV_METADATA_CONTRACT")
    return errors


def preflight(spec: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    required = set(spec["preflight"]["required_fields"])
    if type(evidence) is not dict or set(evidence) != required:
        return {"result": "BLOCKED", "blockers": ["EVIDENCE_SCHEMA"], "mutation_performed": False}
    base = spec["baseline"]
    tests: dict[str, bool] = {
        "MAIN_SHA": type(evidence["exact_final_main"]) is str and FULL_SHA.fullmatch(evidence["exact_final_main"]) is not None,
        "INSTALLED_IDENTITY": evidence["installed_identity_sha"] == base["identity_source_sha"],
        "INSTALLED_REGISTRY": evidence["installed_registry_sha256"] == base["registry_sha256_from_readonly_host"],
        "INSTALLED_COMPOSE": evidence["installed_compose_sha256"] == base["compose_sha256_from_readonly_host"],
        "CONTAINER_COUNT": evidence["weather_container_count"] == 1,
        "PUBLISH_CLASS": evidence["weather_publish_class"] == "wildcard",
    }
    for key in ("checkout_exact_clean_main_origin", "root_owned_files_mode_0444",
                "candidate_source_hashes_match", "non_weather_registry_targets_identical",
                "weather_target_exact", "target_lock_available", "no_blocking_stop_error",
                "weather_running_healthy", "weather_volume_preserved",
                "image_labels_pass", "protected_env_metadata_only"):
        tests[key.upper()] = evidence[key] is True
    for key in ("receipt_digest", "override_digest", "running_image_digest"):
        tests[key.upper()] = type(evidence[key]) is str and IMAGE_DIGEST.fullmatch(evidence[key]) is not None
    tests["DIGEST_IDENTITY"] = len({evidence["receipt_digest"], evidence["override_digest"], evidence["running_image_digest"]}) == 1
    blocked = [name for name, passed in tests.items() if not passed]
    return {"result": "BLOCKED" if blocked else "PASS", "blockers": blocked, "mutation_performed": False}


def postverify(spec: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    fields = spec["postverify_required"]
    if type(evidence) is not dict or set(evidence) != set(fields):
        return {"result": "BLOCKED", "blockers": ["EVIDENCE_SCHEMA"]}
    missing = [key for key in fields if evidence[key] is not True]
    return {"result": "DRIFT" if missing else "PASS", "blockers": missing}


if __name__ == "__main__":
    errors = source_errors(contract())
    print("WEATHER_REBIND_SOURCE_CONTRACT=" + ("PASS" if not errors else "DRIFT"))
    if errors:
        raise SystemExit(2)
