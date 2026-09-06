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
SYSTEMCTL = Path('/usr/bin/systemctl')
ROOT = Path(__file__).resolve().parents[1]
SCRIPT_RELATIVE = 'scripts/install-hermes-deals-origin-broker-evidence-write-recovery.py'
FULL_SHA = re.compile(r'^[0-9a-f]{40}$')
ROOT_UID = 0
ROOT_GID = 0
SOCKET_UNIT = 'rozkalns-hermes-deals-origin-broker.socket'
SERVICE_PATTERN = 'rozkalns-hermes-deals-origin-broker@*.service'
REPLAY_STATE_DIR = Path('/var/lib/rozkalns-deploy-executor-p9')
REPLAY_STATE_DB = REPLAY_STATE_DIR / 'state.sqlite3'
EVIDENCE_ROOT = Path('/var/lib/hermes-deals-audits/origin-path-audit/evidence')
EVIDENCE_MACHINE_ROOT = EVIDENCE_ROOT / 'rpi5'
FAILED_CANARY_DESTINATION = EVIDENCE_MACHINE_ROOT / '2f47f64ab15e767f4e53ad182326e64e313d5094-2026-09-06'
SOURCE_CREDENTIAL = Path('/etc/rozkalns-hermes-deals-origin-broker/source-github-app.pem')
EXECUTOR_CREDENTIAL = Path('/etc/rozkalns-deploy-executor/github-app.pem')
RECEIPT_SCHEMA = 'rozkalns.hermes-deals.origin-broker-evidence-write-recovery-receipt.v1'


class UpgradeError(RuntimeError):
    pass


@dataclass(frozen=True)
class TargetSpec:
    source_path: str
    target_path: Path
    old_blob: str | None
    new_blob: str
    mode: int


@dataclass(frozen=True)
class Prerequisite:
    target_path: Path
    expected_blob: str
    mode: int


REPLACE_TARGETS = (
    TargetSpec('ops/lib/deploy_executor/hermes_deals_origin_runtime_adapters.py', Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_runtime_adapters.py'), '456fea3d6969975d0fd432d20089772f28b63ec7', '21918e96495592b6a3478e8e74ae06fdf640121d', 0o644),
    TargetSpec('ops/systemd/rozkalns-hermes-deals-origin-broker@.service', Path('/etc/systemd/system/rozkalns-hermes-deals-origin-broker@.service'), '21319746d1e32f2b67f701f0a22174bfb0542987', '2f4874323a92610d4d91df719a97688bc880fc48', 0o644),
)

CREATE_TARGETS = ()

PREREQUISITES = (
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_privileged_broker.py'), '7656fe3c0ba7cfe1865ec000ab77503569beb7bd', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_helper_launch.py'), '4e29a13202cfb49003d9922e5ceeb905bb00a774', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_broker_composition.py'), '571f7f51cf10013c66343c1c8c27ddfaf8cd92c0', 0o644),
    Prerequisite(Path('/usr/local/libexec/rozkalns-hermes-deals-origin-broker'), '49aced1a1e6dd0c986947f53f06b23eba590aec4', 0o755),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_adapter.py'), '0b20cefa0c9193ecb8e7811c855767d56baf59ce', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_dispatch_request.py'), 'bd58fa89a6eade662cf1e942d48ef5381c4e679b', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_privileged_consumer.py'), 'af0987064710afedd02cd56f40b9e3a3cacfaf00', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_privileged_dispatcher.py'), 'ae51af60bf2094be944d13c303bf6a94c0117d69', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_broker_runtime.py'), '53112450cbccbabd9a5ec62966b9fd96d3513bea', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_source_auth.py'), '43640e9089cc39e96d472beb50e8653a5df5fa78', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_canonical_revalidator.py'), '8c5d9d7746248b485b212cf601786924ba6e4d42', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/hermes_deals_origin_host_evidence.py'), '4358beb65a48ed72c82d0e99e1fc8fd49db88524', 0o644),
    Prerequisite(Path('/etc/systemd/system/rozkalns-hermes-deals-origin-broker.socket'), '8eb05b83840b13b27e03e2bbb37d6d0bfc3697cb', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/adapters.py'), '9d62967607fc9677a3c8cc2720462ee7135ed2a6', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/queue_normalizer.py'), '1878d4765fab112a1066aec75cbcd9c422040dd2', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/registry.py'), '7de127a58534879385bc58299827d9081775dbe9', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/protocol.py'), 'c968390ea0886894f278da39a92aa714d4ca601d', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/state.py'), 'ac91f1b8d4f78742443e7b90c16c046f1b7ea22f', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/transport.py'), '7e0bbca7f8106e1bb3595ab551d99047db0ccb58', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/source_evidence.py'), '3a3ed0999c6a1c240ac3349866b0d559e46d90e6', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/github_app_auth.py'), '510fab79f5e5e2cb387673eba33e8b7af1e001c2', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/p9_canary.py'), 'e288110ea421edc165284c25923d9b8ed189ac83', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/p9_isolated_auth_surface.py'), 'cb4dc3c68f001032ce6692fdced9bcbbbd23a41d', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/p9_runtime.py'), 'ff3fd3196b7335305dced89244c65f68c65d27b4', 0o644),
    Prerequisite(Path('/usr/local/lib/rozkalns-deploy-executor/deploy_executor/p9_source_auth.py'), '130fc36a22bb4ace500b022c3defcccbf0893012', 0o644),
)

SYSTEMCTL_MUTATIONS = (
    ('stop', SOCKET_UNIT),
    ('daemon-reload',),
    ('start', SOCKET_UNIT),
)


def _fail(message: str) -> None:
    raise UpgradeError(message)


def _git_blob(data: bytes) -> str:
    return hashlib.sha1(f'blob {len(data)}\0'.encode('ascii') + data).hexdigest()


def _run(argv: Sequence[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        tuple(argv), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, shell=False,
        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8'},
    )


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return _run((str(GIT), '-c', f'safe.directory={ROOT}', '-C', str(ROOT), *args))


def _git_stdout(*args: str) -> bytes:
    result = _git(*args)
    if result.returncode != 0:
        _fail('reviewed recovery Git source validation failed')
    return result.stdout


def _require_exact_source(expected_sha: str) -> None:
    if FULL_SHA.fullmatch(expected_sha) is None:
        _fail('expected source SHA must be lowercase 40-character hex')
    head = _git_stdout('rev-parse', 'HEAD').decode('ascii','strict').strip()
    if head != expected_sha:
        _fail('checkout HEAD does not match expected source SHA')
    if _git('status','--porcelain').stdout:
        _fail('trusted source checkout must be clean')
    tracked = _git_stdout('show', f'{expected_sha}:{SCRIPT_RELATIVE}')
    if tracked != Path(__file__).read_bytes():
        _fail('recovery operator bytes differ from exact expected source SHA')
    for target in (*REPLACE_TARGETS, *CREATE_TARGETS):
        data = _git_stdout('show', f'{expected_sha}:{target.source_path}')
        if _git_blob(data) != target.new_blob:
            _fail(f'frozen reviewed source blob drifted: {target.source_path}')


def _require_parent_chain_safe(path: Path) -> None:
    for parent in reversed(path.parents):
        st = os.lstat(parent)
        if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
            _fail(f'target parent is not a real directory: {parent}')
        if st.st_uid != ROOT_UID or st.st_gid != ROOT_GID or stat.S_IMODE(st.st_mode) & 0o022:
            _fail(f'target parent ownership/mode is unsafe: {parent}')


def _read_exact_file(path: Path, *, expected_blob: str, mode: int) -> None:
    _require_parent_chain_safe(path)
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        _fail(f'unable to open required file safely: {path}: {exc.strerror}')
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            _fail(f'required file is not a single-link regular file: {path}')
        if (st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode)) != (ROOT_UID, ROOT_GID, mode):
            _fail(f'required file metadata drifted: {path}')
        chunks=[]
        while True:
            chunk=os.read(fd,1024*1024)
            if not chunk: break
            chunks.append(chunk)
        if _git_blob(b''.join(chunks)) != expected_blob:
            _fail(f'required file content drifted: {path}')
        now=os.stat(path,follow_symlinks=False)
        if (now.st_dev,now.st_ino)!=(st.st_dev,st.st_ino):
            _fail(f'required file changed during validation: {path}')
    finally:
        os.close(fd)


def _require_replace_prestate(target: TargetSpec) -> None:
    assert target.old_blob is not None
    _read_exact_file(target.target_path, expected_blob=target.old_blob, mode=target.mode)
    temp = target.target_path.parent / ('.' + target.target_path.name + '.hermes-evidence-write-recovery.tmp')
    if temp.exists() or temp.is_symlink():
        _fail(f'fixed recovery temporary target already exists: {temp}')


def _require_create_prestate(target: TargetSpec) -> None:
    _require_parent_chain_safe(target.target_path)
    try:
        os.lstat(target.target_path)
    except FileNotFoundError:
        return
    _fail(f'new runtime target already exists and requires reconciliation: {target.target_path}')


def _require_metadata_only(path: Path, mode: int) -> None:
    try:
        st=os.lstat(path)
    except FileNotFoundError:
        _fail(f'required credential metadata path is absent: {path}')
    if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
        _fail(f'credential metadata path is not a regular file: {path}')
    if (st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode)) != (ROOT_UID,ROOT_GID,mode):
        _fail(f'credential metadata drifted: {path}')


def _require_replay_state_metadata() -> None:
    st=os.lstat(REPLAY_STATE_DIR)
    if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
        _fail('replay state directory is not a real directory')
    if (st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode)) != (0,0,0o700):
        _fail('replay state directory metadata drifted')
    db=os.lstat(REPLAY_STATE_DB)
    if not stat.S_ISREG(db.st_mode) or stat.S_ISLNK(db.st_mode):
        _fail('replay state database is not a regular file')
    if (db.st_uid,db.st_gid,stat.S_IMODE(db.st_mode)) != (0,0,0o600):
        _fail('replay state database metadata drifted')
    wal=Path(str(REPLAY_STATE_DB)+'-wal')
    try:
        w=wal.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(w.st_mode) or w.st_size != 0:
        _fail('replay state database has a live WAL')


def _require_evidence_root_metadata() -> None:
    for path in (EVIDENCE_ROOT, EVIDENCE_MACHINE_ROOT):
        st = os.lstat(path)
        if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
            _fail(f'evidence write path is not a real directory: {path}')
        if (st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode)) != (0, 0, 0o700):
            _fail(f'evidence write path metadata drifted: {path}')


def _require_failed_canary_destination_absent() -> None:
    if os.path.lexists(FAILED_CANARY_DESTINATION):
        _fail('failed canary evidence destination already exists; cleanup is not authorized')


def _systemctl_query(*args: str) -> subprocess.CompletedProcess[bytes]:
    allowed={
        ('is-enabled', SOCKET_UNIT),
        ('is-active', SOCKET_UNIT),
        ('list-units','--type=service','--state=active','--no-legend','--no-pager',SERVICE_PATTERN),
    }
    if tuple(args) not in allowed:
        _fail('systemctl query is outside the fixed upgrade allowlist')
    return _run((str(SYSTEMCTL),*args),cwd=Path('/'))


def _require_socket_prestate() -> None:
    enabled=_systemctl_query('is-enabled',SOCKET_UNIT)
    if enabled.returncode != 0 or enabled.stdout.strip() != b'enabled':
        _fail('broker socket must be enabled before upgrade')
    active=_systemctl_query('is-active',SOCKET_UNIT)
    if active.returncode != 0 or active.stdout.strip() != b'active':
        _fail('broker socket must be active before upgrade')
    services=_systemctl_query('list-units','--type=service','--state=active','--no-legend','--no-pager',SERVICE_PATTERN)
    if services.returncode != 0 or services.stdout.strip():
        _fail('active broker service instance exists before upgrade')


def _preflight(expected_sha: str) -> dict[str, bytes]:
    if os.geteuid() != ROOT_UID:
        _fail('broker evidence-write recovery preflight requires root read context')
    _require_exact_source(expected_sha)
    _require_metadata_only(SOURCE_CREDENTIAL,0o600)
    _require_metadata_only(EXECUTOR_CREDENTIAL,0o400)
    _require_replay_state_metadata()
    _require_evidence_root_metadata()
    _require_failed_canary_destination_absent()
    for prerequisite in PREREQUISITES:
        _read_exact_file(prerequisite.target_path, expected_blob=prerequisite.expected_blob, mode=prerequisite.mode)
    reviewed={}
    for target in REPLACE_TARGETS:
        _require_replace_prestate(target)
        reviewed[target.source_path]=_git_stdout('show',f'{expected_sha}:{target.source_path}')
    for target in CREATE_TARGETS:
        _require_create_prestate(target)
        reviewed[target.source_path]=_git_stdout('show',f'{expected_sha}:{target.source_path}')
    _require_socket_prestate()
    return reviewed


def _systemctl_mutation(state: dict[str, object], *args: str) -> None:
    if tuple(args) not in SYSTEMCTL_MUTATIONS:
        _fail('systemctl mutation is outside the fixed recovery allowlist')
    state['mutation_started']=True
    result=_run((str(SYSTEMCTL),*args),cwd=Path('/'))
    if result.returncode != 0:
        _fail('systemctl mutation failed: '+' '.join(args))


def _write_all(fd: int, data: bytes) -> None:
    view=memoryview(data); offset=0
    while offset < len(view):
        count=os.write(fd,view[offset:])
        if count <= 0: _fail('short write while preparing runtime target')
        offset += count


def _read_fd_all(fd: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            return b''.join(chunks)
        chunks.append(chunk)


def _replace_target(target: TargetSpec, data: bytes, state: dict[str, object]) -> None:
    assert target.old_blob is not None
    _require_replace_prestate(target)
    parent = target.target_path.parent
    temp_name = '.' + target.target_path.name + '.hermes-evidence-write-recovery.tmp'
    parent_flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, 'O_DIRECTORY'):
        parent_flags |= os.O_DIRECTORY
    if hasattr(os, 'O_NOFOLLOW'):
        parent_flags |= os.O_NOFOLLOW
    parent_fd = os.open(parent, parent_flags)
    old_fd = -1
    temp_fd = -1
    try:
        read_flags = os.O_RDONLY | os.O_CLOEXEC
        if hasattr(os, 'O_NOFOLLOW'):
            read_flags |= os.O_NOFOLLOW
        old_fd = os.open(target.target_path.name, read_flags, dir_fd=parent_fd)
        old_st = os.fstat(old_fd)
        if not stat.S_ISREG(old_st.st_mode) or old_st.st_nlink != 1:
            _fail(f'old replacement target is not a single-link regular file: {target.target_path}')
        if (old_st.st_uid, old_st.st_gid, stat.S_IMODE(old_st.st_mode)) != (0, 0, target.mode):
            _fail(f'old replacement target metadata drifted: {target.target_path}')
        if _git_blob(_read_fd_all(old_fd)) != target.old_blob:
            _fail(f'old replacement target content drifted: {target.target_path}')

        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
        if hasattr(os, 'O_NOFOLLOW'):
            flags |= os.O_NOFOLLOW
        state['mutation_started'] = True
        temp_fd = os.open(temp_name, flags, 0o600, dir_fd=parent_fd)
        _write_all(temp_fd, data)
        os.fchown(temp_fd, 0, 0)
        os.fchmod(temp_fd, target.mode)
        os.fsync(temp_fd)
        if _git_blob(_read_fd_all(temp_fd)) != target.new_blob:
            _fail(f'prepared replacement content verification failed: {target.target_path}')
        if (os.fstat(temp_fd).st_uid, os.fstat(temp_fd).st_gid, stat.S_IMODE(os.fstat(temp_fd).st_mode)) != (0, 0, target.mode):
            _fail(f'prepared replacement metadata verification failed: {target.target_path}')

        # Revalidate the exact old inode immediately before replacement.
        if _git_blob(_read_fd_all(old_fd)) != target.old_blob:
            _fail(f'old replacement content changed before replace: {target.target_path}')
        path_now = os.stat(target.target_path.name, dir_fd=parent_fd, follow_symlinks=False)
        if (path_now.st_dev, path_now.st_ino) != (old_st.st_dev, old_st.st_ino):
            _fail(f'old replacement inode changed before replace: {target.target_path}')
        os.replace(temp_name, target.target_path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
        state['files_replaced'] = int(state['files_replaced']) + 1
        _read_exact_file(target.target_path, expected_blob=target.new_blob, mode=target.mode)
    finally:
        if temp_fd >= 0:
            os.close(temp_fd)
        if old_fd >= 0:
            os.close(old_fd)
        os.close(parent_fd)

def _create_target(target: TargetSpec, data: bytes, state: dict[str, object]) -> None:
    _require_create_prestate(target)
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC
    if hasattr(os,'O_NOFOLLOW'): flags|=os.O_NOFOLLOW
    state['mutation_started']=True
    fd=os.open(target.target_path,flags,0o600)
    try:
        _write_all(fd,data); os.fchown(fd,0,0); os.fchmod(fd,target.mode); os.fsync(fd)
    finally:
        os.close(fd)
    state['files_created']=int(state['files_created'])+1
    _read_exact_file(target.target_path,expected_blob=target.new_blob,mode=target.mode)


def _receipt(result: str, source_sha: str, state: dict[str, object], reason: str | None=None) -> str:
    value={
        'schema':RECEIPT_SCHEMA,'result':result,'source_sha':source_sha,
        'replace_target_count':len(REPLACE_TARGETS),'create_target_count':len(CREATE_TARGETS),
        'shared_prerequisite_count':len(PREREQUISITES),
        'replay_write_path':str(REPLAY_STATE_DIR),'evidence_write_path':str(EVIDENCE_MACHINE_ROOT),'failed_canary_destination':str(FAILED_CANARY_DESTINATION),'failed_canary_destination_absence_required':True,'global_registry_mutation':False,
        'credential_content_read':False,'github_api_request':False,'replay_consume_invoked':False,
        'helper_executed':False,'genuine_audit_authorized':False,'production_mutation_started':False,
        'mutation_started':bool(state['mutation_started']),'socket_stop_attempted':bool(state['socket_stop_attempted']),
        'socket_stopped':bool(state['socket_stopped']),'files_replaced':int(state['files_replaced']),
        'files_created':int(state['files_created']),'daemon_reload_attempted':bool(state['daemon_reload_attempted']),
        'socket_start_attempted':bool(state['socket_start_attempted']),'socket_started':bool(state['socket_started']),
        'automatic_retry':False,'automatic_rollback':False,'automatic_cleanup':False,
    }
    if reason is not None: value['reason']=reason
    return json.dumps(value,sort_keys=True,separators=(',',':'))


def _new_state() -> dict[str, object]:
    return {
        'mutation_started': False,
        'socket_stop_attempted': False,
        'socket_stopped': False,
        'files_replaced': 0,
        'files_created': 0,
        'daemon_reload_attempted': False,
        'socket_start_attempted': False,
        'socket_started': False,
    }


def apply(expected_sha: str, state: dict[str, object]) -> str:
    reviewed = _preflight(expected_sha)
    # Repeat complete read-only gate immediately before the first mutation.
    reviewed = _preflight(expected_sha)
    state['socket_stop_attempted'] = True
    _systemctl_mutation(state, 'stop', SOCKET_UNIT)
    inactive = _systemctl_query('is-active', SOCKET_UNIT)
    if inactive.returncode != 3 or inactive.stdout.strip() != b'inactive':
        _fail('broker socket did not reach the exact inactive state after stop')
    services = _systemctl_query(
        'list-units', '--type=service', '--state=active', '--no-legend', '--no-pager', SERVICE_PATTERN
    )
    if services.returncode != 0 or services.stdout.strip():
        _fail('broker service instance active after socket stop')
    state['socket_stopped'] = True

    for target in REPLACE_TARGETS:
        _replace_target(target, reviewed[target.source_path], state)
    for target in CREATE_TARGETS:
        _create_target(target, reviewed[target.source_path], state)
    for prerequisite in PREREQUISITES:
        _read_exact_file(
            prerequisite.target_path,
            expected_blob=prerequisite.expected_blob,
            mode=prerequisite.mode,
        )

    state['daemon_reload_attempted'] = True
    _systemctl_mutation(state, 'daemon-reload')
    state['socket_start_attempted'] = True
    _systemctl_mutation(state, 'start', SOCKET_UNIT)
    active = _systemctl_query('is-active', SOCKET_UNIT)
    if active.returncode != 0 or active.stdout.strip() != b'active':
        _fail('broker socket failed post-upgrade active verification')
    enabled = _systemctl_query('is-enabled', SOCKET_UNIT)
    if enabled.returncode != 0 or enabled.stdout.strip() != b'enabled':
        _fail('broker socket enablement drifted during upgrade')
    state['socket_started'] = True
    return _receipt('HERMES_ORIGIN_BROKER_EVIDENCE_WRITE_RECOVERY_PASS', expected_sha, state)


def preflight(expected_sha: str, state: dict[str, object]) -> str:
    _preflight(expected_sha)
    return _receipt('HERMES_ORIGIN_BROKER_EVIDENCE_WRITE_RECOVERY_PREFLIGHT_READY', expected_sha, state)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Fail-closed Hermes broker evidence-write recovery operator; source merge never authorizes --apply.'
    )
    parser.add_argument('expected_source_sha')
    parser.add_argument(
        '--apply',
        action='store_true',
        help='perform only under a separate explicit owner LIVE authorization',
    )
    args = parser.parse_args(argv)
    state = _new_state()
    try:
        output = (
            apply(args.expected_source_sha, state)
            if args.apply
            else preflight(args.expected_source_sha, state)
        )
    except (UpgradeError, OSError) as exc:
        print(
            _receipt('FAIL_CLOSED', args.expected_source_sha, state, reason=str(exc)),
            file=sys.stderr,
        )
        return 1
    print(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
