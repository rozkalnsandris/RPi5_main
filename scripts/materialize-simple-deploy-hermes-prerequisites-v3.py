#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
V2_PATH = ROOT / "scripts/materialize-simple-deploy-hermes-prerequisites-v2.py"
SCRIPT_RELATIVE = "scripts/materialize-simple-deploy-hermes-prerequisites-v3.py"
CONTRACT_RELATIVE = "ops/contracts/simple-deploy-hermes-prerequisite-materialization-v3.json"
V2_SCRIPT_RELATIVE = "scripts/materialize-simple-deploy-hermes-prerequisites-v2.py"
V2_CONTRACT_RELATIVE = "ops/contracts/simple-deploy-hermes-prerequisite-materialization-v2.json"
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
GIT = Path("/usr/bin/git")
PUBLIC_SCHEMA = "rozkalns.rpi5-main.simple-deploy-hermes-prerequisite-preflight.v3"
SOURCE_ENV_KEYS = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "HTTP_USER_AGENT")
DESTINATION_ENV_KEYS = ("DATABASE_URL", "HTTP_USER_AGENT")
DATABASE_URL_TEMPLATE = "postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@db:5432/{POSTGRES_DB}"

spec = importlib.util.spec_from_file_location("simple_deploy_hermes_prerequisites_v2", V2_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("materialization v2 implementation could not be loaded")
v2 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v2
spec.loader.exec_module(v2)

legacy = v2.legacy
MaterializationPaths = v2.MaterializationPaths
MaterializationError = v2.MaterializationError
ApplyFailure = v2.ApplyFailure
Classification = v2.Classification
ProtectedPlan = v2.ProtectedPlan
Progress = v2.Progress
STATUS_ABSENT = v2.STATUS_ABSENT
STATUS_EXACT_READY = v2.STATUS_EXACT_READY
STATUS_PARTIAL_CONFLICT = v2.STATUS_PARTIAL_CONFLICT
STATUS_PRIVILEGED_METADATA_REQUIRED = v2.STATUS_PRIVILEGED_METADATA_REQUIRED
ROOT_UID = v2.ROOT_UID
SOURCE_USER = v2.SOURCE_USER


def _fail(message: str) -> None:
    raise MaterializationError(message)


def _git_readonly(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        (
            str(GIT),
            "--no-optional-locks",
            "-c",
            f"safe.directory={ROOT}",
            "-C",
            str(ROOT),
            *args,
        ),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
        env={
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "GIT_OPTIONAL_LOCKS": "0",
        },
    )


def _git_stdout_readonly(*args: str) -> bytes:
    result = _git_readonly(*args)
    if result.returncode != 0:
        _fail("Git source validation failed")
    return result.stdout


def _require_clean_source_checkout() -> None:
    for args in (
        ("diff-files", "--quiet", "--"),
        ("diff-index", "--cached", "--quiet", "HEAD", "--"),
    ):
        result = _git_readonly(*args)
        if result.returncode == 1:
            _fail("source checkout must be clean")
        if result.returncode != 0:
            _fail("Git source validation failed")
    if _git_stdout_readonly("ls-files", "--others", "--exclude-standard"):
        _fail("source checkout must be clean")


def _require_source_checkout(expected_sha: str) -> None:
    if legacy.FULL_SHA.fullmatch(expected_sha) is None:
        _fail("expected source SHA must be lowercase 40-character hex")
    head = _git_stdout_readonly("rev-parse", "--verify", "HEAD").decode("ascii").strip()
    if head != expected_sha:
        _fail("checkout HEAD does not match expected source SHA")
    origin = _git_stdout_readonly("remote", "get-url", "origin").decode("utf-8").strip()
    if origin != ORIGIN:
        _fail("checkout origin drifted")
    _require_clean_source_checkout()
    for relative in (
        SCRIPT_RELATIVE,
        CONTRACT_RELATIVE,
        V2_SCRIPT_RELATIVE,
        V2_CONTRACT_RELATIVE,
    ):
        tracked = _git_stdout_readonly("show", f"{expected_sha}:{relative}")
        if tracked != (ROOT / relative).read_bytes():
            _fail("reviewed materialization source differs from expected Git source")


def _decode_double_quoted(value: str, *, key: str) -> str:
    decoded: list[str] = []
    index = 0
    escapes = {'"': '"', "\\": "\\", "n": "\n", "r": "\r", "t": "\t"}
    while index < len(value):
        char = value[index]
        if char != "\\":
            decoded.append(char)
            index += 1
            continue
        index += 1
        if index >= len(value) or value[index] not in escapes:
            _fail(f"protected env source key {key} has unsupported escape syntax")
        decoded.append(escapes[value[index]])
        index += 1
    return "".join(decoded)


def _decode_source_value(raw_value: str, *, key: str) -> str:
    value = raw_value.strip()
    if not value:
        _fail(f"protected env source key {key} is empty")
    if value[0] in ("'", '"'):
        quote = value[0]
        if len(value) < 2 or value[-1] != quote:
            _fail(f"protected env source key {key} has malformed quoted value")
        inner = value[1:-1]
        decoded = inner if quote == "'" else _decode_double_quoted(inner, key=key)
    else:
        decoded = value
    if not decoded:
        _fail(f"protected env source key {key} is empty")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in decoded):
        _fail(f"protected env source key {key} contains an unsafe control character")
    if "'" in decoded:
        _fail(f"protected env source key {key} contains an unsupported quote")
    return decoded


def _extract_source_env(raw: bytes) -> dict[str, str]:
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise MaterializationError("protected env source is not valid UTF-8") from exc
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in line:
            _fail("protected env source contains malformed assignment syntax")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not legacy.ENV_KEY.fullmatch(key):
            _fail("protected env source contains malformed key syntax")
        if key not in SOURCE_ENV_KEYS:
            continue
        if key in values:
            _fail(f"protected env source duplicates required key {key}")
        values[key] = _decode_source_value(raw_value, key=key)
    missing = [key for key in SOURCE_ENV_KEYS if key not in values]
    if missing:
        _fail("protected env source is missing required key(s): " + ",".join(missing))
    return values


def _quote_destination_value(value: str, *, key: str) -> str:
    if "'" in value:
        _fail(f"protected env source key {key} cannot be safely projected")
    return f"'{value}'"


def _derive_destination_env(values: dict[str, str]) -> bytes:
    database_url = DATABASE_URL_TEMPLATE.format(**values)
    projected = (
        ("DATABASE_URL", database_url),
        ("HTTP_USER_AGENT", values["HTTP_USER_AGENT"]),
    )
    if tuple(key for key, _ in projected) != DESTINATION_ENV_KEYS:
        _fail("protected env destination projection order drifted")
    return "".join(
        f"{key}={_quote_destination_value(value, key=key)}\n"
        for key, value in projected
    ).encode("utf-8")


def _prepare_protected_v3(
    paths: MaterializationPaths, *, source_uid: int, source_gid: int
) -> ProtectedPlan:
    env_reason = legacy._source_reason(
        paths.source_env,
        kind="file",
        uid=source_uid,
        gid=source_gid,
        private=True,
    )
    if env_reason:
        raise MaterializationError(env_reason)
    source_values = _extract_source_env(legacy._read_regular_bytes_no_follow(paths.source_env))
    env_bytes = _derive_destination_env(source_values)
    data_digest, data_files = legacy._tree_digest(
        paths.source_data,
        expected_uid=source_uid,
        expected_gid=source_gid,
        protected_label="data",
    )
    config_digest, config_files = legacy._tree_digest(
        paths.source_config,
        expected_uid=source_uid,
        expected_gid=source_gid,
        protected_label="config",
    )
    return ProtectedPlan(data_digest, config_digest, env_bytes, data_files + config_files)


def _validate_machine_contract() -> None:
    v2._validate_machine_contract()
    try:
        contract = json.loads((ROOT / CONTRACT_RELATIVE).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MaterializationError("machine-readable materialization v3 contract is unavailable or invalid") from exc
    if contract.get("schema") != "rozkalns.rpi5-main.simple-deploy-hermes-prerequisite-materialization.v3":
        _fail("materialization v3 contract schema drifted")
    if contract.get("issue") != 719:
        _fail("materialization v3 recovery issue binding drifted")
    supersedes = contract.get("supersedes", {})
    if supersedes.get("materialization_v2_issue") != 713:
        _fail("materialization v3 predecessor issue binding drifted")
    if supersedes.get("materialization_v2_pr") != 714:
        _fail("materialization v3 predecessor PR binding drifted")
    private_env = contract.get("private_env", {})
    if tuple(private_env.get("source_required_keys", ())) != SOURCE_ENV_KEYS:
        _fail("materialization v3 protected source key set drifted")
    if tuple(private_env.get("destination_keys", ())) != DESTINATION_ENV_KEYS:
        _fail("materialization v3 destination key set drifted")
    if tuple(private_env.get("projection_order", ())) != DESTINATION_ENV_KEYS:
        _fail("materialization v3 destination projection order drifted")
    if private_env.get("database_url_template") != DATABASE_URL_TEMPLATE:
        _fail("materialization v3 DATABASE_URL derivation drifted")
    verification = contract.get("source_verification", {})
    if verification.get("git_optional_locks") is not False:
        _fail("materialization v3 Git optional-lock policy drifted")
    if verification.get("git_status_allowed") is not False:
        _fail("materialization v3 Git status policy drifted")
    if verification.get("clean_checks") != [
        "git diff-files --quiet --",
        "git diff-index --cached --quiet HEAD --",
        "git ls-files --others --exclude-standard",
    ]:
        _fail("materialization v3 clean-check contract drifted")
    if contract.get("materialization", {}).get("entrypoint") != SCRIPT_RELATIVE:
        _fail("materialization v3 entrypoint drifted")
    if contract.get("cli", {}).get("options") != ["--expected-source-sha", "--apply"]:
        _fail("materialization v3 CLI authority drifted")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed Hermes SIMPLE-DEPLOY host-prerequisite materialization v3 recovery"
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
        runtime_uid, runtime_gid = v2._runtime_ids()
        classification = v2._public_preflight(
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
        plan = _prepare_protected_v3(
            production_paths,
            source_uid=source_account.pw_uid,
            source_gid=source_account.pw_gid,
        )
        progress = v2._apply(
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