#!/usr/bin/env python3
from __future__ import annotations

import argparse
import grp
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
from typing import Any, Mapping, Sequence

GIT = Path("/usr/bin/git")
SYSTEMCTL = Path("/usr/bin/systemctl")
ROOT = Path(__file__).resolve().parents[1]
SCRIPT_RELATIVE = "scripts/preflight-hermes-deals-origin-runtime-prerequisites.py"
BROKER_INSTALLER_MANIFEST = ROOT / "ops/deploy/hermes-deals-origin-broker-installer.json"
IMMUTABLE_IMPLEMENTATION_BASELINE = "2550e77f6cb811ca6f10b49ef0b2fef554d64869"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ROOT_UID = 0
ROOT_GID = 0

CREDENTIAL = Path("/etc/rozkalns-hermes-deals-origin-broker/source-github-app.pem")
STATE_DB = Path("/var/lib/rozkalns-deploy-executor-p9/state.sqlite3")
REGISTRATION = Path("/etc/hermes-deals-audits.d/origin-path-rpi5-pull.json")
HELPER = Path("/usr/local/sbin/hermes-deals-origin-path-rpi5-pull-dispatch")
PROBE = Path("/usr/local/libexec/hermes-deals-audits/origin-path-probe.py")
EVIDENCE_ROOT = Path("/var/lib/hermes-deals-audits/origin-path-audit/evidence")
MACHINE_ROOT = EVIDENCE_ROOT / "rpi5"
SOCKET_UNIT = "rozkalns-hermes-deals-origin-broker.socket"
SOCKET_PATH = Path("/run/rozkalns-hermes-deals-origin-broker/request.sock")
REGISTRATION_SCHEMA = "rozkalns.hermes-deals.origin-path-rpi5-pull-registration.v1"
CAPABILITY = "origin-path-audit"
REVIEWED_HERMES_SOURCE_SHA = "f6c48cc85c187d927575da6efef4b05b4d4c0e40"
HELPER_GIT_BLOB = "4ef95c3f02b810b6b25721aa1b1b53d43b8ca572"
PROBE_GIT_BLOB = "2362e8eb578a7279c38fe4ed2a7d1edd05df891a"
MAX_REGISTRATION_BYTES = 4096
MAX_CODE_BYTES = 2 * 1024 * 1024
REGISTRATION_FIELDS = frozenset(
    {"schema", "capability", "registered_source_sha", "helper_sha256", "probe_sha256"}
)

class RuntimePreflightError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise RuntimePreflightError(message)


def _run(argv: Sequence[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        tuple(argv), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, shell=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return _run((str(GIT), "-c", f"safe.directory={ROOT}", "-C", str(ROOT), *args))


def _git_stdout(*args: str) -> bytes:
    result = _git(*args)
    if result.returncode != 0:
        _fail("reviewed Git source validation failed")
    return result.stdout


def _git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _require_exact_checkout(expected_sha: str) -> None:
    if FULL_SHA.fullmatch(expected_sha) is None:
        _fail("expected source SHA must be lowercase 40-character hex")
    if _git_stdout("rev-parse", "HEAD").decode("ascii").strip() != expected_sha:
        _fail("checkout HEAD does not match expected source SHA")
    if _git("merge-base", "--is-ancestor", IMMUTABLE_IMPLEMENTATION_BASELINE, expected_sha).returncode != 0:
        _fail("expected source SHA is not descended from the immutable implementation baseline")
    if _git_stdout("show", f"{expected_sha}:{SCRIPT_RELATIVE}") != Path(__file__).read_bytes():
        _fail("runtime preflight source differs from expected source SHA")
    if _git("status", "--porcelain").stdout:
        _fail("trusted checkout is not clean")


def _require_root() -> None:
    if os.geteuid() != ROOT_UID:
        _fail("runtime prerequisite preflight requires root read context")


def _require_file_metadata(path: Path, *, mode: int, uid: int | None = None, gid: int | None = None) -> os.stat_result:
    uid = ROOT_UID if uid is None else uid
    gid = ROOT_GID if gid is None else gid
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        _fail(f"required file is absent: {path}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        _fail(f"required path is not a regular non-symlink file: {path}")
    if info.st_uid != uid or info.st_gid != gid:
        _fail(f"required file ownership drifted: {path}")
    if stat.S_IMODE(info.st_mode) != mode:
        _fail(f"required file mode drifted: {path}")
    if info.st_nlink != 1:
        _fail(f"required file link count drifted: {path}")
    return info


def _require_directory_metadata(path: Path, *, mode: int, uid: int | None = None, gid: int | None = None) -> os.stat_result:
    uid = ROOT_UID if uid is None else uid
    gid = ROOT_GID if gid is None else gid
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        _fail(f"required directory is absent: {path}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        _fail(f"required path is not a real directory: {path}")
    if info.st_uid != uid or info.st_gid != gid or stat.S_IMODE(info.st_mode) != mode:
        _fail(f"required directory metadata drifted: {path}")
    return info


def _read_descriptor_safe(path: Path, *, maximum: int) -> bytes:
    for name in ("O_NOFOLLOW", "O_CLOEXEC"):
        if not hasattr(os, name):
            _fail(f"required read guard is unavailable: {name}")
    before = os.lstat(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            _fail(f"file identity changed while opening: {path}")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining > 0:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > maximum:
            _fail(f"required file exceeds reviewed size bound: {path}")
        now = os.stat(path, follow_symlinks=False)
        if (now.st_dev, now.st_ino) != (opened.st_dev, opened.st_ino):
            _fail(f"file identity changed during read: {path}")
        return data
    finally:
        os.close(fd)


def _strict_json(raw: bytes) -> Any:
    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail(f"duplicate JSON field is forbidden: {key}")
            result[key] = value
        return result
    try:
        return json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=reject_pairs,
                          parse_constant=lambda value: _fail(f"non-finite JSON value is forbidden: {value}"))
    except RuntimePreflightError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
        _fail("runtime prerequisite JSON is invalid")


def _load_broker_manifest(expected_sha: str) -> Mapping[str, Any]:
    raw = _git_stdout("show", f"{expected_sha}:ops/deploy/hermes-deals-origin-broker-installer.json")
    value = _strict_json(raw)
    if type(value) is not dict:
        _fail("broker installer manifest is not an object")
    return value


def _verify_broker_targets(expected_sha: str) -> int:
    manifest = _load_broker_manifest(expected_sha)
    rows = list(manifest.get("install_targets", [])) + list(manifest.get("shared_prerequisites", []))
    if len(rows) != 10:
        _fail("broker runtime identity set must contain nine owned targets plus one shared prerequisite")
    for row in rows:
        if type(row) is not dict:
            _fail("broker runtime target row is invalid")
        source = row.get("source")
        target = row.get("target")
        blob = row.get("source_blob")
        mode_text = row.get("mode")
        if not all(type(item) is str for item in (source, target, blob, mode_text)):
            _fail("broker runtime target identity is incomplete")
        source_bytes = _git_stdout("show", f"{expected_sha}:{source}")
        if _git_blob(source_bytes) != blob:
            _fail(f"frozen source blob drifted: {source}")
        mode = int(mode_text, 8)
        path = Path(target)
        _require_file_metadata(path, mode=mode)
        installed = _read_descriptor_safe(path, maximum=len(source_bytes))
        if installed != source_bytes or _git_blob(installed) != blob:
            _fail(f"installed broker prerequisite differs from reviewed source: {path}")
    return len(rows)


def _credential_metadata() -> None:
    # Deliberately metadata-only: do not open/read the private key here.
    _require_directory_metadata(CREDENTIAL.parent, mode=0o700)
    _require_file_metadata(CREDENTIAL, mode=0o600)


def _registration_and_helper() -> str:
    _require_file_metadata(REGISTRATION, mode=0o600)
    registration = _strict_json(_read_descriptor_safe(REGISTRATION, maximum=MAX_REGISTRATION_BYTES))
    if type(registration) is not dict or frozenset(registration) != REGISTRATION_FIELDS:
        _fail("Hermes origin registration fields drifted")
    if registration.get("schema") != REGISTRATION_SCHEMA or registration.get("capability") != CAPABILITY:
        _fail("Hermes origin registration identity drifted")
    source_sha = registration.get("registered_source_sha")
    if type(source_sha) is not str or FULL_SHA.fullmatch(source_sha) is None:
        _fail("registered Hermes source SHA is invalid")
    if source_sha != REVIEWED_HERMES_SOURCE_SHA:
        _fail("registered Hermes source SHA differs from corrected reviewed source")
    helper_sha256 = registration.get("helper_sha256")
    probe_sha256 = registration.get("probe_sha256")
    if type(helper_sha256) is not str or SHA256.fullmatch(helper_sha256) is None:
        _fail("registered helper SHA-256 is invalid")
    if type(probe_sha256) is not str or SHA256.fullmatch(probe_sha256) is None:
        _fail("registered probe SHA-256 is invalid")
    for path, expected_sha256, expected_blob in (
        (HELPER, helper_sha256, HELPER_GIT_BLOB),
        (PROBE, probe_sha256, PROBE_GIT_BLOB),
    ):
        _require_file_metadata(path, mode=0o755)
        raw = _read_descriptor_safe(path, maximum=MAX_CODE_BYTES)
        if hashlib.sha256(raw).hexdigest() != expected_sha256 or _git_blob(raw) != expected_blob:
            _fail(f"Hermes helper/probe identity drifted: {path}")
    _require_directory_metadata(EVIDENCE_ROOT, mode=0o700)
    _require_directory_metadata(MACHINE_ROOT, mode=0o700)
    return source_sha


def _verify_state_db() -> None:
    _require_directory_metadata(STATE_DB.parent, mode=0o700)
    _require_file_metadata(STATE_DB, mode=0o600)
    wal = Path(str(STATE_DB) + "-wal")
    if wal.exists() and wal.stat().st_size > 0:
        _fail("durable replay database has a live WAL; immutable read-only verification would be incomplete")
    uri = f"file:{STATE_DB}?mode=ro&immutable=1"
    try:
        db = sqlite3.connect(uri, uri=True, timeout=1.0, isolation_level=None)
        db.execute("PRAGMA query_only = ON")
        quick = db.execute("PRAGMA quick_check").fetchone()
        application_id = db.execute("PRAGMA application_id").fetchone()[0]
        version = db.execute("PRAGMA user_version").fetchone()[0]
        columns = tuple(
            (row[1], row[2], row[3], row[5])
            for row in db.execute("PRAGMA table_info(requests)").fetchall()
        )
        indexes = db.execute("PRAGMA index_list(requests)").fetchall()
        unique_request_id = False
        for row in indexes:
            if row[2] != 1:
                continue
            name = str(row[1]).replace("'", "''")
            columns_for_index = [
                item[2] for item in db.execute(f"PRAGMA index_info('{name}')").fetchall()
            ]
            if columns_for_index == ["request_id"]:
                unique_request_id = True
                break
    except sqlite3.DatabaseError:
        _fail("durable replay database failed immutable read-only integrity verification")
    finally:
        try:
            db.close()
        except UnboundLocalError:
            pass
    expected_columns = (
        ("repository_id", "INTEGER", 1, 1), ("issue_id", "INTEGER", 1, 2),
        ("request_id", "TEXT", 1, 0), ("canonical_payload_sha256", "TEXT", 1, 0),
        ("raw_body_sha256", "TEXT", 1, 0), ("state", "TEXT", 1, 0),
        ("created_at", "TEXT", 1, 0), ("updated_at", "TEXT", 1, 0),
        ("consumed_at", "TEXT", 0, 0),
    )
    if quick != ("ok",) or application_id != 1381647448 or version != 1 or columns != expected_columns:
        _fail("durable replay database schema/integrity drifted")
    if not unique_request_id:
        _fail("durable replay database request_id uniqueness constraint is missing")


def _systemctl_query(*args: str) -> subprocess.CompletedProcess[bytes]:
    allowed = {
        ("is-enabled", SOCKET_UNIT), ("is-active", SOCKET_UNIT),
        ("show", SOCKET_UNIT, "--property=SubState", "--value"),
        ("show", SOCKET_UNIT, "--property=FragmentPath", "--value"),
    }
    if tuple(args) not in allowed:
        _fail("systemctl query is outside the fixed runtime preflight allowlist")
    return _run((str(SYSTEMCTL), *args), cwd=Path("/"))


def _verify_socket() -> None:
    enabled = _systemctl_query("is-enabled", SOCKET_UNIT)
    active = _systemctl_query("is-active", SOCKET_UNIT)
    if enabled.returncode != 0 or enabled.stdout.strip() != b"enabled":
        _fail("Hermes broker socket is not enabled")
    if active.returncode != 0 or active.stdout.strip() != b"active":
        _fail("Hermes broker socket is not active")
    substate = _systemctl_query("show", SOCKET_UNIT, "--property=SubState", "--value")
    fragment = _systemctl_query("show", SOCKET_UNIT, "--property=FragmentPath", "--value")
    if substate.returncode != 0 or substate.stdout.strip() != b"listening":
        _fail("Hermes broker socket is not listening")
    if fragment.returncode != 0 or fragment.stdout.decode("utf-8", "strict").strip() != "/etc/systemd/system/rozkalns-hermes-deals-origin-broker.socket":
        _fail("Hermes broker socket fragment identity drifted")
    try:
        socket_info = os.lstat(SOCKET_PATH)
    except FileNotFoundError:
        _fail("Hermes broker UNIX socket path is absent")
    if not stat.S_ISSOCK(socket_info.st_mode):
        _fail("Hermes broker UNIX socket path is not a socket")
    try:
        socket_gid = grp.getgrnam("rozkalns-deploy-executor").gr_gid
    except KeyError:
        _fail("Hermes broker socket group is absent")
    if socket_info.st_uid != ROOT_UID or socket_info.st_gid != socket_gid or stat.S_IMODE(socket_info.st_mode) != 0o660:
        _fail("Hermes broker UNIX socket metadata drifted")


def _receipt(*, result: str, source_sha: str, state: Mapping[str, bool] | None = None,
             registration_source_sha: str | None = None, reason: str | None = None) -> str:
    state = dict(state or {})
    value: dict[str, Any] = {
        "schema": "rozkalns.hermes-deals.origin-runtime-prerequisite-preflight.v1",
        "result": result,
        "source_sha": source_sha,
        "registration_source_sha": registration_source_sha,
        "credential_metadata_proven": state.get("credential_metadata_proven", False),
        "credential_content_read": False,
        "github_api_request": False,
        "source_app_installation_scope_proven": False,
        "durable_replay_store_proven": state.get("durable_replay_store_proven", False),
        "local_host_identities_proven": state.get("local_host_identities_proven", False),
        "systemd_query_performed": state.get("systemd_query_performed", False),
        "durable_replay_adapter_runtime_proven": False,
        "host_observation_adapter_runtime_proven": False,
        "broker_entrypoint_wired": False,
        "privileged_dispatch_enabled": False,
        "helper_executed": False,
        "socket_request_sent": False,
        "filesystem_mutation": False,
        "systemd_mutation": False,
        "production_mutation_started": False,
        "genuine_audit_authorized": False,
    }
    if reason is not None:
        value["reason"] = reason
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only Hermes origin runtime prerequisite preflight")
    parser.add_argument("expected_source_sha")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_sha = args.expected_source_sha
    _require_root()
    _require_exact_checkout(source_sha)
    state = {
        "credential_metadata_proven": False,
        "durable_replay_store_proven": False,
        "local_host_identities_proven": False,
        "systemd_query_performed": False,
    }
    _credential_metadata()
    state["credential_metadata_proven"] = True
    _verify_broker_targets(source_sha)
    _verify_state_db()
    state["durable_replay_store_proven"] = True
    registration_source_sha = _registration_and_helper()
    _verify_socket()
    state["systemd_query_performed"] = True
    state["local_host_identities_proven"] = True
    print(_receipt(
        result="HERMES_ORIGIN_RUNTIME_PREFLIGHT_PARTIAL_READY",
        source_sha=source_sha, state=state, registration_source_sha=registration_source_sha,
    ))
    return 0


if __name__ == "__main__":
    source_sha = sys.argv[1] if len(sys.argv) > 1 else "UNRESOLVED"
    try:
        raise SystemExit(main())
    except RuntimePreflightError as exc:
        print(_receipt(result="FAIL_CLOSED", source_sha=source_sha, reason=str(exc)), file=sys.stderr)
        raise SystemExit(1)
