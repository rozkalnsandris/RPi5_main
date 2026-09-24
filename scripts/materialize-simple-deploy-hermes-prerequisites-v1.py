#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
from typing import Sequence

GIT = Path('/usr/bin/git')
ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'https://github.com/rozkalnsandris/RPi5_main.git'
SCRIPT_RELATIVE = 'scripts/materialize-simple-deploy-hermes-prerequisites-v1.py'
CONTRACT_RELATIVE = 'ops/contracts/simple-deploy-hermes-prerequisite-materialization-v1.json'
FULL_SHA = re.compile(r'^[0-9a-f]{40}$')
ENV_KEY = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
SOURCE_USER = 'andris'
SOURCE_HOME_RESOLUTION = 'passwd_database'
SOURCE_CHECKOUT_RELATIVE = Path('hermes-deals')
SOURCE_DATA_RELATIVE = Path('data/raw')
SOURCE_CONFIG_RELATIVE = Path('config')
SOURCE_ENV_RELATIVE = Path('.env')
ETC_ROOT = Path('/etc/rozkalns-simple-deployer')
STATE_PARENT = Path('/var/lib/rozkalns-simple-deployer')
TARGET_ROOT = STATE_PARENT / 'hermes-deals'
TARGET_DATA_PARENT = TARGET_ROOT / 'data'
TARGET_DATA = TARGET_DATA_PARENT / 'raw'
TARGET_CONFIG = TARGET_ROOT / 'config'
PRIVATE_ROOT = ETC_ROOT / 'private'
TARGET_ENV = PRIVATE_ROOT / 'hermes-deals-api.env'
STATE_STAGE = STATE_PARENT / '.hermes-deals-prerequisites-v1.staged'
ENV_STAGE = PRIVATE_ROOT / '.hermes-deals-api.env.prerequisites-v1.staged'
ROOT_UID = 0
ROOT_GID = 0
REQUIRED_ENV_KEYS = ('DATABASE_URL', 'HTTP_USER_AGENT')
STATUS_ABSENT = 'ABSENT'
STATUS_EXACT_READY = 'EXACT_READY'
STATUS_PARTIAL_CONFLICT = 'PARTIAL_CONFLICT'
PUBLIC_SCHEMA = 'rozkalns.rpi5-main.simple-deploy-hermes-prerequisite-preflight.v1'


@dataclass(frozen=True)
class MaterializationPaths:
    checkout: Path
    source_data: Path
    source_config: Path
    source_env: Path
    etc_root: Path
    state_parent: Path
    target_root: Path
    target_data_parent: Path
    target_data: Path
    target_config: Path
    private_root: Path
    target_env: Path
    state_stage: Path
    env_stage: Path


def _production_paths(source_home: Path) -> MaterializationPaths:
    checkout = source_home / SOURCE_CHECKOUT_RELATIVE
    return MaterializationPaths(
        checkout=checkout,
        source_data=checkout / SOURCE_DATA_RELATIVE,
        source_config=checkout / SOURCE_CONFIG_RELATIVE,
        source_env=checkout / SOURCE_ENV_RELATIVE,
        etc_root=ETC_ROOT,
        state_parent=STATE_PARENT,
        target_root=TARGET_ROOT,
        target_data_parent=TARGET_DATA_PARENT,
        target_data=TARGET_DATA,
        target_config=TARGET_CONFIG,
        private_root=PRIVATE_ROOT,
        target_env=TARGET_ENV,
        state_stage=STATE_STAGE,
        env_stage=ENV_STAGE,
    )


class MaterializationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Classification:
    status: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ProtectedPlan:
    source_data_digest: str
    source_config_digest: str
    env_bytes: bytes
    source_files: int


@dataclass
class Progress:
    mutation_started: bool = False
    parent_directories_created: int = 0
    staged_directories_created: int = 0
    staged_files_created: int = 0
    published_targets: int = 0


class ApplyFailure(MaterializationError):
    def __init__(self, message: str, progress: Progress):
        super().__init__(message)
        self.progress = progress


def _fail(message: str) -> None:
    raise MaterializationError(message)


def _run(argv: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        tuple(argv),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'},
    )


def _git_stdout(*args: str) -> bytes:
    result = _run((str(GIT), '-c', f'safe.directory={ROOT}', '-C', str(ROOT), *args), cwd=ROOT)
    if result.returncode != 0:
        _fail('Git source validation failed')
    return result.stdout


def _require_source_checkout(expected_sha: str) -> None:
    if FULL_SHA.fullmatch(expected_sha) is None:
        _fail('expected source SHA must be lowercase 40-character hex')
    if _git_stdout('rev-parse', 'HEAD').decode('ascii').strip() != expected_sha:
        _fail('checkout HEAD does not match expected source SHA')
    if _git_stdout('remote', 'get-url', 'origin').decode('utf-8').strip() != ORIGIN:
        _fail('checkout origin drifted')
    if _git_stdout('status', '--porcelain=v1', '--untracked-files=all'):
        _fail('source checkout must be clean')
    for relative in (SCRIPT_RELATIVE, CONTRACT_RELATIVE):
        if _git_stdout('show', f'{expected_sha}:{relative}') != (ROOT / relative).read_bytes():
            _fail('reviewed materialization source differs from expected Git source')


def _mode(info: os.stat_result) -> int:
    return stat.S_IMODE(info.st_mode)


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None


def _source_reason(path: Path, *, kind: str, uid: int, gid: int, private: bool = False) -> str | None:
    info = _lstat(path)
    if info is None or stat.S_ISLNK(info.st_mode):
        return 'required fixed source is absent or a symlink'
    if kind == 'directory' and not stat.S_ISDIR(info.st_mode):
        return 'required fixed source is not a real directory'
    if kind == 'file' and not stat.S_ISREG(info.st_mode):
        return 'required fixed source is not a real regular file'
    if info.st_uid != uid or info.st_gid != gid:
        return 'fixed source ownership drifted'
    mode = _mode(info)
    if mode & 0o002 or mode & 0o6000:
        return 'fixed source mode is unsafe'
    if private and mode & 0o022:
        return 'fixed private source is group/world-writable'
    return None


def _destination_reason(path: Path, *, kind: str, mode: int, uid: int, gid: int) -> str | None:
    info = _lstat(path)
    if info is None or stat.S_ISLNK(info.st_mode):
        return 'fixed destination is absent or a symlink'
    if kind == 'directory' and not stat.S_ISDIR(info.st_mode):
        return 'fixed destination is not a real directory'
    if kind == 'file' and not stat.S_ISREG(info.st_mode):
        return 'fixed destination is not a real regular file'
    if info.st_uid != uid or info.st_gid != gid or _mode(info) != mode:
        return 'fixed destination ownership or mode drifted'
    return None


def _directory_names(path: Path) -> set[str]:
    try:
        return {entry.name for entry in os.scandir(path)}
    except OSError as exc:
        raise MaterializationError('fixed destination directory could not be inspected') from exc


def _validate_machine_contract() -> None:
    try:
        contract = json.loads((ROOT / CONTRACT_RELATIVE).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MaterializationError('machine-readable materialization contract is unavailable or invalid') from exc
    if contract.get('schema') != 'rozkalns.rpi5-main.simple-deploy-hermes-prerequisite-materialization.v1':
        _fail('materialization contract schema drifted')
    if contract.get('issue') != 711:
        _fail('materialization contract issue binding drifted')
    expected_source = {
        'owner_user': SOURCE_USER,
        'home_resolution': SOURCE_HOME_RESOLUTION,
        'checkout_relative': SOURCE_CHECKOUT_RELATIVE.as_posix(),
        'within_checkout': {
            'data': SOURCE_DATA_RELATIVE.as_posix(),
            'config': SOURCE_CONFIG_RELATIVE.as_posix(),
            'private_env': SOURCE_ENV_RELATIVE.as_posix(),
        },
    }
    source = contract.get('source', {})
    for key, expected in expected_source.items():
        if source.get(key) != expected:
            _fail('materialization contract source identity drifted')
    expected_destinations = {
        'state_root': str(TARGET_ROOT),
        'data': str(TARGET_DATA),
        'config': str(TARGET_CONFIG),
        'private_env': str(TARGET_ENV),
    }
    if contract.get('destination', {}).get('paths') != expected_destinations:
        _fail('materialization contract destination paths drifted')
    if tuple(contract.get('private_env', {}).get('required_keys', ())) != REQUIRED_ENV_KEYS:
        _fail('materialization contract private key set drifted')
    if contract.get('cli', {}).get('options') != ['--expected-source-sha', '--apply']:
        _fail('materialization contract CLI authority drifted')


def _public_preflight(
    paths: MaterializationPaths,
    *,
    source_uid: int,
    source_gid: int,
    root_uid: int = ROOT_UID,
    root_gid: int = ROOT_GID,
) -> Classification:
    reasons: list[str] = []
    for path, kind, private in (
        (paths.checkout, 'directory', False),
        (paths.source_data, 'directory', False),
        (paths.source_config, 'directory', False),
        (paths.source_env, 'file', True),
    ):
        reason = _source_reason(path, kind=kind, uid=source_uid, gid=source_gid, private=private)
        if reason:
            reasons.append(reason)
    if _destination_reason(paths.etc_root, kind='directory', mode=0o755, uid=root_uid, gid=root_gid):
        reasons.append('SIMPLE-DEPLOY etc root metadata drifted')
    if _lstat(paths.state_stage) is not None or _lstat(paths.env_stage) is not None:
        reasons.append('fixed staging path is unexpectedly present')
    root_present = _lstat(paths.target_root) is not None
    env_present = _lstat(paths.target_env) is not None
    if reasons:
        return Classification(STATUS_PARTIAL_CONFLICT, tuple(sorted(set(reasons))))
    if not root_present and not env_present:
        for parent, expected_mode in ((paths.state_parent, 0o755), (paths.private_root, 0o700)):
            if _lstat(parent) is None:
                continue
            if _destination_reason(parent, kind='directory', mode=expected_mode, uid=root_uid, gid=root_gid):
                return Classification(STATUS_PARTIAL_CONFLICT, ('fixed parent directory metadata drifted',))
        return Classification(STATUS_ABSENT, ())
    if not root_present or not env_present:
        return Classification(STATUS_PARTIAL_CONFLICT, ('only part of the fixed prerequisite destination exists',))
    for path, kind, expected_mode in (
        (paths.state_parent, 'directory', 0o755),
        (paths.target_root, 'directory', 0o755),
        (paths.target_data_parent, 'directory', 0o755),
        (paths.target_data, 'directory', 0o755),
        (paths.target_config, 'directory', 0o755),
        (paths.private_root, 'directory', 0o700),
        (paths.target_env, 'file', 0o600),
    ):
        reason = _destination_reason(path, kind=kind, mode=expected_mode, uid=root_uid, gid=root_gid)
        if reason:
            reasons.append(reason)
    if not reasons and _directory_names(paths.target_root) != {'data', 'config'}:
        reasons.append('fixed state root contains unexpected top-level entries')
    if not reasons and _directory_names(paths.target_data_parent) != {'raw'}:
        reasons.append('fixed data parent contains unexpected top-level entries')
    if reasons:
        return Classification(STATUS_PARTIAL_CONFLICT, tuple(sorted(set(reasons))))
    return Classification(STATUS_EXACT_READY, ())


def _read_regular_bytes_no_follow(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise MaterializationError('protected fixed source could not be opened safely') from exc
    try:
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b''.join(chunks)
    except OSError as exc:
        raise MaterializationError('protected fixed source could not be read safely') from exc
    finally:
        os.close(fd)


def _extract_required_env(raw: bytes) -> bytes:
    try:
        text = raw.decode('utf-8')
    except UnicodeError as exc:
        raise MaterializationError('protected env source is not valid UTF-8') from exc
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if '=' not in line:
            raise MaterializationError('protected env source contains malformed assignment syntax')
        key, value = line.split('=', 1)
        key = key.strip()
        if not ENV_KEY.fullmatch(key):
            raise MaterializationError('protected env source contains malformed key syntax')
        if key in REQUIRED_ENV_KEYS:
            if key in values:
                raise MaterializationError(f'protected env source duplicates required key {key}')
            values[key] = value
    missing = [key for key in REQUIRED_ENV_KEYS if key not in values]
    if missing:
        raise MaterializationError('protected env source is missing required key(s): ' + ','.join(missing))
    return ''.join(f'{key}={values[key]}\n' for key in REQUIRED_ENV_KEYS).encode('utf-8')


def _tree_digest(
    root: Path,
    *,
    expected_uid: int,
    expected_gid: int,
    protected_label: str,
    normalized: bool = False,
) -> tuple[str, int]:
    info = _lstat(root)
    if info is None or stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise MaterializationError(f'{protected_label} protected tree root is not a real directory')
    if info.st_uid != expected_uid or info.st_gid != expected_gid:
        raise MaterializationError(f'{protected_label} protected tree ownership drifted')
    if normalized and _mode(info) != 0o755:
        raise MaterializationError(f'{protected_label} protected tree directory mode drifted')
    if not normalized and (_mode(info) & 0o002 or _mode(info) & 0o6000):
        raise MaterializationError(f'{protected_label} protected tree root mode is unsafe')
    digest = hashlib.sha256()
    file_count = 0
    try:
        entries = sorted(root.rglob('*'), key=lambda p: p.relative_to(root).as_posix())
    except OSError as exc:
        raise MaterializationError(f'{protected_label} protected tree could not be traversed') from exc
    for path in entries:
        try:
            entry = os.lstat(path)
        except OSError as exc:
            raise MaterializationError(f'{protected_label} protected tree metadata changed during validation') from exc
        if stat.S_ISLNK(entry.st_mode):
            raise MaterializationError(f'{protected_label} protected tree contains a symlink')
        if entry.st_uid != expected_uid or entry.st_gid != expected_gid:
            raise MaterializationError(f'{protected_label} protected tree ownership drifted')
        mode = _mode(entry)
        relative = path.relative_to(root).as_posix().encode('utf-8')
        if stat.S_ISDIR(entry.st_mode):
            if normalized and mode != 0o755:
                raise MaterializationError(f'{protected_label} protected tree directory mode drifted')
            if not normalized and (mode & 0o002 or mode & 0o6000):
                raise MaterializationError(f'{protected_label} protected tree mode is unsafe')
            digest.update(b'D\0' + relative + b'\0')
            continue
        if not stat.S_ISREG(entry.st_mode):
            raise MaterializationError(f'{protected_label} protected tree contains an unsupported file type')
        if normalized and mode != 0o644:
            raise MaterializationError(f'{protected_label} protected tree file mode drifted')
        if not normalized and (mode & 0o002 or mode & 0o6000):
            raise MaterializationError(f'{protected_label} protected tree mode is unsafe')
        digest.update(b'F\0' + relative + b'\0')
        digest.update(hashlib.sha256(_read_regular_bytes_no_follow(path)).digest())
        file_count += 1
    return digest.hexdigest(), file_count


def _prepare_protected(paths: MaterializationPaths, *, source_uid: int, source_gid: int) -> ProtectedPlan:
    env_reason = _source_reason(paths.source_env, kind='file', uid=source_uid, gid=source_gid, private=True)
    if env_reason:
        raise MaterializationError(env_reason)
    env_bytes = _extract_required_env(_read_regular_bytes_no_follow(paths.source_env))
    data_digest, data_files = _tree_digest(
        paths.source_data,
        expected_uid=source_uid,
        expected_gid=source_gid,
        protected_label='data',
    )
    config_digest, config_files = _tree_digest(
        paths.source_config,
        expected_uid=source_uid,
        expected_gid=source_gid,
        protected_label='config',
    )
    return ProtectedPlan(data_digest, config_digest, env_bytes, data_files + config_files)


def _ensure_directory(
    path: Path,
    *,
    mode: int,
    uid: int,
    gid: int,
    progress: Progress,
    parent: bool = False,
) -> None:
    if _lstat(path) is not None:
        if _destination_reason(path, kind='directory', mode=mode, uid=uid, gid=gid):
            raise ApplyFailure('fixed parent directory metadata drifted before mutation', progress)
        return
    try:
        os.mkdir(path, mode)
        progress.mutation_started = True
        if parent:
            progress.parent_directories_created += 1
        else:
            progress.staged_directories_created += 1
        os.chown(path, uid, gid)
        os.chmod(path, mode)
    except OSError as exc:
        raise ApplyFailure('fixed directory creation failed', progress) from exc


def _copy_regular(
    source: Path,
    destination: Path,
    *,
    source_uid: int,
    source_gid: int,
    root_uid: int,
    root_gid: int,
    progress: Progress,
) -> None:
    try:
        info = os.lstat(source)
    except OSError as exc:
        raise ApplyFailure('protected source metadata changed during copy', progress) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ApplyFailure('protected source entry type changed during copy', progress)
    if info.st_uid != source_uid or info.st_gid != source_gid or _mode(info) & 0o002 or _mode(info) & 0o6000:
        raise ApplyFailure('protected source metadata changed during copy', progress)
    try:
        source_fd = os.open(source, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except OSError as exc:
        raise ApplyFailure('protected source file open failed', progress) from exc
    try:
        try:
            destination_fd = os.open(
                destination,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0),
                0o600,
            )
        except OSError as exc:
            raise ApplyFailure('protected tree file staging failed', progress) from exc
        progress.mutation_started = True
        progress.staged_files_created += 1
        try:
            while True:
                chunk = os.read(source_fd, 1024 * 1024)
                if not chunk:
                    break
                view = memoryview(chunk)
                offset = 0
                while offset < len(view):
                    written = os.write(destination_fd, view[offset:])
                    if written <= 0:
                        raise ApplyFailure('short write while staging protected tree', progress)
                    offset += written
            os.fsync(destination_fd)
            os.fchown(destination_fd, root_uid, root_gid)
            os.fchmod(destination_fd, 0o644)
        except OSError as exc:
            raise ApplyFailure('protected tree file staging failed', progress) from exc
        finally:
            os.close(destination_fd)
    finally:
        os.close(source_fd)


def _copy_tree(
    source_root: Path,
    destination_root: Path,
    *,
    source_uid: int,
    source_gid: int,
    root_uid: int,
    root_gid: int,
    progress: Progress,
) -> None:
    if _lstat(destination_root) is not None:
        raise ApplyFailure('fixed staging tree destination already exists', progress)
    _ensure_directory(destination_root, mode=0o755, uid=root_uid, gid=root_gid, progress=progress)
    try:
        entries = sorted(source_root.rglob('*'), key=lambda p: p.relative_to(source_root).as_posix())
    except OSError as exc:
        raise ApplyFailure('protected source tree could not be traversed during copy', progress) from exc
    for source in entries:
        destination = destination_root / source.relative_to(source_root)
        try:
            info = os.lstat(source)
        except OSError as exc:
            raise ApplyFailure('protected source metadata changed during copy', progress) from exc
        if stat.S_ISLNK(info.st_mode):
            raise ApplyFailure('protected source tree contains a symlink', progress)
        if info.st_uid != source_uid or info.st_gid != source_gid or _mode(info) & 0o002 or _mode(info) & 0o6000:
            raise ApplyFailure('protected source metadata changed during copy', progress)
        if stat.S_ISDIR(info.st_mode):
            _ensure_directory(destination, mode=0o755, uid=root_uid, gid=root_gid, progress=progress)
        elif stat.S_ISREG(info.st_mode):
            _copy_regular(
                source,
                destination,
                source_uid=source_uid,
                source_gid=source_gid,
                root_uid=root_uid,
                root_gid=root_gid,
                progress=progress,
            )
        else:
            raise ApplyFailure('protected source tree contains an unsupported file type', progress)


def _write_env_stage(path: Path, content: bytes, *, uid: int, gid: int, progress: Progress) -> None:
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    except OSError as exc:
        raise ApplyFailure('private env staging creation failed', progress) from exc
    progress.mutation_started = True
    progress.staged_files_created += 1
    try:
        view = memoryview(content)
        offset = 0
        while offset < len(view):
            written = os.write(fd, view[offset:])
            if written <= 0:
                raise ApplyFailure('short write while staging private env', progress)
            offset += written
        os.fsync(fd)
        os.fchown(fd, uid, gid)
        os.fchmod(fd, 0o600)
    except OSError as exc:
        raise ApplyFailure('private env staging write failed', progress) from exc
    finally:
        os.close(fd)


def _fsync_dir(path: Path, progress: Progress) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise ApplyFailure('directory fsync failed', progress) from exc


def _verify_exact_ready_protected(
    paths: MaterializationPaths,
    plan: ProtectedPlan,
    *,
    root_uid: int,
    root_gid: int,
) -> None:
    data_digest, _ = _tree_digest(
        paths.target_data,
        expected_uid=root_uid,
        expected_gid=root_gid,
        protected_label='installed data',
        normalized=True,
    )
    config_digest, _ = _tree_digest(
        paths.target_config,
        expected_uid=root_uid,
        expected_gid=root_gid,
        protected_label='installed config',
        normalized=True,
    )
    if data_digest != plan.source_data_digest:
        _fail('installed protected data tree does not match the fixed source')
    if config_digest != plan.source_config_digest:
        _fail('installed protected config tree does not match the fixed source')
    if _read_regular_bytes_no_follow(paths.target_env) != plan.env_bytes:
        _fail('installed private env projection does not match the fixed protected source')


def _apply(
    paths: MaterializationPaths,
    plan: ProtectedPlan,
    *,
    source_uid: int,
    source_gid: int,
    root_uid: int = ROOT_UID,
    root_gid: int = ROOT_GID,
) -> Progress:
    if _public_preflight(
        paths,
        source_uid=source_uid,
        source_gid=source_gid,
        root_uid=root_uid,
        root_gid=root_gid,
    ).status != STATUS_ABSENT:
        _fail('apply requires exact ABSENT prerequisite destination state')
    progress = Progress()
    try:
        _ensure_directory(paths.state_parent, mode=0o755, uid=root_uid, gid=root_gid, progress=progress, parent=True)
        _ensure_directory(paths.private_root, mode=0o700, uid=root_uid, gid=root_gid, progress=progress, parent=True)
        _ensure_directory(paths.state_stage, mode=0o700, uid=root_uid, gid=root_gid, progress=progress)
        stage_data_parent = paths.state_stage / 'data'
        _ensure_directory(stage_data_parent, mode=0o755, uid=root_uid, gid=root_gid, progress=progress)
        _copy_tree(
            paths.source_data,
            stage_data_parent / 'raw',
            source_uid=source_uid,
            source_gid=source_gid,
            root_uid=root_uid,
            root_gid=root_gid,
            progress=progress,
        )
        _copy_tree(
            paths.source_config,
            paths.state_stage / 'config',
            source_uid=source_uid,
            source_gid=source_gid,
            root_uid=root_uid,
            root_gid=root_gid,
            progress=progress,
        )
        os.chown(paths.state_stage, root_uid, root_gid)
        os.chmod(paths.state_stage, 0o755)
        _write_env_stage(paths.env_stage, plan.env_bytes, uid=root_uid, gid=root_gid, progress=progress)
        if _lstat(paths.target_root) is not None or _lstat(paths.target_env) is not None:
            raise ApplyFailure('fixed final prerequisite destination appeared after preflight', progress)
        staged_data, _ = _tree_digest(
            stage_data_parent / 'raw',
            expected_uid=root_uid,
            expected_gid=root_gid,
            protected_label='staged data',
            normalized=True,
        )
        staged_config, _ = _tree_digest(
            paths.state_stage / 'config',
            expected_uid=root_uid,
            expected_gid=root_gid,
            protected_label='staged config',
            normalized=True,
        )
        if staged_data != plan.source_data_digest or staged_config != plan.source_config_digest:
            raise ApplyFailure('staged protected tree verification failed', progress)
        if _read_regular_bytes_no_follow(paths.env_stage) != plan.env_bytes:
            raise ApplyFailure('staged private env verification failed', progress)
        try:
            os.rename(paths.state_stage, paths.target_root)
        except OSError as exc:
            raise ApplyFailure('atomic state-root publication failed', progress) from exc
        progress.published_targets += 1
        _fsync_dir(paths.state_parent, progress)
        try:
            os.link(paths.env_stage, paths.target_env, follow_symlinks=False)
        except OSError as exc:
            raise ApplyFailure('atomic private-env publication failed', progress) from exc
        progress.published_targets += 1
        _fsync_dir(paths.private_root, progress)
        try:
            os.unlink(paths.env_stage)
        except OSError as exc:
            raise ApplyFailure('private-env staging unlink failed after publication', progress) from exc
        _fsync_dir(paths.private_root, progress)
        final = _public_preflight(
            paths,
            source_uid=source_uid,
            source_gid=source_gid,
            root_uid=root_uid,
            root_gid=root_gid,
        )
        if final.status != STATUS_EXACT_READY:
            raise ApplyFailure('public-safe postcondition did not reach EXACT_READY', progress)
        _verify_exact_ready_protected(paths, plan, root_uid=root_uid, root_gid=root_gid)
        if _lstat(paths.state_stage) is not None or _lstat(paths.env_stage) is not None:
            raise ApplyFailure('staging postcondition failed', progress)
    except ApplyFailure:
        raise
    except MaterializationError as exc:
        raise ApplyFailure(str(exc), progress) from exc
    except OSError as exc:
        raise ApplyFailure('materialization failed after mutation began', progress) from exc
    return progress


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Fail-closed Hermes SIMPLE-DEPLOY host-prerequisite materialization v1'
    )
    parser.add_argument('--expected-source-sha', required=True)
    parser.add_argument('--apply', action='store_true')
    return parser


def _public_result(classification: Classification) -> dict[str, object]:
    return {
        'schema': PUBLIC_SCHEMA,
        'status': classification.status,
        'reasons': list(classification.reasons),
        'mutation_started': False,
        'protected_data_read': False,
        'protected_values_emitted': False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        _require_source_checkout(args.expected_source_sha)
        _validate_machine_contract()
        try:
            account = pwd.getpwnam(SOURCE_USER)
        except KeyError as exc:
            raise MaterializationError('fixed source owner account is absent') from exc
        source_home = Path(account.pw_dir)
        if not source_home.is_absolute():
            _fail('fixed source owner home is not absolute')
        paths = _production_paths(source_home)
        classification = _public_preflight(paths, source_uid=account.pw_uid, source_gid=account.pw_gid)
        if not args.apply:
            print(json.dumps(_public_result(classification), sort_keys=True, separators=(',', ':')))
            return 0 if classification.status != STATUS_PARTIAL_CONFLICT else 3
        if classification.status == STATUS_PARTIAL_CONFLICT:
            _fail('protected apply is blocked by PARTIAL_CONFLICT')
        plan = _prepare_protected(paths, source_uid=account.pw_uid, source_gid=account.pw_gid)
        if classification.status == STATUS_EXACT_READY:
            _verify_exact_ready_protected(paths, plan, root_uid=ROOT_UID, root_gid=ROOT_GID)
            print(json.dumps({
                'schema': PUBLIC_SCHEMA,
                'status': STATUS_EXACT_READY,
                'mutation_started': False,
                'protected_data_read': True,
                'protected_values_emitted': False,
            }, sort_keys=True, separators=(',', ':')))
            return 0
        progress = _apply(paths, plan, source_uid=account.pw_uid, source_gid=account.pw_gid)
        print(json.dumps({
            'schema': PUBLIC_SCHEMA,
            'status': STATUS_EXACT_READY,
            'mutation_started': progress.mutation_started,
            'parent_directories_created': progress.parent_directories_created,
            'staged_directories_created': progress.staged_directories_created,
            'staged_files_created': progress.staged_files_created,
            'published_targets': progress.published_targets,
            'protected_values_emitted': False,
        }, sort_keys=True, separators=(',', ':')))
        return 0
    except ApplyFailure as exc:
        print(json.dumps({
            'schema': PUBLIC_SCHEMA,
            'status': 'ERROR',
            'error': str(exc),
            'mutation_started': exc.progress.mutation_started,
            'published_targets': exc.progress.published_targets,
            'protected_values_emitted': False,
        }, sort_keys=True, separators=(',', ':')), file=sys.stderr)
        return 4
    except MaterializationError as exc:
        print(json.dumps({
            'schema': PUBLIC_SCHEMA,
            'status': 'ERROR',
            'error': str(exc),
            'mutation_started': False,
            'protected_values_emitted': False,
        }, sort_keys=True, separators=(',', ':')), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
