from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import dashboard_bootstrap_contract as c

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass
class MutationState:
    release_started: bool = False


def require_descriptor_safety() -> None:
    if os.name != "posix" or not Path("/proc/self/fd").exists():
        raise c.DashboardBootstrapError("descriptor-safe bootstrap requires Linux /proc/self/fd")
    for name in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK"):
        if not hasattr(os, name):
            raise c.DashboardBootstrapError(f"descriptor-safe bootstrap requires {name}")


def mode(st: os.stat_result) -> int:
    return stat.S_IMODE(st.st_mode)


def assert_owner_mode(st: os.stat_result, expected_mode: int, label: str) -> None:
    if st.st_uid != c.ROOT_UID or st.st_gid != c.ROOT_GID or mode(st) != expected_mode:
        raise c.DashboardBootstrapError(f"{label} metadata mismatch")


def open_abs_dir(path: Path, label: str) -> int:
    require_descriptor_safety()
    if not path.is_absolute():
        raise c.DashboardBootstrapError(f"{label} must be absolute")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            if not stat.S_ISDIR(os.fstat(nxt).st_mode):
                os.close(nxt)
                raise c.DashboardBootstrapError(f"{label} must be a real directory")
            os.close(fd)
            fd = nxt
        return fd
    except Exception:
        os.close(fd)
        raise


def safe_parts(path: str) -> tuple[str, ...]:
    if not path or path.startswith("/") or "\\" in path:
        raise c.DashboardBootstrapError("manifest path is invalid")
    parts = tuple(path.split("/"))
    if any(part in ("", ".", "..") for part in parts):
        raise c.DashboardBootstrapError("manifest path escapes reviewed root")
    if c.MANIFEST_MARKER in parts or "node_modules" in parts:
        raise c.DashboardBootstrapError("manifest path uses a reserved component")
    return parts


def open_rel_dir(root_fd: int, parts: tuple[str, ...], label: str) -> int:
    fd = os.dup(root_fd)
    try:
        for part in parts:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            if not stat.S_ISDIR(os.fstat(nxt).st_mode):
                os.close(nxt)
                raise c.DashboardBootstrapError(f"{label} must be a real directory")
            os.close(fd)
            fd = nxt
        return fd
    except Exception:
        os.close(fd)
        raise


def open_rel_file(root_fd: int, path: str, label: str) -> int:
    parts = safe_parts(path)
    parent = open_rel_dir(root_fd, parts[:-1], f"{label} parent")
    try:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise c.DashboardBootstrapError(f"{label} must be a regular file")
    return fd


def open_abs_file(path: Path, label: str) -> int:
    parent = open_abs_dir(path.parent, f"{label} parent")
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise c.DashboardBootstrapError(f"{label} must be a regular file")
    return fd


def read_bounded(fd: int, maximum: int, label: str) -> bytes:
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_size > maximum:
        raise c.DashboardBootstrapError(f"{label} exceeds reviewed size bound")
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(c.COPY_BUFFER_BYTES, maximum + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > maximum:
            raise c.DashboardBootstrapError(f"{label} exceeds reviewed size bound")
    if os.fstat(fd).st_size != total:
        raise c.DashboardBootstrapError(f"{label} changed while being read")
    return b"".join(chunks)


def strict_json(data: bytes) -> Any:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise c.DashboardBootstrapError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=hook)
    except c.DashboardBootstrapError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise c.DashboardBootstrapError("candidate manifest is not strict UTF-8 JSON") from exc


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def parse_manifest(value: Any, *, source_sha: str, expected_digest: str | None) -> c.CandidateManifest:
    keys = {"schema", "sourceSha", "releasePath", "nodeMajor", "hashAlgorithm", "fileCount", "totalBytes", "files", "candidateSha256"}
    if type(value) is not dict or set(value) != keys or FULL_SHA.fullmatch(source_sha) is None:
        raise c.DashboardBootstrapError("candidate manifest shape/source is invalid")
    if value["schema"] != c.MANIFEST_SCHEMA or value["sourceSha"] != source_sha:
        raise c.DashboardBootstrapError("candidate manifest source/schema mismatch")
    if value["releasePath"] != f"/opt/dashboard_RPi5/releases/{source_sha}" or value["nodeMajor"] != 24 or value["hashAlgorithm"] != "sha256":
        raise c.DashboardBootstrapError("candidate manifest release/runtime/hash mismatch")
    count, total, raw_files = value["fileCount"], value["totalBytes"], value["files"]
    if type(count) is not int or not 1 <= count <= c.MAX_MANIFEST_FILES:
        raise c.DashboardBootstrapError("candidate manifest file count exceeds reviewed bound")
    if type(total) is not int or not 0 <= total <= c.MAX_TOTAL_BYTES or type(raw_files) is not list or len(raw_files) != count:
        raise c.DashboardBootstrapError("candidate manifest aggregate bounds mismatch")
    entries: list[c.CandidateEntry] = []
    seen: set[str] = set()
    for raw in raw_files:
        if type(raw) is not dict or set(raw) != {"path", "bytes", "sha256"}:
            raise c.DashboardBootstrapError("candidate manifest file entry shape mismatch")
        path, size, digest = raw["path"], raw["bytes"], raw["sha256"]
        if type(path) is not str or path in seen:
            raise c.DashboardBootstrapError("candidate manifest path is invalid or duplicated")
        safe_parts(path)
        seen.add(path)
        if type(size) is not int or size < 0 or size > c.MAX_TOTAL_BYTES or type(digest) is not str or SHA256.fullmatch(digest) is None:
            raise c.DashboardBootstrapError("candidate manifest file metadata is invalid")
        entries.append(c.CandidateEntry(path, size, digest))
    if [entry.path for entry in entries] != sorted(entry.path for entry in entries) or sum(e.bytes for e in entries) != total:
        raise c.DashboardBootstrapError("candidate manifest ordering/total mismatch")
    if c.CONTROLLER_RELATIVE_PATH not in seen:
        raise c.DashboardBootstrapError("candidate manifest lacks controller")
    digest = value["candidateSha256"]
    if type(digest) is not str or SHA256.fullmatch(digest) is None:
        raise c.DashboardBootstrapError("candidate manifest digest is invalid")
    core = {key: value[key] for key in ("schema", "sourceSha", "releasePath", "nodeMajor", "hashAlgorithm", "fileCount", "totalBytes", "files")}
    if hashlib.sha256(canonical_json(core)).hexdigest() != digest:
        raise c.DashboardBootstrapError("candidate manifest self-digest mismatch")
    if expected_digest is not None and digest != expected_digest:
        raise c.DashboardBootstrapError("candidate manifest digest changed from reviewed preflight")
    return c.CandidateManifest(source_sha, digest, total, tuple(entries), value)


def load_candidate(paths: c.BootstrapPaths, expected_digest: str) -> c.CandidateManifest:
    fd = open_abs_file(paths.manifest_path, "candidate manifest")
    try:
        return parse_manifest(strict_json(read_bounded(fd, c.MAX_MANIFEST_BYTES, "candidate manifest")), source_sha=c.SOURCE_SHA, expected_digest=expected_digest)
    finally:
        os.close(fd)


def hash_fd(fd: int, expected_size: int, *, git_blob: bool = False) -> str:
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_size != expected_size:
        raise c.DashboardBootstrapError("descriptor size/type mismatch")
    digest = hashlib.sha1() if git_blob else hashlib.sha256()
    if git_blob:
        digest.update(f"blob {expected_size}\0".encode("ascii"))
    os.lseek(fd, 0, os.SEEK_SET)
    total = 0
    while True:
        chunk = os.read(fd, c.COPY_BUFFER_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > expected_size:
            raise c.DashboardBootstrapError("descriptor size changed during read")
        digest.update(chunk)
    if total != expected_size or os.fstat(fd).st_size != expected_size:
        raise c.DashboardBootstrapError("descriptor changed during read")
    return digest.hexdigest()


def verify_candidate(paths: c.BootstrapPaths, manifest: c.CandidateManifest) -> None:
    root = open_abs_dir(paths.candidate_root, "candidate root")
    try:
        for entry in manifest.files:
            fd = open_rel_file(root, entry.path, f"candidate source {entry.path}")
            try:
                if hash_fd(fd, entry.bytes) != entry.sha256:
                    raise c.DashboardBootstrapError(f"candidate source digest mismatch: {entry.path}")
                if entry.path == c.CONTROLLER_RELATIVE_PATH and hash_fd(fd, entry.bytes, git_blob=True) != c.HARDENED_CONTROLLER_BLOB:
                    raise c.DashboardBootstrapError("candidate hardened controller Git blob mismatch")
            finally:
                os.close(fd)
    finally:
        os.close(root)


def read_current(root_fd: int) -> str:
    st = os.stat("current", dir_fd=root_fd, follow_symlinks=False)
    if not stat.S_ISLNK(st.st_mode):
        raise c.DashboardBootstrapError("current pointer is not a symlink")
    target = os.readlink("current", dir_fd=root_fd)
    match = re.fullmatch(r"releases/([0-9a-f]{40})", target)
    if match is None:
        raise c.DashboardBootstrapError("current pointer target is outside reviewed release shape")
    return match.group(1)


def open_release(releases_fd: int, source_sha: str) -> int:
    if FULL_SHA.fullmatch(source_sha) is None:
        raise c.DashboardBootstrapError("release SHA is invalid")
    fd = os.open(source_sha, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=releases_fd)
    assert_owner_mode(os.fstat(fd), c.RELEASE_DIRECTORY_MODE, "release directory")
    return fd


def installed_manifest(release_fd: int, source_sha: str) -> c.CandidateManifest:
    fd = os.open(c.MANIFEST_MARKER, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=release_fd)
    try:
        assert_owner_mode(os.fstat(fd), c.MARKER_MODE, "installed manifest marker")
        value = strict_json(read_bounded(fd, c.MAX_MANIFEST_BYTES, "installed manifest marker"))
    finally:
        os.close(fd)
    return parse_manifest(value, source_sha=source_sha, expected_digest=None)


def collect_tree(fd: int, prefix: str = "") -> list[str]:
    files: list[str] = []
    for name in sorted(os.listdir(fd)):
        if not prefix and name == c.MANIFEST_MARKER:
            continue
        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
        rel = f"{prefix}/{name}" if prefix else name
        if stat.S_ISLNK(st.st_mode):
            raise c.DashboardBootstrapError(f"installed release symlink forbidden: {rel}")
        if stat.S_ISDIR(st.st_mode):
            assert_owner_mode(st, c.RELEASE_DIRECTORY_MODE, f"installed directory {rel}")
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                files.extend(collect_tree(child, rel))
            finally:
                os.close(child)
        elif stat.S_ISREG(st.st_mode):
            assert_owner_mode(st, c.RELEASE_FILE_MODE, f"installed file {rel}")
            files.append(rel)
        else:
            raise c.DashboardBootstrapError(f"installed special file forbidden: {rel}")
    return files


def verify_release(releases_fd: int, source_sha: str, controller_blob: str) -> c.CandidateManifest:
    release = open_release(releases_fd, source_sha)
    try:
        manifest = installed_manifest(release, source_sha)
        if sorted(collect_tree(release)) != [entry.path for entry in manifest.files]:
            raise c.DashboardBootstrapError("installed release tree does not match manifest")
        for entry in manifest.files:
            fd = open_rel_file(release, entry.path, f"installed file {entry.path}")
            try:
                assert_owner_mode(os.fstat(fd), c.RELEASE_FILE_MODE, f"installed file {entry.path}")
                if hash_fd(fd, entry.bytes) != entry.sha256:
                    raise c.DashboardBootstrapError(f"installed release digest mismatch: {entry.path}")
                if entry.path == c.CONTROLLER_RELATIVE_PATH and hash_fd(fd, entry.bytes, git_blob=True) != controller_blob:
                    raise c.DashboardBootstrapError("installed controller Git blob mismatch")
            finally:
                os.close(fd)
        return manifest
    finally:
        os.close(release)


def verify_current(paths: c.BootstrapPaths, expected_sha: str, controller_blob: str) -> None:
    root = open_abs_dir(paths.production_root, "production root")
    try:
        assert_owner_mode(os.fstat(root), c.RELEASE_DIRECTORY_MODE, "production root")
        releases = os.open("releases", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        try:
            assert_owner_mode(os.fstat(releases), c.RELEASE_DIRECTORY_MODE, "releases root")
            if read_current(root) != expected_sha:
                raise c.DashboardBootstrapError("current release changed from reviewed bootstrap baseline")
            verify_release(releases, expected_sha, controller_blob)
        finally:
            os.close(releases)
    finally:
        os.close(root)


def require_target_absent(paths: c.BootstrapPaths) -> None:
    root = open_abs_dir(paths.production_root, "production root")
    try:
        releases = os.open("releases", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        try:
            try:
                os.stat(c.SOURCE_SHA, dir_fd=releases, follow_symlinks=False)
            except FileNotFoundError:
                return
            raise c.DashboardBootstrapError("bootstrap target release already exists; reconcile before any retry")
        finally:
            os.close(releases)
    finally:
        os.close(root)


def destination_parent(release_fd: int, parts: tuple[str, ...]) -> int:
    fd = os.dup(release_fd)
    try:
        for part in parts:
            try:
                os.mkdir(part, c.RELEASE_DIRECTORY_MODE, dir_fd=fd)
                created = True
            except FileExistsError:
                created = False
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            if created:
                os.fchown(nxt, c.ROOT_UID, c.ROOT_GID)
                os.fchmod(nxt, c.RELEASE_DIRECTORY_MODE)
            else:
                assert_owner_mode(os.fstat(nxt), c.RELEASE_DIRECTORY_MODE, "release parent directory")
            os.close(fd)
            fd = nxt
        return fd
    except Exception:
        os.close(fd)
        raise


def copy_entry(candidate_fd: int, release_fd: int, entry: c.CandidateEntry) -> None:
    parts = safe_parts(entry.path)
    source = open_rel_file(candidate_fd, entry.path, f"candidate source {entry.path}")
    parent = destination_parent(release_fd, parts[:-1])
    dest: int | None = None
    try:
        if os.fstat(source).st_size != entry.bytes:
            raise c.DashboardBootstrapError("candidate source size changed before copy")
        dest = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, c.PREVERIFY_FILE_MODE, dir_fd=parent)
        digest = hashlib.sha256()
        os.lseek(source, 0, os.SEEK_SET)
        total = 0
        while True:
            chunk = os.read(source, c.COPY_BUFFER_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > entry.bytes:
                raise c.DashboardBootstrapError("candidate source grew during copy")
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(dest, view)
                if written <= 0:
                    raise c.DashboardBootstrapError("release destination write made no progress")
                view = view[written:]
        if total != entry.bytes or digest.hexdigest() != entry.sha256 or os.fstat(source).st_size != entry.bytes:
            raise c.DashboardBootstrapError("candidate source changed during copy")
        os.fsync(dest)
        os.fchown(dest, c.ROOT_UID, c.ROOT_GID)
        os.fchmod(dest, c.RELEASE_FILE_MODE)
    finally:
        if dest is not None:
            os.close(dest)
        os.close(parent)
        os.close(source)


def materialize(paths: c.BootstrapPaths, manifest: c.CandidateManifest, state: MutationState) -> None:
    root = open_abs_dir(paths.production_root, "production root")
    candidate = open_abs_dir(paths.candidate_root, "candidate root")
    releases = os.open("releases", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
    release: int | None = None
    try:
        assert_owner_mode(os.fstat(releases), c.RELEASE_DIRECTORY_MODE, "releases root")
        state.release_started = True
        os.mkdir(c.SOURCE_SHA, c.RELEASE_DIRECTORY_MODE, dir_fd=releases)
        release = os.open(c.SOURCE_SHA, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=releases)
        os.fchown(release, c.ROOT_UID, c.ROOT_GID)
        os.fchmod(release, c.RELEASE_DIRECTORY_MODE)
        for entry in manifest.files:
            copy_entry(candidate, release, entry)
        marker = os.open(c.MANIFEST_MARKER, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, c.MARKER_MODE, dir_fd=release)
        try:
            payload = canonical_json(manifest.raw) + b"\n"
            view = memoryview(payload)
            while view:
                written = os.write(marker, view)
                if written <= 0:
                    raise c.DashboardBootstrapError("manifest marker write made no progress")
                view = view[written:]
            os.fsync(marker)
            os.fchown(marker, c.ROOT_UID, c.ROOT_GID)
            os.fchmod(marker, c.MARKER_MODE)
        finally:
            os.close(marker)
    finally:
        if release is not None:
            os.close(release)
        os.close(releases)
        os.close(candidate)
        os.close(root)


def swap_current(paths: c.BootstrapPaths, state: MutationState) -> None:
    root = open_abs_dir(paths.production_root, "production root")
    try:
        temporary = f".current.bootstrap-{c.SOURCE_SHA}-{uuid.uuid4()}"
        os.symlink(f"releases/{c.SOURCE_SHA}", temporary, dir_fd=root)
        state.release_started = True
        os.rename(temporary, "current", src_dir_fd=root, dst_dir_fd=root)
    finally:
        os.close(root)


def acquire_lock(paths: c.BootstrapPaths) -> int:
    root = open_abs_dir(paths.production_root, "production root")
    fd: int | None = None
    try:
        try:
            fd = os.open(c.APPLY_LOCK_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root)
        except FileExistsError as exc:
            raise c.DashboardBootstrapError("bootstrap apply lock exists; inspect evidence before explicit cleanup") from exc
        try:
            os.fchown(fd, c.ROOT_UID, c.ROOT_GID)
            os.fchmod(fd, 0o600)
        except BaseException as exc:
            try:
                os.close(fd)
                fd = None
                os.unlink(c.APPLY_LOCK_NAME, dir_fd=root)
            except BaseException as cleanup_exc:
                raise c.DashboardBootstrapError("bootstrap lock initialization cleanup was incomplete") from cleanup_exc
            raise c.DashboardBootstrapError("bootstrap apply lock initialization failed") from exc
        return fd
    finally:
        os.close(root)


def remove_lock(paths: c.BootstrapPaths) -> None:
    root = open_abs_dir(paths.production_root, "production root")
    try:
        os.unlink(c.APPLY_LOCK_NAME, dir_fd=root)
    finally:
        os.close(root)
