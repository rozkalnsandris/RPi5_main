#!/usr/bin/env python3
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
LEGACY_PATH = ROOT / "scripts/materialize-simple-deploy-hermes-prerequisites-v1.py"
CONTRACT_RELATIVE = "ops/contracts/simple-deploy-hermes-prerequisite-materialization-v2.json"
SCRIPT_RELATIVE = "scripts/materialize-simple-deploy-hermes-prerequisites-v2.py"
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
RUNTIME_USER = "rozkalns-simple-deployer"
RUNTIME_GROUP = "rozkalns-simple-deployer"
RUNTIME_HOME = "/var/lib/rozkalns-simple-deployer"
RUNTIME_SHELL = "/usr/sbin/nologin"
STATUS_PRIVILEGED_METADATA_REQUIRED = "PRIVILEGED_METADATA_REQUIRED"
PUBLIC_SCHEMA = "rozkalns.rpi5-main.simple-deploy-hermes-prerequisite-preflight.v2"

spec = importlib.util.spec_from_file_location("simple_deploy_hermes_prerequisites_v1", LEGACY_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("legacy materialization implementation could not be loaded")
legacy = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = legacy
spec.loader.exec_module(legacy)

MaterializationPaths = legacy.MaterializationPaths
MaterializationError = legacy.MaterializationError
ApplyFailure = legacy.ApplyFailure
Classification = legacy.Classification
ProtectedPlan = legacy.ProtectedPlan
Progress = legacy.Progress
STATUS_ABSENT = legacy.STATUS_ABSENT
STATUS_EXACT_READY = legacy.STATUS_EXACT_READY
STATUS_PARTIAL_CONFLICT = legacy.STATUS_PARTIAL_CONFLICT
ROOT_UID = legacy.ROOT_UID
ROOT_GID = legacy.ROOT_GID
SOURCE_USER = legacy.SOURCE_USER
REQUIRED_ENV_KEYS = legacy.REQUIRED_ENV_KEYS


def _fail(message: str) -> None:
    raise MaterializationError(message)


def _require_source_checkout(expected_sha: str) -> None:
    if legacy.FULL_SHA.fullmatch(expected_sha) is None:
        _fail("expected source SHA must be lowercase 40-character hex")
    head = legacy._git_stdout("rev-parse", "HEAD").decode("ascii").strip()
    if head != expected_sha:
        _fail("checkout HEAD does not match expected source SHA")
    origin = legacy._git_stdout("remote", "get-url", "origin").decode("utf-8").strip()
    if origin != ORIGIN:
        _fail("checkout origin drifted")
    if legacy._git_stdout("status", "--porcelain=v1", "--untracked-files=all"):
        _fail("source checkout must be clean")
    tracked = legacy._git_stdout("show", f"{expected_sha}:{SCRIPT_RELATIVE}")
    if tracked != Path(__file__).read_bytes():
        _fail("materialization v2 working-tree bytes differ from expected source")


def _runtime_ids() -> tuple[int, int]:
    try:
        user = pwd.getpwnam(RUNTIME_USER)
        primary = grp.getgrnam(RUNTIME_GROUP)
    except KeyError as exc:
        raise MaterializationError("fixed SIMPLE-DEPLOY runtime principal is absent") from exc
    if user.pw_gid != primary.gr_gid:
        _fail("fixed SIMPLE-DEPLOY runtime principal primary-group binding drifted")
    if user.pw_dir != RUNTIME_HOME or user.pw_shell != RUNTIME_SHELL:
        _fail("fixed SIMPLE-DEPLOY runtime principal metadata drifted")
    return user.pw_uid, primary.gr_gid


def _validate_machine_contract() -> None:
    legacy._validate_machine_contract()
    try:
        contract = json.loads((ROOT / CONTRACT_RELATIVE).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MaterializationError("machine-readable materialization v2 contract is unavailable or invalid") from exc
    if contract.get("schema") != "rozkalns.rpi5-main.simple-deploy-hermes-prerequisite-materialization.v2":
        _fail("materialization v2 contract schema drifted")
    if contract.get("issue") != 713:
        _fail("materialization v2 contract issue binding drifted")
    phase_b = contract.get("phase_b_state_parent", {})
    if phase_b != {
        "path": str(legacy.STATE_PARENT),
        "owner_user": RUNTIME_USER,
        "owner_group": RUNTIME_GROUP,
        "mode": "0700",
        "must_preexist": True,
        "materializer_may_create_or_reown": False,
    }:
        _fail("Phase-B state-parent contract drifted")
    if contract.get("supersedes", {}).get("materialization_v1_issue") != 711:
        _fail("materialization v2 supersession binding drifted")
    source = contract.get("source", {})
    if source.get("owner_user") != SOURCE_USER or source.get("home_resolution") != legacy.SOURCE_HOME_RESOLUTION:
        _fail("materialization v2 source identity drifted")
    if source.get("checkout_relative") != legacy.SOURCE_CHECKOUT_RELATIVE.as_posix():
        _fail("materialization v2 checkout identity drifted")
    if source.get("within_checkout") != {
        "data": legacy.SOURCE_DATA_RELATIVE.as_posix(),
        "config": legacy.SOURCE_CONFIG_RELATIVE.as_posix(),
        "private_env": legacy.SOURCE_ENV_RELATIVE.as_posix(),
    }:
        _fail("materialization v2 source-relative identities drifted")
    if contract.get("destination", {}).get("paths") != {
        "state_root": str(legacy.TARGET_ROOT),
        "data": str(legacy.TARGET_DATA),
        "config": str(legacy.TARGET_CONFIG),
        "private_env": str(legacy.TARGET_ENV),
    }:
        _fail("materialization v2 destination identities drifted")
    if contract.get("materialization", {}).get("entrypoint") != SCRIPT_RELATIVE:
        _fail("materialization v2 entrypoint drifted")
    if tuple(contract.get("classifier", {}).get("statuses", ())) != (
        STATUS_ABSENT,
        STATUS_EXACT_READY,
        STATUS_PARTIAL_CONFLICT,
        STATUS_PRIVILEGED_METADATA_REQUIRED,
    ):
        _fail("materialization v2 classifier statuses drifted")
    if tuple(contract.get("private_env", {}).get("required_keys", ())) != REQUIRED_ENV_KEYS:
        _fail("materialization v2 private key set drifted")
    if contract.get("cli", {}).get("options") != ["--expected-source-sha", "--apply"]:
        _fail("materialization v2 CLI authority drifted")


def _probe(path: Path) -> str:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return "ABSENT"
    except PermissionError:
        return "INACCESSIBLE"
    except OSError as exc:
        raise MaterializationError("fixed destination metadata probe failed") from exc
    return "PRESENT"


def _destination_reason_or_privilege(
    path: Path, *, kind: str, mode: int, uid: int, gid: int
) -> tuple[str | None, bool]:
    try:
        reason = legacy._destination_reason(path, kind=kind, mode=mode, uid=uid, gid=gid)
    except PermissionError:
        return None, True
    return reason, False


def _public_preflight(
    paths: MaterializationPaths,
    *,
    source_uid: int,
    source_gid: int,
    runtime_uid: int,
    runtime_gid: int,
    root_uid: int = ROOT_UID,
    root_gid: int = ROOT_GID,
) -> Classification:
    reasons: list[str] = []
    for path, kind, private in (
        (paths.checkout, "directory", False),
        (paths.source_data, "directory", False),
        (paths.source_config, "directory", False),
        (paths.source_env, "file", True),
    ):
        try:
            reason = legacy._source_reason(path, kind=kind, uid=source_uid, gid=source_gid, private=private)
        except PermissionError:
            reason = "required fixed source metadata is inaccessible"
        if reason:
            reasons.append(reason)

    etc_reason, etc_privileged = _destination_reason_or_privilege(
        paths.etc_root, kind="directory", mode=0o755, uid=root_uid, gid=root_gid
    )
    if etc_privileged:
        reasons.append("SIMPLE-DEPLOY etc root metadata is inaccessible")
    elif etc_reason:
        reasons.append("SIMPLE-DEPLOY etc root metadata drifted")

    state_parent_reason, state_parent_privileged = _destination_reason_or_privilege(
        paths.state_parent, kind="directory", mode=0o700, uid=runtime_uid, gid=runtime_gid
    )
    if state_parent_privileged:
        reasons.append("Phase-B state root metadata is inaccessible")
    elif state_parent_reason:
        reasons.append("Phase-B state root is absent or metadata drifted")

    if reasons:
        return Classification(STATUS_PARTIAL_CONFLICT, tuple(sorted(set(reasons))))

    env_stage_probe = _probe(paths.env_stage)
    env_probe = _probe(paths.target_env)
    private_root_probe = _probe(paths.private_root)
    for probe in (env_stage_probe, env_probe, private_root_probe):
        if probe == "INACCESSIBLE":
            return Classification(
                STATUS_PRIVILEGED_METADATA_REQUIRED,
                ("fixed private destination metadata requires privileged read-only inspection",),
            )

    state_stage_probe = _probe(paths.state_stage)
    root_probe = _probe(paths.target_root)
    if state_stage_probe == "INACCESSIBLE" or root_probe == "INACCESSIBLE":
        return Classification(
            STATUS_PRIVILEGED_METADATA_REQUIRED,
            ("Phase-B 0700 state root hides fixed child metadata from the current account",),
        )

    if state_stage_probe == "PRESENT" or env_stage_probe == "PRESENT":
        return Classification(
            STATUS_PARTIAL_CONFLICT, ("fixed staging path is unexpectedly present",)
        )

    root_present = root_probe == "PRESENT"
    env_present = env_probe == "PRESENT"

    if not root_present and not env_present:
        if private_root_probe == "PRESENT":
            private_reason, private_privileged = _destination_reason_or_privilege(
                paths.private_root, kind="directory", mode=0o700, uid=root_uid, gid=root_gid
            )
            if private_privileged:
                return Classification(
                    STATUS_PRIVILEGED_METADATA_REQUIRED,
                    ("fixed private destination metadata requires privileged read-only inspection",),
                )
            if private_reason:
                return Classification(
                    STATUS_PARTIAL_CONFLICT, ("fixed private parent directory metadata drifted",)
                )
        return Classification(STATUS_ABSENT, ())

    if not root_present or not env_present:
        return Classification(
            STATUS_PARTIAL_CONFLICT,
            ("only part of the fixed prerequisite destination exists",),
        )

    for path, kind, expected_mode in (
        (paths.target_root, "directory", 0o755),
        (paths.target_data_parent, "directory", 0o755),
        (paths.target_data, "directory", 0o755),
        (paths.target_config, "directory", 0o755),
        (paths.private_root, "directory", 0o700),
        (paths.target_env, "file", 0o600),
    ):
        reason, privileged = _destination_reason_or_privilege(
            path, kind=kind, mode=expected_mode, uid=root_uid, gid=root_gid
        )
        if privileged:
            return Classification(
                STATUS_PRIVILEGED_METADATA_REQUIRED,
                ("fixed destination metadata requires privileged read-only inspection",),
            )
        if reason:
            reasons.append(reason)

    if not reasons:
        try:
            if legacy._directory_names(paths.target_root) != {"data", "config"}:
                reasons.append("fixed state root contains unexpected top-level entries")
            if legacy._directory_names(paths.target_data_parent) != {"raw"}:
                reasons.append("fixed data parent contains unexpected top-level entries")
        except MaterializationError:
            return Classification(
                STATUS_PRIVILEGED_METADATA_REQUIRED,
                ("fixed destination shape requires privileged read-only inspection",),
            )
    if reasons:
        return Classification(STATUS_PARTIAL_CONFLICT, tuple(sorted(set(reasons))))
    return Classification(STATUS_EXACT_READY, ())


def _apply(
    paths: MaterializationPaths,
    plan: ProtectedPlan,
    *,
    source_uid: int,
    source_gid: int,
    runtime_uid: int,
    runtime_gid: int,
    root_uid: int = ROOT_UID,
    root_gid: int = ROOT_GID,
) -> Progress:
    classification = _public_preflight(
        paths,
        source_uid=source_uid,
        source_gid=source_gid,
        runtime_uid=runtime_uid,
        runtime_gid=runtime_gid,
        root_uid=root_uid,
        root_gid=root_gid,
    )
    if classification.status != STATUS_ABSENT:
        _fail("apply requires exact privileged ABSENT prerequisite destination state")

    state_parent_reason, privileged = _destination_reason_or_privilege(
        paths.state_parent, kind="directory", mode=0o700, uid=runtime_uid, gid=runtime_gid
    )
    if privileged or state_parent_reason:
        _fail("canonical Phase-B state root must preexist with exact runtime ownership and mode")

    progress = Progress()
    try:
        legacy._ensure_directory(
            paths.private_root,
            mode=0o700,
            uid=root_uid,
            gid=root_gid,
            progress=progress,
            parent=True,
        )
        legacy._ensure_directory(
            paths.state_stage,
            mode=0o700,
            uid=root_uid,
            gid=root_gid,
            progress=progress,
        )
        stage_data_parent = paths.state_stage / "data"
        legacy._ensure_directory(
            stage_data_parent,
            mode=0o755,
            uid=root_uid,
            gid=root_gid,
            progress=progress,
        )
        legacy._copy_tree(
            paths.source_data,
            stage_data_parent / "raw",
            source_uid=source_uid,
            source_gid=source_gid,
            root_uid=root_uid,
            root_gid=root_gid,
            progress=progress,
        )
        legacy._copy_tree(
            paths.source_config,
            paths.state_stage / "config",
            source_uid=source_uid,
            source_gid=source_gid,
            root_uid=root_uid,
            root_gid=root_gid,
            progress=progress,
        )
        os.chown(paths.state_stage, root_uid, root_gid)
        os.chmod(paths.state_stage, 0o755)
        legacy._write_env_stage(
            paths.env_stage, plan.env_bytes, uid=root_uid, gid=root_gid, progress=progress
        )
        if _probe(paths.target_root) != "ABSENT" or _probe(paths.target_env) != "ABSENT":
            raise ApplyFailure("fixed final prerequisite destination appeared after preflight", progress)

        staged_data, _ = legacy._tree_digest(
            stage_data_parent / "raw",
            expected_uid=root_uid,
            expected_gid=root_gid,
            protected_label="staged data",
            normalized=True,
        )
        staged_config, _ = legacy._tree_digest(
            paths.state_stage / "config",
            expected_uid=root_uid,
            expected_gid=root_gid,
            protected_label="staged config",
            normalized=True,
        )
        if staged_data != plan.source_data_digest or staged_config != plan.source_config_digest:
            raise ApplyFailure("staged protected tree verification failed", progress)
        if legacy._read_regular_bytes_no_follow(paths.env_stage) != plan.env_bytes:
            raise ApplyFailure("staged private env verification failed", progress)

        os.rename(paths.state_stage, paths.target_root)
        progress.published_targets += 1
        legacy._fsync_dir(paths.state_parent, progress)
        os.link(paths.env_stage, paths.target_env, follow_symlinks=False)
        progress.published_targets += 1
        legacy._fsync_dir(paths.private_root, progress)
        os.unlink(paths.env_stage)
        legacy._fsync_dir(paths.private_root, progress)

        final = _public_preflight(
            paths,
            source_uid=source_uid,
            source_gid=source_gid,
            runtime_uid=runtime_uid,
            runtime_gid=runtime_gid,
            root_uid=root_uid,
            root_gid=root_gid,
        )
        if final.status != STATUS_EXACT_READY:
            raise ApplyFailure("public-safe postcondition did not reach EXACT_READY", progress)
        legacy._verify_exact_ready_protected(
            paths, plan, root_uid=root_uid, root_gid=root_gid
        )
        if _probe(paths.state_stage) != "ABSENT" or _probe(paths.env_stage) != "ABSENT":
            raise ApplyFailure("staging postcondition failed", progress)
    except ApplyFailure:
        raise
    except MaterializationError as exc:
        raise ApplyFailure(str(exc), progress) from exc
    except OSError as exc:
        raise ApplyFailure("materialization failed after mutation began", progress) from exc
    return progress


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed Hermes SIMPLE-DEPLOY host-prerequisite materialization v2"
    )
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--apply", action="store_true")
    return parser


def _public_result(classification: Classification) -> dict[str, object]:
    return {
        "schema": PUBLIC_SCHEMA,
        "status": classification.status,
        "reasons": list(classification.reasons),
        "mutation_started": False,
        "protected_data_read": False,
        "protected_values_emitted": False,
        "privileged_metadata_required": (
            classification.status == STATUS_PRIVILEGED_METADATA_REQUIRED
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        _require_source_checkout(args.expected_source_sha)
        _validate_machine_contract()
        try:
            source_account = pwd.getpwnam(SOURCE_USER)
        except KeyError as exc:
            raise MaterializationError("fixed source owner account is absent") from exc
        production_paths = legacy._production_paths(Path(source_account.pw_dir))
        runtime_uid, runtime_gid = _runtime_ids()
        classification = _public_preflight(
            production_paths,
            source_uid=source_account.pw_uid,
            source_gid=source_account.pw_gid,
            runtime_uid=runtime_uid,
            runtime_gid=runtime_gid,
        )
        if not args.apply:
            print(json.dumps(_public_result(classification), sort_keys=True, separators=(",", ":")))
            if classification.status in (STATUS_ABSENT, STATUS_EXACT_READY):
                return 0
            if classification.status == STATUS_PRIVILEGED_METADATA_REQUIRED:
                return 5
            return 3

        if os.geteuid() != ROOT_UID:
            _fail("--apply requires root and a separate exact LIVE authorization")
        if classification.status != STATUS_ABSENT:
            _fail("protected apply is blocked unless privileged metadata preflight is exact ABSENT")
        plan = legacy._prepare_protected(
            production_paths,
            source_uid=source_account.pw_uid,
            source_gid=source_account.pw_gid,
        )
        progress = _apply(
            production_paths,
            plan,
            source_uid=source_account.pw_uid,
            source_gid=source_account.pw_gid,
            runtime_uid=runtime_uid,
            runtime_gid=runtime_gid,
        )
        print(
            json.dumps(
                {
                    "schema": PUBLIC_SCHEMA,
                    "status": STATUS_EXACT_READY,
                    "mutation_started": progress.mutation_started,
                    "parent_directories_created": progress.parent_directories_created,
                    "staged_directories_created": progress.staged_directories_created,
                    "staged_files_created": progress.staged_files_created,
                    "published_targets": progress.published_targets,
                    "protected_values_emitted": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except ApplyFailure as exc:
        print(
            json.dumps(
                {
                    "schema": PUBLIC_SCHEMA,
                    "status": "ERROR",
                    "error": str(exc),
                    "mutation_started": exc.progress.mutation_started,
                    "published_targets": exc.progress.published_targets,
                    "protected_values_emitted": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 4
    except MaterializationError as exc:
        print(
            json.dumps(
                {
                    "schema": PUBLIC_SCHEMA,
                    "status": "ERROR",
                    "error": str(exc),
                    "mutation_started": False,
                    "protected_values_emitted": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
