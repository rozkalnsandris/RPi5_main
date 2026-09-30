#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/lib"))

from deploy_executor import weather_operator_v10_successor_broker_refresh as refresh

BASE_OPERATOR = ROOT / "scripts/refresh-weather-operator-v9-host-capability-broker.py"
CONTRACT = ROOT / "ops/deploy/weather-operator-v10-successor-broker-refresh.json"
PREDECESSOR_BROKER_SOURCES = refresh.PREDECESSOR_BROKER_SOURCES
TARGET_BROKER_SOURCE = "ops/bin/rozkalns-weather-operator-v10-successor-privileged-broker"


def _load_base_operator():
    spec = importlib.util.spec_from_file_location("weather_v10_successor_broker_refresh_base", BASE_OPERATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("base broker-refresh operator cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.refresh = refresh
    module.CONTRACT = CONTRACT
    module.BROKER_SOURCE = TARGET_BROKER_SOURCE
    return module


base = _load_base_operator()


def _source_sha() -> str:
    sha = base.run_git("rev-parse", "HEAD").stdout.strip()
    if refresh.SHA40_RE.fullmatch(sha) is None:
        base.fail("source HEAD is not an exact lowercase SHA")
    if base.run_git("remote", "get-url", "origin").stdout.strip() != base.ORIGIN:
        base.fail("source origin drifted")
    if base.run_git("status", "--porcelain", "--untracked-files=all").stdout != "":
        base.fail("source checkout must be clean")
    return sha


def _artifact_hashes(commit: str, manager: Path, broker_source: str) -> dict[str, str]:
    base.require_executable_git_mode(commit, broker_source)
    return {
        "module_sha256": refresh.sha256(base.git_blob(commit, base.MODULE_SOURCE)),
        "broker_sha256": refresh.sha256(base.git_blob(commit, broker_source)),
        "socket_sha256": refresh.sha256(base.git_blob(commit, base.SOCKET_SOURCE)),
        "service_sha256": refresh.sha256(base.render_service(base.git_blob(commit, base.SERVICE_SOURCE), manager)),
    }


def _candidate_broker_hashes(commit: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for broker_source in PREDECESSOR_BROKER_SOURCES:
        exists = base.run_git("cat-file", "-e", f"{commit}:{broker_source}", check=False)
        if exists.returncode != 0:
            continue
        base.require_executable_git_mode(commit, broker_source)
        result[broker_source] = refresh.sha256(base.git_blob(commit, broker_source))
    return result


def _validate_contract() -> None:
    try:
        value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise base.CapabilityBrokerRefreshOperatorError("successor broker-refresh contract is unavailable or malformed") from exc
    budget = tuple(
        (item.get("category"), item.get("max_operations"))
        for item in value.get("mutation_budget", [])
        if type(item) is dict
    )
    if (
        value.get("schema") != "rozkalns.rpi5-main.weather-operator-v10-successor-broker-refresh.v1"
        or value.get("issue") != 664
        or value.get("minimum_predecessor_ancestor") != refresh.MINIMUM_PREDECESSOR_ANCESTOR
        or value.get("predecessor_broker_sources") != list(PREDECESSOR_BROKER_SOURCES)
        or value.get("predecessor_selection") != "REGISTRATION_BROKER_SHA256_EXACTLY_ONE_FIXED_GIT_SOURCE"
        or value.get("target_broker_source") != TARGET_BROKER_SOURCE
        or value.get("replacement_order") != ["broker", "registration"]
        or budget != refresh.MUTATION_BUDGET
        or value.get("state_db_policy") != "PRESERVE_EXISTING_UNCHANGED"
        or value.get("systemd_mutation") is not False
        or value.get("queue_or_live_auth_creation") is not False
        or value.get("source_merge_authorizes_live") is not False
    ):
        base.fail("successor broker-refresh contract drifted")


def _preflight_material():
    _validate_contract()
    target_sha = _source_sha()
    registration = base.load_registration()
    predecessor_sha = str(registration["capability_source_sha"])
    if refresh.SHA40_RE.fullmatch(predecessor_sha) is None:
        base.fail("installed registration predecessor SHA is invalid")
    if base.run_git("merge-base", "--is-ancestor", refresh.MINIMUM_PREDECESSOR_ANCESTOR, predecessor_sha, check=False).returncode != 0:
        base.fail("installed predecessor predates the reviewed v9 capability floor")
    if base.run_git("merge-base", "--is-ancestor", predecessor_sha, target_sha, check=False).returncode != 0:
        base.fail("target source does not descend from the installed predecessor source")
    manager = Path(str(registration["manager_checkout"]))
    if not manager.is_absolute() or manager.name != "RPi5_main":
        base.fail("registered manager checkout identity drifted")

    try:
        predecessor_broker_source = refresh.select_predecessor_broker_source(
            str(registration["broker_sha256"]),
            _candidate_broker_hashes(predecessor_sha),
        )
    except refresh.WeatherV10SuccessorBrokerRefreshError as exc:
        raise base.CapabilityBrokerRefreshOperatorError(str(exc)) from exc
    predecessor = _artifact_hashes(predecessor_sha, manager, predecessor_broker_source)
    target = _artifact_hashes(target_sha, manager, TARGET_BROKER_SOURCE)
    installed = base.installed_hashes()
    before_state = base.state_snapshot()
    try:
        plan = refresh.build_refresh_plan(
            source_sha=target_sha,
            predecessor_source_sha=predecessor_sha,
            registration=registration,
            predecessor_hashes=predecessor,
            installed_hashes=installed,
            target_hashes=target,
            state_db_present=True,
            temp_paths_absent=not (
                base.BROKER_TEMP.exists() or base.BROKER_TEMP.is_symlink()
                or base.REGISTRATION_TEMP.exists() or base.REGISTRATION_TEMP.is_symlink()
            ),
        )
    except refresh.WeatherV10SuccessorBrokerRefreshError as exc:
        raise base.CapabilityBrokerRefreshOperatorError(str(exc)) from exc
    broker_bytes = base.git_blob(target_sha, TARGET_BROKER_SOURCE)
    registration_bytes = refresh.registration_bytes(plan.new_registration)
    return plan, broker_bytes, registration_bytes, before_state


base.preflight_material = _preflight_material
base.validate_contract = _validate_contract


def main() -> int:
    parser = argparse.ArgumentParser(description="Weather v10 successor privileged broker refresh")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = base.apply() if args.apply else base.preflight()
    result["schema"] = (
        "rozkalns.rpi5-main.weather-operator-v10-successor-broker-refresh-receipt.v1"
        if args.apply
        else "rozkalns.rpi5-main.weather-operator-v10-successor-broker-refresh-preflight.v1"
    )
    return_code = 0
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return return_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (base.CapabilityBrokerRefreshOperatorError, refresh.WeatherV10SuccessorBrokerRefreshError, RuntimeError) as exc:
        print(json.dumps({
            "schema": "rozkalns.rpi5-main.weather-operator-v10-successor-broker-refresh-receipt.v1",
            "result": "FAIL_CLOSED",
            "reason": str(exc),
            "automatic_retry": False,
            "automatic_cleanup": False,
            "automatic_rollback": False,
        }, sort_keys=True, separators=(",", ":")))
        raise SystemExit(78)
