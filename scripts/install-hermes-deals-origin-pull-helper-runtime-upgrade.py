#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Sequence

GIT = Path('/usr/bin/git')
ROOT = Path(__file__).resolve().parents[1]
SCRIPT_RELATIVE = 'scripts/install-hermes-deals-origin-pull-helper-runtime-upgrade.py'
FULL_SHA = re.compile(r'^[0-9a-f]{40}$')
ROOT_UID = 0
ROOT_GID = 0
HERMES_SOURCE_ROOT = ROOT.parent / 'hermes-deals-origin-pull-trusted'
HERMES_ORIGIN = 'https://github.com/rozkalnsandris/hermes-deals.git'
HERMES_SOURCE_SHA = 'f6c48cc85c187d927575da6efef4b05b4d4c0e40'
HELPER_SOURCE = 'tools/runner/origin_path_rpi5_pull_helper.py'
PROBE_SOURCE = 'tools/hermes_deals_origin_probe.py'
HELPER_OLD_BLOB = '51bb23cc6c2083ab7c8b4e81ba82dd880e46d673'
HELPER_NEW_BLOB = '4ef95c3f02b810b6b25721aa1b1b53d43b8ca572'
HELPER_OLD_SHA256 = 'f2f6e4ca823eb6c0872de0a5e92531ebacb076c48934c80654d84f3ef6f7e625'
HELPER_NEW_SHA256 = '23b29ff5f800cc5ade9cc8e38607a4e37beae9f45c6c82111ea4b49f063e06cf'
PROBE_BLOB = '2362e8eb578a7279c38fe4ed2a7d1edd05df891a'
PROBE_SHA256 = '96a8b5819ec85f27095c535f1a3be6cba7bac0e2a40a1132869fb39dc669ad43'
REGISTRATION_SCHEMA = 'rozkalns.hermes-deals.origin-path-rpi5-pull-registration.v1'
CAPABILITY = 'origin-path-audit'
REGISTRATION_OLD_BLOB = 'eac8778b2c09e191ca2d3abac3a4f5e243cd41c3'
REGISTRATION_NEW_BLOB = 'a0444a84cb1a54abfeaefb47baf7f0c41b9677d8'
REGISTRATION_OLD_SHA256 = 'b92564a93d67098c9ec264e88d48096ae1323430547ed14b6d22b590ac8591bc'
REGISTRATION_NEW_SHA256 = '36c511a36e462bf196a6695c4bac39497c56ab9ef7749aa0b2eb4621e172cad7'


class UpgradeError(RuntimeError):
    pass


@dataclass(frozen=True)
class TargetSpec:
    name: str
    path: Path
    mode: int
    old_blob: str
    new_blob: str
    temp_name: str
    source_path: str | None = None
    old_sha256: str | None = None
    new_sha256: str | None = None


CONSUMER_TARGETS = (
    TargetSpec(
        'consumer_adapter',
        Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_adapter.py'),
        0o644, '0b20cefa0c9193ecb8e7811c855767d56baf59ce',
        '03d2d250d7da9a235f0d6150e799dc85a5796ff1',
        '.hermes_deals_origin_adapter.py.loopback-upgrade.tmp',
        'ops/lib/deploy_executor/hermes_deals_origin_adapter.py',
    ),
    TargetSpec(
        'runtime_adapters',
        Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_runtime_adapters.py'),
        0o644, '21918e96495592b6a3478e8e74ae06fdf640121d',
        '862946e500749036a641c0ed3dcc66445dcdf23a',
        '.hermes_deals_origin_runtime_adapters.py.loopback-upgrade.tmp',
        'ops/lib/deploy_executor/hermes_deals_origin_runtime_adapters.py',
    ),
    TargetSpec(
        'broker_runtime',
        Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_broker_runtime.py'),
        0o644, '53112450cbccbabd9a5ec62966b9fd96d3513bea',
        'e1d4c1d8af780eca5d33ba5806cd66adecb33c81',
        '.hermes_deals_origin_broker_runtime.py.loopback-upgrade.tmp',
        'ops/lib/deploy_executor/hermes_deals_origin_broker_runtime.py',
    ),
)
HELPER_TARGET = TargetSpec(
    'helper', Path('/usr/local/sbin/hermes-deals-origin-path-rpi5-pull-dispatch'),
    0o755, HELPER_OLD_BLOB, HELPER_NEW_BLOB,
    '.hermes-deals-origin-path-rpi5-pull-dispatch.loopback-upgrade.tmp',
    old_sha256=HELPER_OLD_SHA256, new_sha256=HELPER_NEW_SHA256,
)
REGISTRATION_TARGET = TargetSpec(
    'registration', Path('/etc/hermes-deals-audits.d/origin-path-rpi5-pull.json'),
    0o600, REGISTRATION_OLD_BLOB, REGISTRATION_NEW_BLOB,
    '.origin-path-rpi5-pull.json.loopback-upgrade.tmp',
    old_sha256=REGISTRATION_OLD_SHA256, new_sha256=REGISTRATION_NEW_SHA256,
)
TARGETS = (*CONSUMER_TARGETS, HELPER_TARGET, REGISTRATION_TARGET)
PROBE_TARGET = Path('/usr/local/libexec/hermes-deals-audits/origin-path-probe.py')


def _fail(message: str) -> None:
    raise UpgradeError(message)


def _git_blob(data: bytes) -> str:
    return hashlib.sha1(f'blob {len(data)}\0'.encode('ascii') + data).hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run(argv: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        tuple(argv), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, shell=False,
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'},
    )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return _run((str(GIT), '-c', f'safe.directory={repo}', '-C', str(repo), *args), cwd=repo)


def _git_stdout(repo: Path, *args: str) -> bytes:
    result = _git(repo, *args)
    if result.returncode != 0:
        _fail(f'reviewed Git source validation failed for fixed repository: {repo}')
    return result.stdout


def _require_rpi_source(expected_sha: str) -> dict[str, bytes]:
    if FULL_SHA.fullmatch(expected_sha) is None:
        _fail('expected RPi5 source SHA must be lowercase 40-character hex')
    if _git_stdout(ROOT, 'rev-parse', 'HEAD').decode('ascii', 'strict').strip() != expected_sha:
        _fail('RPi5 checkout HEAD does not match expected source SHA')
    if _git_stdout(ROOT, 'status', '--porcelain=v1', '--untracked-files=all'):
        _fail('RPi5 trusted checkout is not clean')
    if _git_stdout(ROOT, 'show', f'{expected_sha}:{SCRIPT_RELATIVE}') != Path(__file__).read_bytes():
        _fail('upgrade operator bytes differ from exact expected RPi5 source')
    reviewed: dict[str, bytes] = {}
    for spec in CONSUMER_TARGETS:
        assert spec.source_path is not None
        raw = _git_stdout(ROOT, 'show', f'{expected_sha}:{spec.source_path}')
        if _git_blob(raw) != spec.new_blob:
            _fail(f'corrected RPi5 consumer binding drifted: {spec.source_path}')
        reviewed[spec.name] = raw
    return reviewed


def _require_hermes_source() -> bytes:
    if _git_stdout(HERMES_SOURCE_ROOT, 'rev-parse', '--show-toplevel').decode().strip() != str(HERMES_SOURCE_ROOT):
        _fail('fixed Hermes trusted source root identity drifted')
    if _git_stdout(HERMES_SOURCE_ROOT, 'rev-parse', 'HEAD').decode().strip() != HERMES_SOURCE_SHA:
        _fail('Hermes trusted source HEAD differs from corrected reviewed source')
    symbolic = _git(HERMES_SOURCE_ROOT, 'symbolic-ref', '-q', 'HEAD')
    if symbolic.returncode == 0:
        _fail('Hermes trusted source checkout must be detached')
    if symbolic.returncode != 1:
        _fail('unable to prove detached Hermes trusted source checkout')
    if _git_stdout(HERMES_SOURCE_ROOT, 'status', '--porcelain=v1', '--untracked-files=all'):
        _fail('Hermes trusted source checkout is not clean')
    if _git_stdout(HERMES_SOURCE_ROOT, 'remote', 'get-url', 'origin').decode().strip() != HERMES_ORIGIN:
        _fail('Hermes trusted source origin drifted')
    helper = _git_stdout(HERMES_SOURCE_ROOT, 'show', f'{HERMES_SOURCE_SHA}:{HELPER_SOURCE}')
    if _git_blob(helper) != HELPER_NEW_BLOB or _sha256(helper) != HELPER_NEW_SHA256:
        _fail('corrected Hermes helper provenance drifted')
    helper_path = HERMES_SOURCE_ROOT / HELPER_SOURCE
    meta = os.lstat(helper_path)
    if stat.S_ISLNK(meta.st_mode) or not stat.S_ISREG(meta.st_mode) or helper_path.read_bytes() != helper:
        _fail('Hermes helper worktree bytes differ from corrected reviewed source')
    probe = _git_stdout(HERMES_SOURCE_ROOT, 'show', f'{HERMES_SOURCE_SHA}:{PROBE_SOURCE}')
    if _git_blob(probe) != PROBE_BLOB or _sha256(probe) != PROBE_SHA256:
        _fail('reviewed Hermes probe provenance drifted')
    return helper


def _registration_bytes() -> bytes:
    value = {
        'schema': REGISTRATION_SCHEMA,
        'capability': CAPABILITY,
        'registered_source_sha': HERMES_SOURCE_SHA,
        'helper_sha256': HELPER_NEW_SHA256,
        'probe_sha256': PROBE_SHA256,
    }
    raw = (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
    if _git_blob(raw) != REGISTRATION_NEW_BLOB or _sha256(raw) != REGISTRATION_NEW_SHA256:
        _fail('derived corrected registration provenance drifted')
    return raw


def _require_parent_chain_safe(path: Path) -> None:
    for parent in reversed(path.parents):
        st = os.lstat(parent)
        if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
            _fail(f'target parent is not a real directory: {parent}')
        if st.st_uid != ROOT_UID or st.st_gid != ROOT_GID or stat.S_IMODE(st.st_mode) & 0o022:
            _fail(f'target parent ownership/mode is unsafe: {parent}')


def _open_parent(spec: TargetSpec) -> int:
    _require_parent_chain_safe(spec.path)
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(spec.path.parent, flags)
    st = os.fstat(fd)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != ROOT_UID or st.st_gid != ROOT_GID or stat.S_IMODE(st.st_mode) & 0o022:
        os.close(fd)
        _fail(f'opened target parent is unsafe: {spec.path.parent}')
    return fd


def _read_fd(fd: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            return b''.join(chunks)
        chunks.append(chunk)


def _require_exact_target(parent_fd: int, spec: TargetSpec, *, new: bool) -> os.stat_result:
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(spec.path.name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise UpgradeError(f'unable to open fixed {spec.name} target safely') from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            _fail(f'{spec.name} target is not a single-link regular file')
        if (st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode)) != (ROOT_UID, ROOT_GID, spec.mode):
            _fail(f'{spec.name} target metadata drifted')
        raw = _read_fd(fd)
        expected_blob = spec.new_blob if new else spec.old_blob
        expected_sha = spec.new_sha256 if new else spec.old_sha256
        if _git_blob(raw) != expected_blob or (expected_sha is not None and _sha256(raw) != expected_sha):
            _fail(f'{spec.name} target content drifted')
        path_now = os.stat(spec.path.name, dir_fd=parent_fd, follow_symlinks=False)
        if (path_now.st_dev, path_now.st_ino) != (st.st_dev, st.st_ino):
            _fail(f'{spec.name} target changed during validation')
        return st
    finally:
        os.close(fd)


def _require_temp_absent(parent_fd: int, spec: TargetSpec) -> None:
    try:
        os.stat(spec.temp_name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    _fail(f'fixed {spec.name} upgrade temporary target already exists')


def _require_probe() -> None:
    spec = TargetSpec('probe', PROBE_TARGET, 0o755, PROBE_BLOB, PROBE_BLOB, '.unused', old_sha256=PROBE_SHA256, new_sha256=PROBE_SHA256)
    parent_fd = _open_parent(spec)
    try:
        _require_exact_target(parent_fd, spec, new=False)
    finally:
        os.close(parent_fd)


def _preflight(expected_sha: str) -> dict[str, bytes]:
    if os.geteuid() != ROOT_UID:
        _fail('loopback provenance runtime-upgrade preflight requires root read context')
    reviewed = _require_rpi_source(expected_sha)
    reviewed['helper'] = _require_hermes_source()
    reviewed['registration'] = _registration_bytes()
    _require_probe()
    for spec in TARGETS:
        parent_fd = _open_parent(spec)
        try:
            _require_exact_target(parent_fd, spec, new=False)
            _require_temp_absent(parent_fd, spec)
        finally:
            os.close(parent_fd)
    return reviewed


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    offset = 0
    while offset < len(view):
        count = os.write(fd, view[offset:])
        if count <= 0:
            _fail('short write while preparing reviewed replacement')
        offset += count


def _replace_target(spec: TargetSpec, desired: bytes, state: dict[str, bool]) -> None:
    parent_fd = _open_parent(spec)
    temp_fd = -1
    try:
        opened = _require_exact_target(parent_fd, spec, new=False)
        _require_temp_absent(parent_fd, spec)
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | getattr(os, 'O_NOFOLLOW', 0)
        state['mutation_started'] = True
        temp_fd = os.open(spec.temp_name, flags, 0o600, dir_fd=parent_fd)
        _write_all(temp_fd, desired)
        os.fchown(temp_fd, ROOT_UID, ROOT_GID)
        os.fchmod(temp_fd, spec.mode)
        os.fsync(temp_fd)
        temp_st = os.fstat(temp_fd)
        if not stat.S_ISREG(temp_st.st_mode) or temp_st.st_nlink != 1:
            _fail(f'prepared {spec.name} replacement is not a single-link regular file')
        if (temp_st.st_uid, temp_st.st_gid, stat.S_IMODE(temp_st.st_mode)) != (ROOT_UID, ROOT_GID, spec.mode):
            _fail(f'prepared {spec.name} replacement metadata drifted')
        raw = _read_fd(temp_fd)
        if _git_blob(raw) != spec.new_blob or (spec.new_sha256 is not None and _sha256(raw) != spec.new_sha256):
            _fail(f'prepared {spec.name} replacement content drifted')
        current = _require_exact_target(parent_fd, spec, new=False)
        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            _fail(f'{spec.name} target inode changed before replacement')
        os.replace(spec.temp_name, spec.path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        state[f'{spec.name}_replaced'] = True
        os.fsync(parent_fd)
        _require_exact_target(parent_fd, spec, new=True)
    finally:
        if temp_fd >= 0:
            os.close(temp_fd)
        os.close(parent_fd)


def _new_state() -> dict[str, bool]:
    state = {'mutation_started': False}
    state.update({f'{spec.name}_replaced': False for spec in TARGETS})
    return state


def _receipt(result: str, source_sha: str, state: dict[str, bool], *, reason: str | None = None) -> str:
    value = {
        'schema': 'rozkalns.hermes-deals.origin-loopback-provenance-runtime-upgrade-receipt.v1',
        'result': result,
        'source_sha': source_sha,
        'hermes_source_sha': HERMES_SOURCE_SHA,
        'target_count': len(TARGETS),
        **state,
        'probe_mutated': False,
        'systemd_mutation': False,
        'docker_mutation': False,
        'network_mutation': False,
        'credential_content_read': False,
        'github_api_request': False,
        'socket_request_sent': False,
        'helper_executed': False,
        'genuine_audit_authorized': False,
        'production_mutation_started': state['mutation_started'],
        'automatic_retry': False,
        'automatic_rollback': False,
        'automatic_cleanup': False,
    }
    if reason is not None:
        value['reason'] = reason
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Fail-closed Hermes loopback helper provenance runtime upgrade')
    parser.add_argument('expected_sha', help='exact reviewed RPi5_main source SHA')
    parser.add_argument('--apply', action='store_true', help='perform separately owner-authorized fixed runtime mutation')
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    state = _new_state()
    try:
        reviewed = _preflight(args.expected_sha)
        if not args.apply:
            print(_receipt('HERMES_LOOPBACK_PROVENANCE_RUNTIME_UPGRADE_PREFLIGHT_READY', args.expected_sha, state))
            return 0
        reviewed = _preflight(args.expected_sha)
        for spec in TARGETS:
            _replace_target(spec, reviewed[spec.name], state)
    except (UpgradeError, OSError) as exc:
        print(_receipt('FAIL_CLOSED', args.expected_sha, state, reason=str(exc)))
        return 1
    print(_receipt('HERMES_LOOPBACK_PROVENANCE_RUNTIME_UPGRADE_PASS', args.expected_sha, state))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
