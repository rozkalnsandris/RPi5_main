#!/usr/bin/env python3
"""Source-only Hermes v4 metadata preflight. No protected reads or LIVE apply."""
from __future__ import annotations

import argparse
import grp
import importlib.util
import json
import os
from pathlib import Path
import pwd
import stat
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "scripts/materialize-simple-deploy-hermes-prerequisites-v3.py"
SCRIPT_RELATIVE = "scripts/materialize-simple-deploy-hermes-prerequisites-v4.py"
CONTRACT_RELATIVE = "ops/contracts/simple-deploy-hermes-prerequisite-materialization-v4.json"
PUBLIC_SCHEMA = "rozkalns.rpi5-main.hermes-prerequisite-preflight.v4"
RUNTIME_NAME = "rozkalns-simple-deployer"
PARENT_MODE = 0o750
CANDIDATE_CHILD_MODE = 0o640

spec = importlib.util.spec_from_file_location("hermes_materializer_v3_for_v4", V3)
if spec is None or spec.loader is None:
    raise RuntimeError("Hermes v3 source unavailable")
v3 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v3
spec.loader.exec_module(v3)
v2 = v3.v2
legacy = v2.legacy

STATUS_ABSENT = v2.STATUS_ABSENT
STATUS_EXACT_READY = v2.STATUS_EXACT_READY
STATUS_PARTIAL_CONFLICT = v2.STATUS_PARTIAL_CONFLICT
STATUS_PRIVILEGED_METADATA_REQUIRED = v2.STATUS_PRIVILEGED_METADATA_REQUIRED
MaterializationError = v3.MaterializationError
Classification = v3.Classification


def _exclusive_runtime_group(name: str, gid: int) -> bool:
    """Conservatively reject another local NSS primary or supplementary member.

    This is not proof of Compose's effective runtime credentials or remote NSS
    completeness. Even an affirmative result never authorizes LIVE.
    """
    try:
        group = grp.getgrgid(gid)
        users = pwd.getpwall()
    except (KeyError, OSError):
        return False
    if group.gr_name != RUNTIME_NAME:
        return False
    if set(group.gr_mem) - {name}:
        return False
    primary = {account.pw_name for account in users if account.pw_gid == gid}
    return primary == {name}


def _require_frozen_source(expected_sha: str) -> None:
    # V3 prohibits Git index refresh and uses --no-optional-locks.
    v3._require_source_checkout(expected_sha)
    for relative in (SCRIPT_RELATIVE, CONTRACT_RELATIVE):
        tracked = v3._git_stdout_readonly("show", f"{expected_sha}:{relative}")
        if tracked != (ROOT / relative).read_bytes():
            raise MaterializationError("v4 reviewed source identity drifted")


def _validate_contract() -> None:
    v3._validate_machine_contract()
    try:
        data = json.loads((ROOT / CONTRACT_RELATIVE).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise MaterializationError("v4 machine contract unavailable") from exc
    if (
        data.get("schema") != "rozkalns.rpi5-main.hermes-prerequisite-materialization.v4"
        or data.get("issue") != 958
        or data.get("status") != "SOURCE_ONLY_NO_APPLY_CONSUMER_ACCESS_UNPROVEN"
        or data.get("entrypoint") != SCRIPT_RELATIVE
        or data.get("parent") != {
            "path": str(legacy.PRIVATE_ROOT),
            "uid": "root",
            "gid": RUNTIME_NAME,
            "mode": "0750",
            "must_preexist": True,
            "may_create_reown_chmod_or_replace": False,
        }
        or data.get("candidate_child") != {
            "path": str(legacy.TARGET_ENV),
            "uid": "root",
            "gid": RUNTIME_NAME,
            "mode": "0640",
            "candidate_not_authorized": True,
        }
        or data.get("cli") != ["--expected-source-sha"]
        or data.get("activation_eligible") is not False
        or data.get("apply_available") is not False
        or data.get("group_exclusivity_required") is not True
        or data.get("authority") != {
            "apply": False, "merge": False, "live": False,
            "host": False, "docker": False, "permissions": False,
            "protected_data": False, "retry": False,
            "rollback": False, "cleanup": False,
        }
    ):
        raise MaterializationError("v4 machine contract drifted")


def _destination_reason(path: Path, *, kind: str, mode: int, uid: int, gid: int):
    return v2._destination_reason_or_privilege(
        path, kind=kind, mode=mode, uid=uid, gid=gid
    )


def _classify(
    paths: v2.MaterializationPaths,
    *,
    source_uid: int,
    source_gid: int,
    runtime_uid: int,
    runtime_gid: int,
    root_uid: int = 0,
    root_gid: int = 0,
) -> Classification:
    for path, kind, private in (
        (paths.checkout, "directory", False),
        (paths.source_data, "directory", False),
        (paths.source_config, "directory", False),
        (paths.source_env, "file", True),
    ):
        try:
            reason = legacy._source_reason(
                path, kind=kind, uid=source_uid, gid=source_gid, private=private
            )
        except PermissionError:
            return Classification(
                STATUS_PRIVILEGED_METADATA_REQUIRED, ("source metadata inaccessible",)
            )
        if reason:
            return Classification(STATUS_PARTIAL_CONFLICT, ("fixed source metadata drifted",))

    for path, mode, uid, gid in (
        (paths.etc_root, 0o755, root_uid, root_gid),
        (paths.state_parent, 0o700, runtime_uid, runtime_gid),
        (paths.private_root, PARENT_MODE, root_uid, runtime_gid),
    ):
        reason, privilege = _destination_reason(
            path, kind="directory", mode=mode, uid=uid, gid=gid
        )
        if privilege:
            return Classification(
                STATUS_PRIVILEGED_METADATA_REQUIRED, ("fixed parent inaccessible",)
            )
        if reason:
            return Classification(
                STATUS_PARTIAL_CONFLICT, ("fixed parent identity or mode drifted",)
            )

    if not _exclusive_runtime_group(RUNTIME_NAME, runtime_gid):
        return Classification(
            STATUS_PARTIAL_CONFLICT, ("runtime group identity or membership unverified",)
        )

    probes = (
        v2._probe(paths.state_stage),
        v2._probe(paths.env_stage),
        v2._probe(paths.target_root),
        v2._probe(paths.target_env),
    )
    if "INACCESSIBLE" in probes:
        return Classification(
            STATUS_PRIVILEGED_METADATA_REQUIRED, ("fixed child metadata inaccessible",)
        )
    state_stage, env_stage, root_probe, env_probe = probes
    if state_stage != "ABSENT" or env_stage != "ABSENT":
        return Classification(STATUS_PARTIAL_CONFLICT, ("unexpected staging path",))
    if root_probe == "ABSENT" and env_probe == "ABSENT":
        return Classification(STATUS_ABSENT, ())
    if root_probe != "PRESENT" or env_probe != "PRESENT":
        return Classification(STATUS_PARTIAL_CONFLICT, ("incomplete destination",))

    for path, kind, mode, uid, gid in (
        (paths.target_root, "directory", 0o755, root_uid, root_gid),
        (paths.target_data_parent, "directory", 0o755, root_uid, root_gid),
        (paths.target_data, "directory", 0o755, root_uid, root_gid),
        (paths.target_config, "directory", 0o755, root_uid, root_gid),
        (paths.target_env, "file", CANDIDATE_CHILD_MODE, root_uid, runtime_gid),
    ):
        reason, privilege = _destination_reason(
            path, kind=kind, mode=mode, uid=uid, gid=gid
        )
        if privilege:
            return Classification(
                STATUS_PRIVILEGED_METADATA_REQUIRED, ("fixed destination inaccessible",)
            )
        if reason:
            return Classification(
                STATUS_PARTIAL_CONFLICT, ("fixed destination identity or mode drifted",)
            )
    # Hard links are not an acceptable way of publishing a protected env child.
    try:
        env_metadata = os.lstat(paths.target_env)
    except PermissionError:
        return Classification(
            STATUS_PRIVILEGED_METADATA_REQUIRED, ("private child metadata inaccessible",)
        )
    except OSError:
        return Classification(STATUS_PARTIAL_CONFLICT, ("private child metadata unstable",))
    if not stat.S_ISREG(env_metadata.st_mode) or env_metadata.st_nlink != 1:
        return Classification(STATUS_PARTIAL_CONFLICT, ("private child link count drifted",))

    try:
        if legacy._directory_names(paths.target_root) != {"data", "config"}:
            return Classification(STATUS_PARTIAL_CONFLICT, ("state child shape drifted",))
        if legacy._directory_names(paths.target_data_parent) != {"raw"}:
            return Classification(STATUS_PARTIAL_CONFLICT, ("data child shape drifted",))
    except MaterializationError:
        return Classification(
            STATUS_PRIVILEGED_METADATA_REQUIRED, ("fixed child shape inaccessible",)
        )
    return Classification(STATUS_EXACT_READY, ())


def _public_result(result: Classification) -> dict[str, object]:
    return {
        "schema": PUBLIC_SCHEMA,
        "status": result.status,
        "reasons": list(result.reasons),
        "consumer_access": "NOT_PROVEN",
        "activation_eligible": False,
        "apply_available": False,
        "protected_content_read": False,
        "mutation_started": False,
        "protected_values_emitted": False,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hermes v4 metadata-only source preflight")
    parser.add_argument("--expected-source-sha", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        _require_frozen_source(args.expected_source_sha)
        _validate_contract()
        source = pwd.getpwnam(v3.SOURCE_USER)
        runtime_uid, runtime_gid = v2._runtime_ids()
        paths = legacy._production_paths(Path(source.pw_dir))
        result = _classify(
            paths, source_uid=source.pw_uid, source_gid=source.pw_gid,
            runtime_uid=runtime_uid, runtime_gid=runtime_gid,
        )
        print(json.dumps(_public_result(result), sort_keys=True, separators=(",", ":")))
        if result.status == STATUS_PRIVILEGED_METADATA_REQUIRED:
            return 5
        return 0 if result.status in (STATUS_ABSENT, STATUS_EXACT_READY) else 3
    except (MaterializationError, KeyError, OSError, UnicodeError, ValueError):
        print(json.dumps({
            "schema": PUBLIC_SCHEMA, "status": "ERROR",
            "activation_eligible": False, "apply_available": False,
            "protected_content_read": False,
            "protected_values_emitted": False, "mutation_started": False,
        }, sort_keys=True, separators=(",", ":")), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
