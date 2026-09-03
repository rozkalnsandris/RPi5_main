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
import sys
from typing import Any

OPERATION_ID = "dashboard-rpi5.production-release.v1"
REVIEWED_SOURCE_SHA = "066b9a24008dd57439f9e66eae198416c4dfc590"
MANIFEST_SCHEMA = "dashboard-rpi5.production-candidate.v1"
MANIFEST_NAME = "candidate-manifest.json"
SOURCE_NAME = "source"
INPUT_BASE = Path("/var/lib/rozkalns-dashboard-candidate-input")
INPUT_ROOT = INPUT_BASE / REVIEWED_SOURCE_SHA
INPUT_SOURCE = INPUT_ROOT / SOURCE_NAME
INPUT_MANIFEST = INPUT_ROOT / MANIFEST_NAME
STAGING_BASE = Path("/var/lib/rozkalns-dashboard-release-candidates")
STAGING_ROOT = STAGING_BASE / REVIEWED_SOURCE_SHA
STAGING_SOURCE = STAGING_ROOT / SOURCE_NAME
STAGING_MANIFEST = STAGING_ROOT / MANIFEST_NAME
PARTIAL_NAME = f".{REVIEWED_SOURCE_SHA}.candidate-stager-partial"
ACK = "I_AUTHORIZED_DASHBOARD_RPI5_CANDIDATE_STAGING_066B9A24"

MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_FILES = 512
MAX_TOTAL_BYTES = 512 * 1024 * 1024
COPY_BUFFER_BYTES = 64 * 1024
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
INPUT_BASE_MODE = 0o755
INPUT_DIRECTORY_MODE = 0o555
INPUT_FILE_MODE = 0o444
OUTPUT_DIRECTORY_MODE = 0o755
OUTPUT_FILE_MODE = 0o644
ROOT_UID = 0
ROOT_GID = 0

STAGING_MUTATION_BUDGET = (
    ("staging-namespace-root-create", 1),
    ("staging-candidate-partial-root-create", 1),
    ("staging-file-materialization", MAX_MANIFEST_FILES),
    ("staging-manifest-materialization", 1),
    ("staging-final-rename", 1),
)


class CandidateStagerError(RuntimeError):
    pass


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


def _mode(st: os.stat_result) -> int:
    return stat.S_IMODE(st.st_mode)


def _require_descriptor_safety() -> None:
    if os.name != "posix" or not Path("/proc/self/fd").exists():
        raise CandidateStagerError("descriptor-safe staging requires Linux /proc/self/fd")
    for name in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK"):
        if not hasattr(os, name):
            raise CandidateStagerError(f"descriptor-safe staging requires {name}")


def _safe_parts(path: str) -> tuple[str, ...]:
    if not path or path.startswith("/") or "\\" in path:
        raise CandidateStagerError("candidate manifest path is invalid")
    parts = tuple(path.split("/"))
    if any(part in ("", ".", "..") for part in parts):
        raise CandidateStagerError("candidate manifest path escapes reviewed root")
    if MANIFEST_NAME in parts or ".dashboard-production-candidate.json" in parts or "node_modules" in parts:
        raise CandidateStagerError("candidate manifest path uses a reserved component")
    return parts


def _strict_json(data: bytes) -> Any:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CandidateStagerError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=hook)
    except CandidateStagerError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidateStagerError("candidate manifest is not strict UTF-8 JSON") from exc


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _parse_manifest(raw_bytes: bytes, *, expected_digest: str) -> CandidateManifest:
    if type(expected_digest) is not str or SHA256.fullmatch(expected_digest) is None:
        raise CandidateStagerError("expected candidate digest must be exact lowercase SHA-256")
    if len(raw_bytes) > MAX_MANIFEST_BYTES:
        raise CandidateStagerError("candidate manifest exceeds reviewed size bound")
    value = _strict_json(raw_bytes)
    keys = {
        "schema", "sourceSha", "releasePath", "nodeMajor", "hashAlgorithm",
        "fileCount", "totalBytes", "files", "candidateSha256",
    }
    if type(value) is not dict or set(value) != keys:
        raise CandidateStagerError("candidate manifest shape is invalid")
    if value["schema"] != MANIFEST_SCHEMA or value["sourceSha"] != REVIEWED_SOURCE_SHA:
        raise CandidateStagerError("candidate manifest source/schema mismatch")
    if FULL_SHA.fullmatch(value["sourceSha"]) is None:
        raise CandidateStagerError("candidate manifest source SHA is invalid")
    if value["releasePath"] != f"/opt/dashboard_RPi5/releases/{REVIEWED_SOURCE_SHA}":
        raise CandidateStagerError("candidate manifest release path mismatch")
    if value["nodeMajor"] != 24 or value["hashAlgorithm"] != "sha256":
        raise CandidateStagerError("candidate manifest runtime/hash mismatch")

    count, total, files = value["fileCount"], value["totalBytes"], value["files"]
    if type(count) is not int or not 1 <= count <= MAX_MANIFEST_FILES:
        raise CandidateStagerError("candidate manifest file count exceeds reviewed bound")
    if type(total) is not int or not 0 <= total <= MAX_TOTAL_BYTES:
        raise CandidateStagerError("candidate manifest total bytes exceeds reviewed bound")
    if type(files) is not list or len(files) != count:
        raise CandidateStagerError("candidate manifest file list mismatch")

    entries: list[CandidateEntry] = []
    seen: set[str] = set()
    for item in files:
        if type(item) is not dict or set(item) != {"path", "bytes", "sha256"}:
            raise CandidateStagerError("candidate manifest file entry shape mismatch")
        path, size, digest = item["path"], item["bytes"], item["sha256"]
        if type(path) is not str or path in seen:
            raise CandidateStagerError("candidate manifest path is invalid or duplicated")
        _safe_parts(path)
        seen.add(path)
        if type(size) is not int or size < 0 or size > MAX_TOTAL_BYTES:
            raise CandidateStagerError("candidate manifest file size is invalid")
        if type(digest) is not str or SHA256.fullmatch(digest) is None:
            raise CandidateStagerError("candidate manifest file digest is invalid")
        entries.append(CandidateEntry(path, size, digest))

    if [entry.path for entry in entries] != sorted(entry.path for entry in entries):
        raise CandidateStagerError("candidate manifest files are not deterministically sorted")
    if sum(entry.bytes for entry in entries) != total:
        raise CandidateStagerError("candidate manifest aggregate size mismatch")

    digest = value["candidateSha256"]
    if type(digest) is not str or SHA256.fullmatch(digest) is None:
        raise CandidateStagerError("candidate manifest digest is invalid")
    core = {key: value[key] for key in (
        "schema", "sourceSha", "releasePath", "nodeMajor", "hashAlgorithm",
        "fileCount", "totalBytes", "files",
    )}
    if hashlib.sha256(_canonical_json(core)).hexdigest() != digest:
        raise CandidateStagerError("candidate manifest self-digest mismatch")
    if digest != expected_digest:
        raise CandidateStagerError("candidate manifest digest differs from LIVE binding")
    return CandidateManifest(REVIEWED_SOURCE_SHA, digest, total, tuple(entries), raw_bytes)


def _open_abs_dir(path: Path, label: str) -> int:
    _require_descriptor_safety()
    if not path.is_absolute():
        raise CandidateStagerError(f"{label} must be absolute")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            if not stat.S_ISDIR(os.fstat(nxt).st_mode):
                os.close(nxt)
                raise CandidateStagerError(f"{label} must be a real directory")
            os.close(fd)
            fd = nxt
        return fd
    except Exception:
        os.close(fd)
        raise


def _open_rel_dir(root_fd: int, parts: tuple[str, ...], label: str) -> int:
    fd = os.dup(root_fd)
    try:
        for part in parts:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            if not stat.S_ISDIR(os.fstat(nxt).st_mode):
                os.close(nxt)
                raise CandidateStagerError(f"{label} must be a real directory")
            os.close(fd)
            fd = nxt
        return fd
    except Exception:
        os.close(fd)
        raise


def _open_rel_file(root_fd: int, relative_path: str, label: str) -> int:
    parts = _safe_parts(relative_path)
    parent = _open_rel_dir(root_fd, parts[:-1], f"{label} parent")
    try:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise CandidateStagerError(f"{label} must be a regular file")
    return fd


def _read_bounded(fd: int, maximum: int, label: str) -> bytes:
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_size > maximum:
        raise CandidateStagerError(f"{label} exceeds reviewed size bound")
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(COPY_BUFFER_BYTES, maximum + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > maximum:
            raise CandidateStagerError(f"{label} exceeds reviewed size bound")
        chunks.append(chunk)
    if os.fstat(fd).st_size != total:
        raise CandidateStagerError(f"{label} changed while being read")
    return b"".join(chunks)


def _assert_metadata(st: os.stat_result, *, uid: int, gid: int, mode: int, label: str, directory: bool) -> None:
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(st.st_mode) or st.st_uid != uid or st.st_gid != gid or _mode(st) != mode:
        raise CandidateStagerError(f"{label} metadata mismatch")


def _collect_input_tree(fd: int, *, uid: int, gid: int, prefix: str = "") -> list[str]:
    files: list[str] = []
    for name in sorted(os.listdir(fd)):
        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
        rel = f"{prefix}/{name}" if prefix else name
        if stat.S_ISLNK(st.st_mode):
            raise CandidateStagerError(f"candidate input symlink forbidden: {rel}")
        if stat.S_ISDIR(st.st_mode):
            _assert_metadata(st, uid=uid, gid=gid, mode=INPUT_DIRECTORY_MODE, label=f"candidate input directory {rel}", directory=True)
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                files.extend(_collect_input_tree(child, uid=uid, gid=gid, prefix=rel))
            finally:
                os.close(child)
        elif stat.S_ISREG(st.st_mode):
            _assert_metadata(st, uid=uid, gid=gid, mode=INPUT_FILE_MODE, label=f"candidate input file {rel}", directory=False)
            files.append(rel)
        else:
            raise CandidateStagerError(f"candidate input special file forbidden: {rel}")
    return files


def _hash_fd(fd: int, expected_size: int, label: str) -> str:
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_size != expected_size:
        raise CandidateStagerError(f"{label} size/type mismatch")
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    total = 0
    while True:
        chunk = os.read(fd, COPY_BUFFER_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > expected_size:
            raise CandidateStagerError(f"{label} changed while reading")
        digest.update(chunk)
    if total != expected_size or os.fstat(fd).st_size != expected_size:
        raise CandidateStagerError(f"{label} changed while reading")
    return digest.hexdigest()


def _open_verified_input_root(*, uid: int, gid: int) -> int:
    base = _open_abs_dir(INPUT_BASE, "candidate input base")
    try:
        _assert_metadata(os.fstat(base), uid=uid, gid=gid, mode=INPUT_BASE_MODE, label="candidate input base", directory=True)
        root = os.open(REVIEWED_SOURCE_SHA, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=base)
    finally:
        os.close(base)
    try:
        _assert_metadata(os.fstat(root), uid=uid, gid=gid, mode=INPUT_DIRECTORY_MODE, label="candidate input root", directory=True)
    except Exception:
        os.close(root)
        raise
    return root


def _load_and_verify_input(*, expected_digest: str, uid: int, gid: int) -> CandidateManifest:
    root = _open_verified_input_root(uid=uid, gid=gid)
    try:
        manifest_fd = os.open(MANIFEST_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
        try:
            _assert_metadata(os.fstat(manifest_fd), uid=uid, gid=gid, mode=INPUT_FILE_MODE, label="candidate input manifest", directory=False)
            raw = _read_bounded(manifest_fd, MAX_MANIFEST_BYTES, "candidate input manifest")
        finally:
            os.close(manifest_fd)
        manifest = _parse_manifest(raw, expected_digest=expected_digest)
        source_fd = os.open(SOURCE_NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        try:
            _assert_metadata(os.fstat(source_fd), uid=uid, gid=gid, mode=INPUT_DIRECTORY_MODE, label="candidate input source", directory=True)
            actual = _collect_input_tree(source_fd, uid=uid, gid=gid)
            expected = [entry.path for entry in manifest.entries]
            if actual != expected:
                raise CandidateStagerError("candidate input tree does not exactly match manifest")
            for entry in manifest.entries:
                fd = _open_rel_file(source_fd, entry.path, f"candidate input {entry.path}")
                try:
                    _assert_metadata(os.fstat(fd), uid=uid, gid=gid, mode=INPUT_FILE_MODE, label=f"candidate input {entry.path}", directory=False)
                    if _hash_fd(fd, entry.bytes, f"candidate input {entry.path}") != entry.sha256:
                        raise CandidateStagerError(f"candidate input digest mismatch: {entry.path}")
                finally:
                    os.close(fd)
        finally:
            os.close(source_fd)
        return manifest
    finally:
        os.close(root)


def _require_root_owned_dir(fd: int, label: str, mode: int = OUTPUT_DIRECTORY_MODE) -> None:
    _assert_metadata(os.fstat(fd), uid=ROOT_UID, gid=ROOT_GID, mode=mode, label=label, directory=True)


def _open_or_create_staging_base() -> int:
    parent = _open_abs_dir(STAGING_BASE.parent, "staging namespace parent")
    try:
        _require_root_owned_dir(parent, "staging namespace parent")
        created = False
        try:
            os.mkdir(STAGING_BASE.name, 0o700, dir_fd=parent)
            created = True
        except FileExistsError:
            pass
        base = os.open(STAGING_BASE.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        if created:
            os.fchown(base, ROOT_UID, ROOT_GID)
            os.fchmod(base, OUTPUT_DIRECTORY_MODE)
    finally:
        os.close(parent)
    _require_root_owned_dir(base, "staging namespace root")
    return base


def _ensure_output_parent(root_fd: int, parts: tuple[str, ...]) -> int:
    fd = os.dup(root_fd)
    try:
        for part in parts:
            created = False
            try:
                os.mkdir(part, 0o700, dir_fd=fd)
                created = True
            except FileExistsError:
                pass
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            if created:
                os.fchown(nxt, ROOT_UID, ROOT_GID)
                os.fchmod(nxt, OUTPUT_DIRECTORY_MODE)
            _require_root_owned_dir(nxt, f"staging directory {part}")
            os.close(fd)
            fd = nxt
        return fd
    except Exception:
        os.close(fd)
        raise


def _copy_verified_file(input_root_fd: int, output_root_fd: int, entry: CandidateEntry, *, uid: int, gid: int) -> None:
    source_fd = _open_rel_file(input_root_fd, entry.path, f"candidate input {entry.path}")
    try:
        _assert_metadata(os.fstat(source_fd), uid=uid, gid=gid, mode=INPUT_FILE_MODE, label=f"candidate input {entry.path}", directory=False)
        parts = _safe_parts(entry.path)
        parent = _ensure_output_parent(output_root_fd, parts[:-1])
        try:
            dest_fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, OUTPUT_FILE_MODE, dir_fd=parent)
        finally:
            os.close(parent)
        try:
            digest = hashlib.sha256()
            os.lseek(source_fd, 0, os.SEEK_SET)
            total = 0
            while True:
                chunk = os.read(source_fd, COPY_BUFFER_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > entry.bytes:
                    raise CandidateStagerError(f"candidate input changed while staging: {entry.path}")
                digest.update(chunk)
                view = memoryview(chunk)
                while view:
                    written = os.write(dest_fd, view)
                    view = view[written:]
            if total != entry.bytes or os.fstat(source_fd).st_size != entry.bytes or digest.hexdigest() != entry.sha256:
                raise CandidateStagerError(f"candidate input digest drift while staging: {entry.path}")
            os.fchmod(dest_fd, OUTPUT_FILE_MODE)
            os.fchown(dest_fd, ROOT_UID, ROOT_GID)
            os.fsync(dest_fd)
        finally:
            os.close(dest_fd)
    finally:
        os.close(source_fd)


def _write_manifest(output_root_fd: int, manifest: CandidateManifest) -> None:
    fd = os.open(MANIFEST_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, OUTPUT_FILE_MODE, dir_fd=output_root_fd)
    try:
        view = memoryview(manifest.raw_bytes)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fchmod(fd, OUTPUT_FILE_MODE)
        os.fchown(fd, ROOT_UID, ROOT_GID)
        os.fsync(fd)
    finally:
        os.close(fd)


def _stage_verified_input(manifest: CandidateManifest, *, uid: int, gid: int) -> dict[str, Any]:
    input_root = _open_verified_input_root(uid=uid, gid=gid)
    try:
        input_source = os.open(SOURCE_NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=input_root)
        try:
            _assert_metadata(os.fstat(input_source), uid=uid, gid=gid, mode=INPUT_DIRECTORY_MODE, label="candidate input source", directory=True)
            base = _open_or_create_staging_base()
            try:
                for name in (REVIEWED_SOURCE_SHA, PARTIAL_NAME):
                    try:
                        os.stat(name, dir_fd=base, follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    raise CandidateStagerError(f"staging target already exists: {name}")
                os.mkdir(PARTIAL_NAME, 0o700, dir_fd=base)
                partial = os.open(PARTIAL_NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=base)
                try:
                    os.fchown(partial, ROOT_UID, ROOT_GID)
                    os.fchmod(partial, 0o700)
                    _assert_metadata(os.fstat(partial), uid=ROOT_UID, gid=ROOT_GID, mode=0o700, label="partial staging root", directory=True)
                    os.mkdir(SOURCE_NAME, 0o700, dir_fd=partial)
                    output_source = os.open(SOURCE_NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=partial)
                    try:
                        os.fchown(output_source, ROOT_UID, ROOT_GID)
                        os.fchmod(output_source, OUTPUT_DIRECTORY_MODE)
                        _require_root_owned_dir(output_source, "staging source root")
                        for entry in manifest.entries:
                            _copy_verified_file(input_source, output_source, entry, uid=uid, gid=gid)
                        os.fsync(output_source)
                    finally:
                        os.close(output_source)
                    _write_manifest(partial, manifest)
                    os.fchmod(partial, OUTPUT_DIRECTORY_MODE)
                    os.fsync(partial)
                finally:
                    os.close(partial)
                os.rename(PARTIAL_NAME, REVIEWED_SOURCE_SHA, src_dir_fd=base, dst_dir_fd=base)
                os.fsync(base)
            finally:
                os.close(base)
        finally:
            os.close(input_source)
    finally:
        os.close(input_root)

    return {
        "status": "STAGED",
        "operation_id": OPERATION_ID,
        "source_sha": REVIEWED_SOURCE_SHA,
        "candidate_sha256": manifest.candidate_sha256,
        "candidate_root": str(STAGING_SOURCE),
        "manifest": str(STAGING_MANIFEST),
        "file_count": len(manifest.entries),
        "total_bytes": manifest.total_bytes,
        "production_release_materializations": 0,
        "current_pointer_swaps": 0,
        "apply_lock_mutations": 0,
        "candidate_javascript_executed_as_root": False,
        "automatic_retry_cleanup_rollback": False,
    }


def _handoff_ids() -> tuple[int, int]:
    return ROOT_UID, ROOT_GID


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage the exact reviewed Dashboard P10 production candidate")
    parser.add_argument("--expected-candidate", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--ack", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if os.geteuid() != 0:
        raise CandidateStagerError("candidate stager must run as root through a separately authorized LIVE gate")
    if not args.apply:
        raise CandidateStagerError("candidate staging requires explicit --apply")
    if args.ack != ACK:
        raise CandidateStagerError("candidate staging acknowledgement mismatch")
    if SHA256.fullmatch(args.expected_candidate) is None:
        raise CandidateStagerError("expected candidate digest must be exact lowercase SHA-256")
    uid, gid = _handoff_ids()
    manifest = _load_and_verify_input(expected_digest=args.expected_candidate, uid=uid, gid=gid)
    receipt = _stage_verified_input(manifest, uid=uid, gid=gid)
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"P10_DASHBOARD_CANDIDATE_STAGER=STOP reason={type(exc).__name__}:{exc}", file=sys.stderr)
        raise SystemExit(1)
