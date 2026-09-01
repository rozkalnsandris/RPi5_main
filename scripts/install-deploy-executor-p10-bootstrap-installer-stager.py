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
from typing import Any

GIT = Path('/usr/bin/git')
ROOT = Path(__file__).resolve().parents[1]
SCRIPT_RELATIVE = 'scripts/install-deploy-executor-p10-bootstrap-installer-stager.py'

DASHBOARD_SOURCE_SHA = '5f7739348f56398d0ba301c9320e1de0062838fc'
EXPECTED_CANDIDATE_SHA256 = 'c5a2adef8f7242833094a1c0cb8a8074392312567deeddd1228dc46c16cff5c0'
PRESERVED_PARENT_NAME = 'p10-preflight-5f773934-20260901T074158Z-294325'
PRESERVED_CANDIDATE_NAME = 'candidate'
PRESERVED_MANIFEST_NAME = 'candidate.json'

HISTORICAL_CONTROLLER_BLOB = 'c501bea57c0d5c35e7961ae1f1e5593a02268661'
HARDENED_CONTROLLER_BLOB = 'c0566adb76e044632a4556dbefeb0f46839b4996'
CONTROLLER_RELATIVE_PATH = 'tools/production-release-controller.mjs'
MANIFEST_SCHEMA = 'dashboard-rpi5.production-candidate.v1'
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_FILES = 512
MAX_TOTAL_BYTES = 512 * 1024 * 1024
COPY_BUFFER_BYTES = 64 * 1024

STAGING_PARENT = Path('/var/lib/rozkalns-dashboard-controller-bootstrap')
STAGING_ROOT = STAGING_PARENT / DASHBOARD_SOURCE_SHA
STAGING_TMP_NAME = f'.{DASHBOARD_SOURCE_SHA}.installer-stager-partial'
STAGING_SOURCE_NAME = 'source'
STAGING_MANIFEST_NAME = 'candidate-manifest.json'

INSTALLED_ENTRYPOINT = Path('/usr/local/sbin/rozkalns-dashboard-controller-bootstrap')
INSTALLED_LIBRARY_ROOT = Path('/usr/local/lib/rozkalns-deploy-executor')
INSTALLED_PACKAGE_ROOT = INSTALLED_LIBRARY_ROOT / 'deploy_executor'

FULL_SHA = re.compile(r'^[0-9a-f]{40}$')
SHA256 = re.compile(r'^[0-9a-f]{64}$')

ROOT_UID = 0
ROOT_GID = 0
TRUSTED_DIRECTORY_MODE = 0o755
TRUSTED_MODULE_MODE = 0o644
TRUSTED_ENTRYPOINT_MODE = 0o755
STAGED_DIRECTORY_MODE = 0o755
STAGED_FILE_MODE = 0o644

INSTALLER_STAGER_MUTATION_BUDGET = (
    ('fixed-staging-root-materialization', 1),
    ('trusted-entrypoint-installation', 1),
    ('trusted-module-installation', 3),
)


class InstallerStagerError(RuntimeError):
    pass


@dataclass(frozen=True)
class TrustedTarget:
    source_path: str
    target_path: Path
    expected_blob: str
    mode: int


@dataclass(frozen=True)
class CandidateEntry:
    path: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class CandidateManifest:
    source_sha: str
    candidate_sha256: str
    total_bytes: int
    entries: tuple[CandidateEntry, ...]
    raw_bytes: bytes


TRUSTED_TARGETS = (
    TrustedTarget(
        'ops/bin/rozkalns-dashboard-controller-bootstrap',
        INSTALLED_ENTRYPOINT,
        'be46238c6bb7ed2aafef115db93830dc86a2ec44',
        TRUSTED_ENTRYPOINT_MODE,
    ),
    TrustedTarget(
        'ops/lib/deploy_executor/dashboard_bootstrap_contract.py',
        INSTALLED_PACKAGE_ROOT / 'dashboard_bootstrap_contract.py',
        'f446dfa5152531507312edcfcf66e8de5a73306d',
        TRUSTED_MODULE_MODE,
    ),
    TrustedTarget(
        'ops/lib/deploy_executor/dashboard_bootstrap_fs.py',
        INSTALLED_PACKAGE_ROOT / 'dashboard_bootstrap_fs.py',
        'd258026312f9b9109c98b934e287d04a97fb8328',
        TRUSTED_MODULE_MODE,
    ),
    TrustedTarget(
        'ops/lib/deploy_executor/dashboard_bootstrap.py',
        INSTALLED_PACKAGE_ROOT / 'dashboard_bootstrap.py',
        'b3e8d3995afb39820e64889a8f1b770fbcf70615',
        TRUSTED_MODULE_MODE,
    ),
)


def _git_blob(data: bytes) -> str:
    digest = hashlib.sha1()
    digest.update(f'blob {len(data)}\0'.encode('ascii'))
    digest.update(data)
    return digest.hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run_git(*args: str, capture: bool = False) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [str(GIT), '-C', str(ROOT), *args],
        check=False,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _require_exact_control_source(expected_sha: str) -> None:
    if FULL_SHA.fullmatch(expected_sha) is None:
        raise InstallerStagerError('expected control SHA must be lowercase 40-char hex')
    actual = _run_git('rev-parse', '--verify', 'HEAD', capture=True)
    if actual.returncode != 0 or actual.stdout.decode('ascii').strip() != expected_sha:
        raise InstallerStagerError('control source HEAD mismatch')
    clean = _run_git('diff', '--quiet', '--no-ext-diff', expected_sha, '--', SCRIPT_RELATIVE)
    if clean.returncode != 0:
        raise InstallerStagerError('installer/stager differs from exact expected control source')


def _reviewed_target_bytes(expected_sha: str, target: TrustedTarget) -> bytes:
    result = _run_git('show', f'{expected_sha}:{target.source_path}', capture=True)
    if result.returncode != 0:
        raise InstallerStagerError(f'reviewed source object unavailable: {target.source_path}')
    if _git_blob(result.stdout) != target.expected_blob:
        raise InstallerStagerError(f'reviewed source blob mismatch: {target.source_path}')
    return result.stdout


def _mode(st: os.stat_result) -> int:
    return stat.S_IMODE(st.st_mode)


def _require_safe_root_dir(path: Path, expected_mode: int | None = None) -> None:
    st = os.lstat(path)
    if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
        raise InstallerStagerError(f'expected real directory: {path}')
    if st.st_uid != ROOT_UID or st.st_gid != ROOT_GID or (_mode(st) & 0o022):
        raise InstallerStagerError(f'unsafe root-owned directory metadata: {path}')
    if expected_mode is not None and _mode(st) != expected_mode:
        raise InstallerStagerError(f'directory mode mismatch: {path}')


def _require_fixed_installer_parents() -> None:
    for path in (Path('/usr'), Path('/usr/local'), Path('/usr/local/sbin'), Path('/usr/local/lib')):
        _require_safe_root_dir(path)
    _require_safe_root_dir(INSTALLED_LIBRARY_ROOT, TRUSTED_DIRECTORY_MODE)
    _require_safe_root_dir(INSTALLED_PACKAGE_ROOT, TRUSTED_DIRECTORY_MODE)


def _require_targets_absent() -> None:
    for target in TRUSTED_TARGETS:
        try:
            os.lstat(target.target_path)
        except FileNotFoundError:
            continue
        raise InstallerStagerError(f'fixed trusted target already exists: {target.target_path}')


def _safe_parts(path: str) -> tuple[str, ...]:
    if not path or path.startswith('/') or '\\' in path:
        raise InstallerStagerError('candidate manifest path is invalid')
    parts = tuple(path.split('/'))
    if any(part in ('', '.', '..') for part in parts):
        raise InstallerStagerError('candidate manifest path escapes reviewed root')
    if '.dashboard-production-candidate.json' in parts or 'node_modules' in parts:
        raise InstallerStagerError('candidate manifest path uses a reserved component')
    return parts


def _strict_json(data: bytes) -> Any:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise InstallerStagerError(f'duplicate JSON key: {key}')
            result[key] = value
        return result

    try:
        return json.loads(data.decode('utf-8'), object_pairs_hook=hook)
    except InstallerStagerError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstallerStagerError('candidate manifest is not strict UTF-8 JSON') from exc


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def _parse_manifest(raw_bytes: bytes, *, expected_digest: str = EXPECTED_CANDIDATE_SHA256) -> CandidateManifest:
    if len(raw_bytes) > MAX_MANIFEST_BYTES:
        raise InstallerStagerError('candidate manifest exceeds reviewed size bound')
    value = _strict_json(raw_bytes)
    keys = {
        'schema', 'sourceSha', 'releasePath', 'nodeMajor', 'hashAlgorithm',
        'fileCount', 'totalBytes', 'files', 'candidateSha256',
    }
    if type(value) is not dict or set(value) != keys:
        raise InstallerStagerError('candidate manifest shape is invalid')
    if value['schema'] != MANIFEST_SCHEMA or value['sourceSha'] != DASHBOARD_SOURCE_SHA:
        raise InstallerStagerError('candidate manifest source/schema mismatch')
    if value['releasePath'] != f'/opt/dashboard_RPi5/releases/{DASHBOARD_SOURCE_SHA}':
        raise InstallerStagerError('candidate manifest release path mismatch')
    if value['nodeMajor'] != 24 or value['hashAlgorithm'] != 'sha256':
        raise InstallerStagerError('candidate manifest runtime/hash mismatch')
    count, total, files = value['fileCount'], value['totalBytes'], value['files']
    if type(count) is not int or not 1 <= count <= MAX_MANIFEST_FILES:
        raise InstallerStagerError('candidate manifest file count exceeds reviewed bound')
    if type(total) is not int or not 0 <= total <= MAX_TOTAL_BYTES:
        raise InstallerStagerError('candidate manifest total bytes exceeds reviewed bound')
    if type(files) is not list or len(files) != count:
        raise InstallerStagerError('candidate manifest file list mismatch')

    entries: list[CandidateEntry] = []
    seen: set[str] = set()
    for item in files:
        if type(item) is not dict or set(item) != {'path', 'bytes', 'sha256'}:
            raise InstallerStagerError('candidate manifest file entry shape mismatch')
        path, size, digest = item['path'], item['bytes'], item['sha256']
        if type(path) is not str or path in seen:
            raise InstallerStagerError('candidate manifest path is invalid or duplicated')
        _safe_parts(path)
        seen.add(path)
        if type(size) is not int or size < 0 or size > MAX_TOTAL_BYTES:
            raise InstallerStagerError('candidate manifest file size is invalid')
        if type(digest) is not str or SHA256.fullmatch(digest) is None:
            raise InstallerStagerError('candidate manifest file digest is invalid')
        entries.append(CandidateEntry(path, size, digest))
    if [entry.path for entry in entries] != sorted(entry.path for entry in entries):
        raise InstallerStagerError('candidate manifest files are not deterministically sorted')
    if sum(entry.bytes for entry in entries) != total:
        raise InstallerStagerError('candidate manifest aggregate size mismatch')
    if CONTROLLER_RELATIVE_PATH not in seen:
        raise InstallerStagerError('candidate manifest lacks hardened controller')

    digest = value['candidateSha256']
    if type(digest) is not str or SHA256.fullmatch(digest) is None:
        raise InstallerStagerError('candidate manifest digest is invalid')
    core = {key: value[key] for key in (
        'schema', 'sourceSha', 'releasePath', 'nodeMajor', 'hashAlgorithm',
        'fileCount', 'totalBytes', 'files',
    )}
    if _sha256(_canonical_json(core)) != digest:
        raise InstallerStagerError('candidate manifest self-digest mismatch')
    if digest != expected_digest:
        raise InstallerStagerError('candidate manifest digest differs from reviewed preflight')
    return CandidateManifest(DASHBOARD_SOURCE_SHA, digest, total, tuple(entries), raw_bytes)


def _read_fd_exact(fd: int, expected_size: int) -> bytes:
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_size != expected_size:
        raise InstallerStagerError('candidate descriptor size/type mismatch')
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, COPY_BUFFER_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > expected_size:
            raise InstallerStagerError('candidate descriptor changed while reading')
        chunks.append(chunk)
    if total != expected_size or os.fstat(fd).st_size != expected_size:
        raise InstallerStagerError('candidate descriptor changed while reading')
    return b''.join(chunks)


def _open_rel_dir(root_fd: int, parts: tuple[str, ...]) -> int:
    fd = os.dup(root_fd)
    try:
        for part in parts:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            if not stat.S_ISDIR(os.fstat(nxt).st_mode):
                os.close(nxt)
                raise InstallerStagerError('candidate path component is not a real directory')
            os.close(fd)
            fd = nxt
        return fd
    except Exception:
        os.close(fd)
        raise


def _open_rel_file(root_fd: int, relative_path: str) -> int:
    parts = _safe_parts(relative_path)
    parent = _open_rel_dir(root_fd, parts[:-1])
    try:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise InstallerStagerError(f'candidate entry is not a regular file: {relative_path}')
    return fd


def _preserved_root_fd() -> int:
    if not hasattr(os, 'O_NOFOLLOW') or not Path('/proc/self/fd').exists():
        raise InstallerStagerError('descriptor-safe Linux filesystem support is required')
    fd = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        resolved = Path(os.readlink(f'/proc/self/fd/{fd}'))
        if resolved.name != PRESERVED_PARENT_NAME:
            raise InstallerStagerError('cwd is not the exact reviewed preserved preflight parent')
        st = os.fstat(fd)
        if not stat.S_ISDIR(st.st_mode) or (_mode(st) & 0o022):
            raise InstallerStagerError('preserved preflight parent metadata is unsafe')
        return fd
    except Exception:
        os.close(fd)
        raise


def _load_preserved_candidate(parent_fd: int) -> tuple[int, CandidateManifest]:
    manifest_fd = os.open(PRESERVED_MANIFEST_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd)
    try:
        st = os.fstat(manifest_fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_MANIFEST_BYTES:
            raise InstallerStagerError('preserved candidate manifest is not a bounded regular file')
        raw = _read_fd_exact(manifest_fd, st.st_size)
    finally:
        os.close(manifest_fd)
    manifest = _parse_manifest(raw)
    candidate_fd = os.open(PRESERVED_CANDIDATE_NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    if not stat.S_ISDIR(os.fstat(candidate_fd).st_mode):
        os.close(candidate_fd)
        raise InstallerStagerError('preserved candidate root is not a real directory')
    return candidate_fd, manifest


def _verify_candidate(candidate_fd: int, manifest: CandidateManifest) -> None:
    for entry in manifest.entries:
        fd = _open_rel_file(candidate_fd, entry.path)
        try:
            data = _read_fd_exact(fd, entry.bytes)
            if _sha256(data) != entry.sha256:
                raise InstallerStagerError(f'preserved candidate digest mismatch: {entry.path}')
            if entry.path == CONTROLLER_RELATIVE_PATH and _git_blob(data) != HARDENED_CONTROLLER_BLOB:
                raise InstallerStagerError('preserved candidate hardened controller Git blob mismatch')
        finally:
            os.close(fd)


def _require_staging_prestate() -> None:
    if STAGING_ROOT.exists() or (STAGING_PARENT / STAGING_TMP_NAME).exists():
        raise InstallerStagerError('fixed bootstrap staging target/partial path already exists')
    cursor = STAGING_PARENT
    missing: list[Path] = []
    while not cursor.exists():
        missing.append(cursor)
        if cursor == Path('/'):
            raise InstallerStagerError('unable to find staging parent anchor')
        cursor = cursor.parent
    _require_safe_root_dir(cursor)
    for ancestor in cursor.parents:
        if ancestor == Path('/'):
            break
        _require_safe_root_dir(ancestor)
    if missing and cursor != Path('/var/lib'):
        raise InstallerStagerError('fixed staging parent is missing below an unexpected anchor')


def _mkdir_fixed_chain(path: Path) -> None:
    parts = path.parts[1:]
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        built = Path('/')
        for part in parts:
            built = built / part
            try:
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                os.mkdir(part, STAGED_DIRECTORY_MODE, dir_fd=fd)
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.fchmod(nxt, STAGED_DIRECTORY_MODE)
                os.fchown(nxt, ROOT_UID, ROOT_GID)
                os.fsync(nxt)
            st = os.fstat(nxt)
            if not stat.S_ISDIR(st.st_mode) or st.st_uid != ROOT_UID or st.st_gid != ROOT_GID or (_mode(st) & 0o022):
                os.close(nxt)
                raise InstallerStagerError(f'unsafe fixed staging path component: {built}')
            os.close(fd)
            fd = nxt
    finally:
        os.close(fd)


def _mkdir_rel_chain(root_fd: int, parts: tuple[str, ...]) -> int:
    fd = os.dup(root_fd)
    try:
        for part in parts:
            try:
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                os.mkdir(part, STAGED_DIRECTORY_MODE, dir_fd=fd)
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.fchmod(nxt, STAGED_DIRECTORY_MODE)
                os.fchown(nxt, ROOT_UID, ROOT_GID)
            st = os.fstat(nxt)
            if not stat.S_ISDIR(st.st_mode) or st.st_uid != ROOT_UID or st.st_gid != ROOT_GID or _mode(st) != STAGED_DIRECTORY_MODE:
                os.close(nxt)
                raise InstallerStagerError('staging directory metadata mismatch')
            os.close(fd)
            fd = nxt
        return fd
    except Exception:
        os.close(fd)
        raise


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    offset = 0
    while offset < len(view):
        written = os.write(fd, view[offset:])
        if written <= 0:
            raise InstallerStagerError('short write while materializing reviewed bytes')
        offset += written


def _create_file_at(parent_fd: int, name: str, data: bytes, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(name, flags, mode, dir_fd=parent_fd)
    try:
        _write_all(fd, data)
        os.fchmod(fd, mode)
        os.fchown(fd, ROOT_UID, ROOT_GID)
        os.fsync(fd)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != ROOT_UID or st.st_gid != ROOT_GID or _mode(st) != mode:
            raise InstallerStagerError('materialized file metadata mismatch')
    finally:
        os.close(fd)


def _materialize_staging(candidate_fd: int, manifest: CandidateManifest, *, staging_parent: Path = STAGING_PARENT) -> Path:
    _mkdir_fixed_chain(staging_parent)
    parent_fd = os.open(staging_parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        final_name = DASHBOARD_SOURCE_SHA
        temp_name = STAGING_TMP_NAME
        for name in (final_name, temp_name):
            try:
                os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise InstallerStagerError('fixed bootstrap staging target/partial path already exists')
        os.mkdir(temp_name, STAGED_DIRECTORY_MODE, dir_fd=parent_fd)
        tmp_fd = os.open(temp_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        try:
            os.fchmod(tmp_fd, STAGED_DIRECTORY_MODE)
            os.fchown(tmp_fd, ROOT_UID, ROOT_GID)
            os.mkdir(STAGING_SOURCE_NAME, STAGED_DIRECTORY_MODE, dir_fd=tmp_fd)
            source_out_fd = os.open(STAGING_SOURCE_NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=tmp_fd)
            try:
                os.fchmod(source_out_fd, STAGED_DIRECTORY_MODE)
                os.fchown(source_out_fd, ROOT_UID, ROOT_GID)
                for entry in manifest.entries:
                    src_fd = _open_rel_file(candidate_fd, entry.path)
                    try:
                        data = _read_fd_exact(src_fd, entry.bytes)
                    finally:
                        os.close(src_fd)
                    if _sha256(data) != entry.sha256:
                        raise InstallerStagerError(f'candidate changed before staging: {entry.path}')
                    parts = _safe_parts(entry.path)
                    dst_parent = _mkdir_rel_chain(source_out_fd, parts[:-1])
                    try:
                        _create_file_at(dst_parent, parts[-1], data, STAGED_FILE_MODE)
                    finally:
                        os.close(dst_parent)
                os.fsync(source_out_fd)
            finally:
                os.close(source_out_fd)
            _create_file_at(tmp_fd, STAGING_MANIFEST_NAME, manifest.raw_bytes, STAGED_FILE_MODE)
            os.fsync(tmp_fd)
        finally:
            os.close(tmp_fd)
        os.rename(temp_name, final_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    return staging_parent / DASHBOARD_SOURCE_SHA


def _verify_materialized_staging(manifest: CandidateManifest, *, staging_root: Path = STAGING_ROOT) -> None:
    root_fd = os.open(staging_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        st = os.fstat(root_fd)
        if st.st_uid != ROOT_UID or st.st_gid != ROOT_GID or _mode(st) != STAGED_DIRECTORY_MODE:
            raise InstallerStagerError('fixed staging root metadata mismatch')
        manifest_fd = os.open(STAGING_MANIFEST_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
        try:
            raw = _read_fd_exact(manifest_fd, len(manifest.raw_bytes))
            if raw != manifest.raw_bytes:
                raise InstallerStagerError('fixed staging manifest differs from preserved evidence')
        finally:
            os.close(manifest_fd)
        source_fd = os.open(STAGING_SOURCE_NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        try:
            _verify_candidate(source_fd, manifest)
        finally:
            os.close(source_fd)
    finally:
        os.close(root_fd)


def _create_trusted_target(target: TrustedTarget, data: bytes) -> None:
    parent_fd = os.open(target.target_path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _create_file_at(parent_fd, target.target_path.name, data, target.mode)
    finally:
        os.close(parent_fd)
    st = os.lstat(target.target_path)
    if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
        raise InstallerStagerError(f'installed trusted target is not regular: {target.target_path}')
    if st.st_uid != ROOT_UID or st.st_gid != ROOT_GID or _mode(st) != target.mode:
        raise InstallerStagerError(f'installed trusted target metadata mismatch: {target.target_path}')
    if _git_blob(target.target_path.read_bytes()) != target.expected_blob:
        raise InstallerStagerError(f'installed trusted target blob mismatch: {target.target_path}')


def _preflight(expected_sha: str) -> tuple[int, CandidateManifest, tuple[tuple[TrustedTarget, bytes], ...]]:
    _require_exact_control_source(expected_sha)
    _require_fixed_installer_parents()
    _require_targets_absent()
    _require_staging_prestate()
    parent_fd = _preserved_root_fd()
    candidate_fd = -1
    try:
        candidate_fd, manifest = _load_preserved_candidate(parent_fd)
        _verify_candidate(candidate_fd, manifest)
        reviewed = tuple((target, _reviewed_target_bytes(expected_sha, target)) for target in TRUSTED_TARGETS)
        return candidate_fd, manifest, reviewed
    except Exception:
        if candidate_fd >= 0:
            os.close(candidate_fd)
        raise
    finally:
        os.close(parent_fd)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            'Preflight, and only with --apply materialize, the fixed P10 bootstrap trust anchor '
            'and exact preserved Dashboard candidate staging. Source merge never authorizes --apply.'
        )
    )
    parser.add_argument('expected_sha', help='exact reviewed RPi5_main control source SHA')
    parser.add_argument('--apply', action='store_true', help='perform the separately owner-authorized installer/stager mutation')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    candidate_fd = -1
    try:
        candidate_fd, manifest, reviewed = _preflight(args.expected_sha)
        if not args.apply:
            print('P10_BOOTSTRAP_INSTALLER_STAGER_PREFLIGHT=PASS')
            print(f'control_source_sha={args.expected_sha}')
            print(f'dashboard_source_sha={DASHBOARD_SOURCE_SHA}')
            print(f'candidate_sha256={manifest.candidate_sha256}')
            print('MUTATION=NO')
            return 0
        if os.geteuid() != 0:
            raise InstallerStagerError('P10 bootstrap installer/stager --apply requires root')

        # Repeat every read-only predicate immediately before the first authorized mutation.
        os.close(candidate_fd)
        candidate_fd = -1
        candidate_fd, manifest, reviewed = _preflight(args.expected_sha)

        _materialize_staging(candidate_fd, manifest)
        _verify_materialized_staging(manifest)
        for target, data in reviewed:
            _create_trusted_target(target, data)
        _verify_materialized_staging(manifest)
        for target, _ in reviewed:
            st = os.lstat(target.target_path)
            if st.st_uid != ROOT_UID or st.st_gid != ROOT_GID or _mode(st) != target.mode:
                raise InstallerStagerError(f'post-install trusted target metadata mismatch: {target.target_path}')
            if _git_blob(target.target_path.read_bytes()) != target.expected_blob:
                raise InstallerStagerError(f'post-install trusted target blob mismatch: {target.target_path}')
    except InstallerStagerError as exc:
        print(f'P10_BOOTSTRAP_INSTALLER_STAGER=STOP reason={exc}', file=sys.stderr)
        return 1
    finally:
        if candidate_fd >= 0:
            os.close(candidate_fd)

    print('P10_BOOTSTRAP_INSTALLER_STAGER=PASS')
    print(f'control_source_sha={args.expected_sha}')
    print(f'dashboard_source_sha={DASHBOARD_SOURCE_SHA}')
    print(f'candidate_sha256={manifest.candidate_sha256}')
    print('TRUST_ANCHOR_FILES_INSTALLED=4')
    print('MUTATION_BUDGET=fixed_staging_root:1,trusted_entrypoint:1,trusted_modules:3')
    print('FIXED_STAGING_TREES_MATERIALIZED=1')
    print('PRODUCTION_RELEASES_MATERIALIZED=0')
    print('CURRENT_POINTER_SWAPS=0')
    print('P10_PLAN_EXECUTED=0')
    print('P10_APPLY_EXECUTED=0')
    print('PACKAGE_SERVICE_SYSTEMD_DOCKER_NETWORK_CREDENTIAL_MUTATION=NO')
    print('ROLLBACK_PATH=NO')
    print('RETRY_PATH=NO')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
