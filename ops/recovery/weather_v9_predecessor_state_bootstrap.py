#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.util
import json
import os
from pathlib import Path
import sys
sys.dont_write_bytecode = True
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
BASE_RECOVERY = ROOT / "ops/recovery/weather_v9_capability_state_bootstrap.py"
CONTRACT = ROOT / "ops/recovery/weather_v9_predecessor_state_bootstrap.contract.json"
PREDECESSOR_SOURCE_SHA = "80261255b3be2aa7dd40986254d4ea478b4e2e1b"


def _load_base():
    spec = importlib.util.spec_from_file_location(
        "weather_v9_capability_state_bootstrap_base", BASE_RECOVERY
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("base Weather v9 state bootstrap recovery cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


base = _load_base()

SUPPORT_ROOT = base.SUPPORT_ROOT
PACKAGE_ROOT = base.PACKAGE_ROOT
BROKER_PATH = base.BROKER_PATH
CONFIG_ROOT = base.CONFIG_ROOT
REGISTRATION_PATH = base.REGISTRATION_PATH
STATE_ROOT = base.STATE_ROOT
STATE_DB_PATH = base.STATE_DB_PATH
SYSTEMD_ROOT = base.SYSTEMD_ROOT
SOCKET_NAME = base.SOCKET_NAME
SERVICE_NAME = base.SERVICE_NAME
SOCKET_UNIT_PATH = base.SOCKET_UNIT_PATH
SERVICE_UNIT_PATH = base.SERVICE_UNIT_PATH
MODULE_PATH = base.MODULE_PATH
REGISTRATION_TEMP = base.REGISTRATION_TEMP
KNOWN_STAGING_PATHS = base.KNOWN_STAGING_PATHS
REGISTRATION_SCHEMA = base.REGISTRATION_SCHEMA
REGISTRATION_FIELDS = base.REGISTRATION_FIELDS
MAX_REGISTRATION_BYTES = base.MAX_REGISTRATION_BYTES


class RecoveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class RecoveryPlan:
    execution_source_sha: str
    registration_source_sha: str
    manager_checkout: Path
    manager_uid: int
    manager_gid: int
    artifact_hashes: Mapping[str, str]
    state_root_present: bool


def fail(message: str) -> None:
    raise RecoveryError(message)


def _load_installer():
    return base._load_installer()


def _load_state_store():
    return base._load_state_store()


def _validate_contract(installer: Any) -> None:
    base._validate_contract(installer)
    try:
        value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryError("predecessor state-bootstrap contract is unavailable or malformed") from exc

    expected_targets = {
        "support_root": str(SUPPORT_ROOT),
        "broker": str(BROKER_PATH),
        "registration": str(REGISTRATION_PATH),
        "state_root": str(STATE_ROOT),
        "state_db": str(STATE_DB_PATH),
        "socket_unit": str(SOCKET_UNIT_PATH),
        "service_unit": str(SERVICE_UNIT_PATH),
        "module": str(MODULE_PATH),
    }
    if (
        value.get("schema")
        != "rozkalns.rpi5-main.weather-operator-v9-predecessor-state-bootstrap.v1"
        or value.get("issue") != 625
        or value.get("predecessor_source_sha") != PREDECESSOR_SOURCE_SHA
        or value.get("accepted_baseline")
        != {"registration": "ABSENT", "state_db": "ABSENT"}
        or value.get("fixed_targets") != expected_targets
        or value.get("artifact_count") != 15
        or value.get("registration_schema") != REGISTRATION_SCHEMA
        or value.get("registration_binding_source_sha") != PREDECESSOR_SOURCE_SHA
        or value.get("registration_published_last") is not True
        or value.get("systemd_mutation") is not False
        or value.get("automatic_retry") is not False
        or value.get("automatic_cleanup") is not False
        or value.get("automatic_rollback") is not False
        or value.get("source_merge_authorizes_live") is not False
        or value.get("known_staging_paths") != [str(path) for path in KNOWN_STAGING_PATHS]
    ):
        fail("predecessor state-bootstrap contract drifted")


def _execution_source_sha(installer: Any) -> str:
    try:
        sha = str(installer.source_sha())
        ancestor = installer.run_git(
            "merge-base",
            "--is-ancestor",
            PREDECESSOR_SOURCE_SHA,
            sha,
            check=False,
        )
    except Exception as exc:
        raise RecoveryError("execution source provenance preflight failed") from exc
    if sha == PREDECESSOR_SOURCE_SHA:
        fail("execution source must be newer than the predecessor binding")
    if ancestor.returncode != 0:
        fail("execution source no longer descends from the reviewed predecessor")
    return sha


def _predecessor_installed_bytes(
    installer: Any, source: str, manager: Path, mode: int
) -> bytes:
    expected_git_mode = "100755" if mode & 0o111 else "100644"
    try:
        tree = installer.run_git(
            "ls-tree", PREDECESSOR_SOURCE_SHA, "--", source, check=False
        )
        shown = installer.run_git(
            "show", f"{PREDECESSOR_SOURCE_SHA}:{source}", check=False
        )
    except Exception as exc:
        raise RecoveryError(f"predecessor source artifact unavailable: {source}") from exc
    if tree.returncode != 0 or not tree.stdout.strip().startswith(
        expected_git_mode + " blob "
    ):
        fail(f"predecessor source mode drifted: {source}")
    if shown.returncode != 0 or shown.stdout == "":
        fail(f"predecessor source blob is unavailable: {source}")
    try:
        data = shown.stdout.encode("utf-8")
    except UnicodeError as exc:
        raise RecoveryError(f"predecessor source blob is not UTF-8: {source}") from exc
    service_source = getattr(installer, "SERVICE_SOURCE", None)
    if source == service_source:
        try:
            data = installer.render_service_unit(data, manager)
        except Exception as exc:
            raise RecoveryError("predecessor service rendering failed") from exc
    return data


def preflight_material(installer: Any | None = None) -> RecoveryPlan:
    installer = _load_installer() if installer is None else installer
    _validate_contract(installer)

    base._require_absent(REGISTRATION_PATH)
    base._require_absent(STATE_DB_PATH)
    for path in KNOWN_STAGING_PATHS:
        base._require_absent(path)

    base._require_root_directory(CONFIG_ROOT, 0o700)
    state_root_present = base._require_root_directory(
        STATE_ROOT, 0o700, allow_absent=True
    )

    execution_source_sha = _execution_source_sha(installer)
    try:
        manager = Path(installer.canonical_manager_checkout())
        manager_uid, manager_gid = installer.manager_identity(manager)
    except Exception as exc:
        raise RecoveryError("canonical manager provenance preflight failed") from exc
    if not manager.is_absolute() or manager.name != "RPi5_main":
        fail("canonical manager checkout identity drifted")
    if (
        type(manager_uid) is not int
        or type(manager_gid) is not int
        or manager_uid <= 0
        or manager_gid <= 0
    ):
        fail("canonical manager owner identity is invalid")

    artifact_hashes: dict[str, str] = {}
    targets: set[Path] = set()
    for source, target, mode in installer.ARTIFACTS:
        target = Path(target)
        if target in targets:
            fail("canonical installer contains duplicate artifact target")
        targets.add(target)
        expected = _predecessor_installed_bytes(installer, source, manager, int(mode))
        observed = base._safe_regular_bytes(target, mode=int(mode))
        if observed != expected:
            fail(f"installed artifact bytes drifted from predecessor source: {target}")
        artifact_hashes[str(target)] = base._sha256(observed)

    required_identity_targets = {
        MODULE_PATH,
        BROKER_PATH,
        SOCKET_UNIT_PATH,
        SERVICE_UNIT_PATH,
    }
    if not required_identity_targets.issubset(targets):
        fail("canonical installer identity targets drifted")

    return RecoveryPlan(
        execution_source_sha=execution_source_sha,
        registration_source_sha=PREDECESSOR_SOURCE_SHA,
        manager_checkout=manager,
        manager_uid=manager_uid,
        manager_gid=manager_gid,
        artifact_hashes=artifact_hashes,
        state_root_present=state_root_present,
    )


def _registration(plan: RecoveryPlan) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": REGISTRATION_SCHEMA,
        "capability_source_sha": plan.registration_source_sha,
        "manager_checkout": str(plan.manager_checkout),
        "manager_uid": plan.manager_uid,
        "manager_gid": plan.manager_gid,
        "artifact_count": 15,
        "module_sha256": plan.artifact_hashes[str(MODULE_PATH)],
        "broker_sha256": plan.artifact_hashes[str(BROKER_PATH)],
        "socket_sha256": plan.artifact_hashes[str(SOCKET_UNIT_PATH)],
        "service_sha256": plan.artifact_hashes[str(SERVICE_UNIT_PATH)],
    }
    if frozenset(value) != REGISTRATION_FIELDS:
        fail("registration fields drifted")
    return value


def _registration_bytes(plan: RecoveryPlan) -> bytes:
    return json.dumps(
        _registration(plan),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8") + b"\n"


def _verify_state_db(StateStore: Any) -> None:
    raw = base._safe_regular_bytes(
        STATE_DB_PATH, mode=0o600, max_bytes=64 * 1024 * 1024
    )
    if not raw.startswith(b"SQLite format 3\x00"):
        fail("bootstrapped state database does not have canonical SQLite header")
    try:
        with StateStore(STATE_DB_PATH):
            pass
    except Exception as exc:
        raise RecoveryError("bootstrapped StateStore integrity verification failed") from exc


def preflight() -> dict[str, object]:
    plan = preflight_material()
    return {
        "schema": (
            "rozkalns.rpi5-main.weather-operator-v9-predecessor-state-bootstrap-"
            "preflight.v1"
        ),
        "result": "PASS",
        "execution_source_sha": plan.execution_source_sha,
        "registration_source_sha": plan.registration_source_sha,
        "artifact_count": len(plan.artifact_hashes),
        "state_root_action": (
            "PRESERVE" if plan.state_root_present else "CREATE_ROOT_0700"
        ),
        "next_gate": "POST83_BROKER_REFRESH",
        "host_mutation_started": False,
        "systemd_mutation": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
        "source_merge_authorizes_live": False,
    }


def apply() -> dict[str, object]:
    if os.geteuid() != 0:
        fail("--apply requires a separately owner-authorized root process")

    plan = preflight_material()
    StateStore = _load_state_store()
    registration_bytes = _registration_bytes(plan)
    mutation_started = False

    try:
        if not plan.state_root_present:
            STATE_ROOT.mkdir(mode=0o700, parents=False, exist_ok=False)
            os.chown(STATE_ROOT, base.ROOT_UID, base.ROOT_GID)
            os.chmod(STATE_ROOT, 0o700)
            mutation_started = True

        mutation_started = True
        with StateStore(STATE_DB_PATH, bootstrap=True):
            pass
        os.chown(STATE_DB_PATH, base.ROOT_UID, base.ROOT_GID)
        os.chmod(STATE_DB_PATH, 0o600)
        base._fsync_directory(STATE_ROOT)
        _verify_state_db(StateStore)

        base._write_exclusive(REGISTRATION_TEMP, registration_bytes, 0o600)
        if base._safe_regular_bytes(
            REGISTRATION_TEMP, mode=0o600, max_bytes=MAX_REGISTRATION_BYTES
        ) != registration_bytes:
            fail("staged registration identity drifted")
        os.replace(REGISTRATION_TEMP, REGISTRATION_PATH)
        base._fsync_directory(CONFIG_ROOT)
        if base._safe_regular_bytes(
            REGISTRATION_PATH, mode=0o600, max_bytes=MAX_REGISTRATION_BYTES
        ) != registration_bytes:
            fail("published predecessor registration identity drifted")
    except Exception as exc:
        raise RecoveryError(
            "Weather v9 predecessor state bootstrap failed closed after mutation; "
            "no retry/cleanup/rollback is authorized"
        ) from exc

    return {
        "schema": (
            "rozkalns.rpi5-main.weather-operator-v9-predecessor-state-bootstrap-"
            "receipt.v1"
        ),
        "result": "PASS",
        "execution_source_sha": plan.execution_source_sha,
        "registration_source_sha": plan.registration_source_sha,
        "artifact_count": len(plan.artifact_hashes),
        "host_mutation_started": mutation_started,
        "state_db_bootstrapped": True,
        "registration_published": True,
        "next_gate": "POST83_BROKER_REFRESH",
        "systemd_mutation": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Recover Weather v9 predecessor-bound durable state before the "
            "post-#83 broker refresh"
        )
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = apply() if args.apply else preflight()
    except RecoveryError as exc:
        print(
            json.dumps(
                {
                    "schema": (
                        "rozkalns.rpi5-main.weather-operator-v9-predecessor-state-"
                        "bootstrap-receipt.v1"
                        if args.apply
                        else "rozkalns.rpi5-main.weather-operator-v9-predecessor-state-"
                        "bootstrap-preflight.v1"
                    ),
                    "result": "FAIL_CLOSED",
                    "reason": str(exc),
                    "automatic_retry": False,
                    "automatic_cleanup": False,
                    "automatic_rollback": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 78
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
