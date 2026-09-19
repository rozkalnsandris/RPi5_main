#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = ROOT / "scripts/install-weather-v9-predecessor-bootstrap-capability.py"
CORE_PATH = ROOT / "ops/lib/deploy_executor/weather_v9_predecessor_bootstrap_privileged.py"
CONTRACT_PATH = ROOT / "ops/recovery/weather_v9_predecessor_bootstrap_preflight_diagnostic.contract.json"
SCHEMA = "rozkalns.rpi5-main.weather-v9-predecessor-bootstrap-preflight-diagnostic.v1"
PREDECESSOR_SHA = "80261255b3be2aa7dd40986254d4ea478b4e2e1b"
ROOT_UID = 0

FAILURE_CODES = {
    "SOURCE_IDENTITY": frozenset({"SOURCE_IDENTITY_INVALID"}),
    "BOOTSTRAP_CAPABILITY": frozenset({"CAPABILITY_CLOSURE_INVALID"}),
    "PREDECESSOR_CONTRACT": frozenset({"CONTRACT_INVALID"}),
    "DURABLE_BASELINE": frozenset({
        "REGISTRATION_PRESENT", "STATE_DB_PRESENT", "STAGING_RESIDUE_PRESENT",
        "CONFIG_ROOT_METADATA_INVALID", "STATE_ROOT_METADATA_INVALID",
    }),
    "EXECUTION_PROVENANCE": frozenset({"EXECUTION_PROVENANCE_INVALID"}),
    "ARTIFACT_IDENTITY": frozenset({"ARTIFACT_IDENTITY_INVALID"}),
    "POSTCONDITION": frozenset({"CANONICAL_PREFLIGHT_REJECTED"}),
    "INTERNAL": frozenset({"UNCLASSIFIED"}),
}


class SafeDiagnosticFailure(RuntimeError):
    def __init__(self, stage: str, code: str):
        super().__init__("privacy-safe predecessor diagnostic failure")
        self.stage = stage
        self.code = code


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SafeDiagnosticFailure("INTERNAL", "UNCLASSIFIED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _failure(stage: str, code: str) -> dict[str, object]:
    allowed = FAILURE_CODES.get(stage)
    if allowed is None or code not in allowed:
        stage, code = "INTERNAL", "UNCLASSIFIED"
    return {
        "schema": SCHEMA,
        "result": "FAIL_CLOSED",
        "failure_stage": stage,
        "failure_code": code,
        "host_mutation_started": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def _contract() -> dict[str, object]:
    try:
        value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SafeDiagnosticFailure("PREDECESSOR_CONTRACT", "CONTRACT_INVALID") from exc
    expected = {stage: sorted(codes) for stage, codes in FAILURE_CODES.items()}
    if (
        value.get("schema") != "rozkalns.rpi5-main.weather-v9-predecessor-bootstrap-preflight-diagnostic-contract.v1"
        or value.get("issue") != 636
        or value.get("failure_codes") != expected
        or value.get("root_read_only") is not True
        or value.get("source_merge_authorizes_live") is not False
    ):
        raise SafeDiagnosticFailure("PREDECESSOR_CONTRACT", "CONTRACT_INVALID")
    return value


class CanonicalProbe:
    def __init__(self):
        self.installer = _load(INSTALLER_PATH, "weather_v9_predecessor_diag_installer")
        self.core = _load(CORE_PATH, "weather_v9_predecessor_diag_core")
        self.diagnostic_source_sha = ""
        self.registration = None
        self.recovery = None
        self.adapter = None

    def source_identity(self) -> None:
        if os.geteuid() != ROOT_UID:
            raise SafeDiagnosticFailure("SOURCE_IDENTITY", "SOURCE_IDENTITY_INVALID")
        try:
            sha, _manager, _uid, _gid = self.installer.source_identity()
        except Exception as exc:
            raise SafeDiagnosticFailure("SOURCE_IDENTITY", "SOURCE_IDENTITY_INVALID") from exc
        self.diagnostic_source_sha = sha

    def bootstrap_capability(self) -> None:
        try:
            self.registration = self.core.load_registration()
            self.recovery, self.adapter = self.core._recovery_and_adapter(self.registration)
        except Exception as exc:
            raise SafeDiagnosticFailure("BOOTSTRAP_CAPABILITY", "CAPABILITY_CLOSURE_INVALID") from exc

    def predecessor_contract(self) -> None:
        _contract()
        try:
            self.recovery._validate_contract(self.adapter)
        except Exception as exc:
            raise SafeDiagnosticFailure("PREDECESSOR_CONTRACT", "CONTRACT_INVALID") from exc

    def durable_baseline(self) -> None:
        recovery = self.recovery
        base = recovery.base
        if base._lstat_optional(recovery.REGISTRATION_PATH) is not None:
            raise SafeDiagnosticFailure("DURABLE_BASELINE", "REGISTRATION_PRESENT")
        if base._lstat_optional(recovery.STATE_DB_PATH) is not None:
            raise SafeDiagnosticFailure("DURABLE_BASELINE", "STATE_DB_PRESENT")
        if any(base._lstat_optional(path) is not None for path in recovery.KNOWN_STAGING_PATHS):
            raise SafeDiagnosticFailure("DURABLE_BASELINE", "STAGING_RESIDUE_PRESENT")
        try:
            base._require_root_directory(recovery.CONFIG_ROOT, 0o700)
        except Exception as exc:
            raise SafeDiagnosticFailure("DURABLE_BASELINE", "CONFIG_ROOT_METADATA_INVALID") from exc
        try:
            base._require_root_directory(recovery.STATE_ROOT, 0o700, allow_absent=True)
        except Exception as exc:
            raise SafeDiagnosticFailure("DURABLE_BASELINE", "STATE_ROOT_METADATA_INVALID") from exc

    def execution_provenance(self) -> None:
        try:
            sha = self.recovery._execution_source_sha(self.adapter)
            manager = Path(self.adapter.canonical_manager_checkout())
            uid, gid = self.adapter.manager_identity(manager)
            if sha != self.registration.source_sha or not manager.is_absolute() or manager.name != "RPi5_main":
                raise RuntimeError("bounded provenance mismatch")
            if type(uid) is not int or type(gid) is not int or uid <= 0 or gid <= 0:
                raise RuntimeError("bounded manager identity mismatch")
        except Exception as exc:
            raise SafeDiagnosticFailure("EXECUTION_PROVENANCE", "EXECUTION_PROVENANCE_INVALID") from exc

    def artifact_identity(self) -> None:
        recovery = self.recovery
        base = recovery.base
        try:
            manager = Path(self.adapter.canonical_manager_checkout())
            targets: set[Path] = set()
            for source, target, mode in self.adapter.ARTIFACTS:
                target = Path(target)
                if target in targets:
                    raise RuntimeError("duplicate bounded target")
                targets.add(target)
                expected = recovery._predecessor_installed_bytes(self.adapter, source, manager, int(mode))
                observed = base._safe_regular_bytes(target, mode=int(mode))
                if observed != expected:
                    raise RuntimeError("bounded artifact mismatch")
        except Exception as exc:
            raise SafeDiagnosticFailure("ARTIFACT_IDENTITY", "ARTIFACT_IDENTITY_INVALID") from exc

    def postcondition(self) -> None:
        try:
            result = self.recovery.preflight()
            if (
                type(result) is not dict
                or result.get("result") != "PASS"
                or result.get("execution_source_sha") != self.registration.source_sha
                or result.get("host_mutation_started") is not False
            ):
                raise RuntimeError("bounded canonical postcondition mismatch")
        except Exception as exc:
            raise SafeDiagnosticFailure("POSTCONDITION", "CANONICAL_PREFLIGHT_REJECTED") from exc


def diagnose(probe: Any | None = None) -> dict[str, object]:
    probe = CanonicalProbe() if probe is None else probe
    try:
        probe.source_identity()
        probe.bootstrap_capability()
        probe.predecessor_contract()
        probe.durable_baseline()
        probe.execution_provenance()
        probe.artifact_identity()
        probe.postcondition()
        return {
            "schema": SCHEMA,
            "result": "PASS",
            "diagnostic_source_sha": probe.diagnostic_source_sha,
            "execution_source_sha": probe.registration.source_sha,
            "predecessor_source_sha": PREDECESSOR_SHA,
            "host_mutation_started": False,
            "automatic_retry": False,
            "automatic_cleanup": False,
            "automatic_rollback": False,
        }
    except SafeDiagnosticFailure as exc:
        return _failure(exc.stage, exc.code)
    except Exception:
        return _failure("INTERNAL", "UNCLASSIFIED")


def main() -> int:
    if len(sys.argv) != 1:
        print(json.dumps(_failure("INTERNAL", "UNCLASSIFIED"), sort_keys=True, separators=(",", ":")))
        return 64
    result = diagnose()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("result") == "PASS" else 78


if __name__ == "__main__":
    raise SystemExit(main())
