#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
import errno
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys
from typing import Any

CAPABILITY = "dashboard-rpi5.preverified-handoff-materializer.v1"
REVIEWED_SOURCE_SHA = "066b9a24008dd57439f9e66eae198416c4dfc590"
REVIEWED_SOURCE_TREE_SHA = "62756ba22fc8d47e44988c086c08dcf37779cfb3"
REVIEWED_PARENT_SHA = "5f7739348f56398d0ba301c9320e1de0062838fc"
REVIEWED_PRODUCER_BLOB_SHA = "bea0f30602d119ae53b81e70ce2d4c283d369ce8"
EXPECTED_CANDIDATE_SHA256 = "d12a49de01891e3a4cc188fa16c173c5eb44c786f013d3a6ebfefe95dcaa47b9"
EXPECTED_FILE_COUNT = 72
EXPECTED_TOTAL_BYTES = 6_773_246
MANIFEST_SCHEMA = "dashboard-rpi5.production-candidate.v1"
MANIFEST_NAME = "candidate-manifest.json"
SOURCE_NAME = "source"
INGRESS_OWNER = "andris"
INGRESS_GROUP = "andris"
INGRESS_BASE = Path("/home") / INGRESS_OWNER / ".cache" / "rozkalns-dashboard-preverified-ingress"
INGRESS_ROOT = INGRESS_BASE / REVIEWED_SOURCE_SHA
INGRESS_SOURCE = INGRESS_ROOT / SOURCE_NAME
INGRESS_MANIFEST = INGRESS_ROOT / MANIFEST_NAME
HANDOFF_OWNER = "rozkalns-deploy-executor"
HANDOFF_GROUP = "rozkalns-deploy-executor"
HANDOFF_BASE = Path("/var/lib/rozkalns-deploy-executor/dashboard-candidate-input")
HANDOFF_ROOT = HANDOFF_BASE / REVIEWED_SOURCE_SHA
HANDOFF_SOURCE = HANDOFF_ROOT / SOURCE_NAME
HANDOFF_MANIFEST = HANDOFF_ROOT / MANIFEST_NAME
PARTIAL_NAME = f".{REVIEWED_SOURCE_SHA}.handoff-materializer-partial"
ACK = "I_AUTHORIZED_DASHBOARD_RPI5_PREVERIFIED_HANDOFF_066B9A24"

MAX_MANIFEST_BYTES = 4 * 1024 * 1024
COPY_BUFFER_BYTES = 64 * 1024
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
INGRESS_DIRECTORY_MODE = 0o555
INGRESS_FILE_MODE = 0o444
HANDOFF_BASE_MODE = 0o755
HANDOFF_DIRECTORY_MODE = 0o555
HANDOFF_FILE_MODE = 0o444
BUILD_DIRECTORY_MODE = 0o700
BUILD_FILE_MODE = 0o400
ROOT_UID = 0
ROOT_GID = 0
RENAME_NOREPLACE = 1

HANDOFF_MUTATION_BUDGET = (
    ("handoff-candidate-partial-root-create", 1),
    ("handoff-source-root-create", 1),
    ("handoff-file-materialization", EXPECTED_FILE_COUNT),
    ("handoff-manifest-materialization", 1),
    ("handoff-final-no-replace-rename", 1),
)


class HandoffMaterializerError(RuntimeError):
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
        raise HandoffMaterializerError("descriptor-safe handoff materialization requires Linux /proc/self/fd")
    for name in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK"):
        if not hasattr(os, name):
            raise HandoffMaterializerError(f"descriptor-safe handoff materialization requires {name}")
    libc = ctypes.CDLL(None)
    if not hasattr(libc, "renameat2"):
        raise HandoffMaterializerError("atomic no-replace publish requires renameat2")


def _safe_parts(path: str) -> tuple[str, ...]:
    if not path or path.startswith("/") or "\\" in path:
        raise HandoffMaterializerError("candidate manifest path is invalid")
    parts = tuple(path.split("/"))
    if any(part in ("", ".", "..") for part in parts):
        raise HandoffMaterializerError("candidate manifest path escapes reviewed root")
    if MANIFEST_NAME in parts or ".dashboard-production-candidate.json" in parts or "node_modules" in parts:
        raise HandoffMaterializerError("candidate manifest path uses a reserved component")
    return parts


def _strict_json(data: bytes) -> Any:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise HandoffMaterializerError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=hook)
    except HandoffMaterializerError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HandoffMaterializerError("candidate manifest is not strict UTF-8 JSON") from exc


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _parse_manifest(raw_bytes: bytes) -> CandidateManifest:
    if len(raw_bytes) > MAX_MANIFEST_BYTES:
        raise HandoffMaterializerError("candidate manifest exceeds reviewed size bound")
    value = _strict_json(raw_bytes)
    keys = {
        "schema", "sourceSha", "releasePath", "nodeMajor", "hashAlgorithm",
        "fileCount", "totalBytes", "files", "candidateSha256",
    }
    if type(value) is not dict or set(value) != keys:
        raise HandoffMaterializerError("candidate manifest shape is invalid")
    if value["schema"] != MANIFEST_SCHEMA or value["sourceSha"] != REVIEWED_SOURCE_SHA:
        raise HandoffMaterializerError("candidate manifest source/schema mismatch")
    if FULL_SHA.fullmatch(value["sourceSha"]) is None:
        raise HandoffMaterializerError("candidate manifest source SHA is invalid")
    if value["releasePath"] != f"/opt/dashboard_RPi5/releases/{REVIEWED_SOURCE_SHA}":
        raise HandoffMaterializerError("candidate manifest release path mismatch")
    if value["nodeMajor"] != 24 or value["hashAlgorithm"] != "sha256":
        raise HandoffMaterializerError("candidate manifest runtime/hash mismatch")

    count, total, files = value["fileCount"], value["totalBytes"], value["files"]
    if type(count) is not int or count != EXPECTED_FILE_COUNT:
        raise HandoffMaterializerError("candidate manifest file count differs from reviewed preverification")
    if type(total) is not int or total != EXPECTED_TOTAL_BYTES:
        raise HandoffMaterializerError("candidate manifest total bytes differ from reviewed preverification")
    if type(files) is not list or len(files) != EXPECTED_FILE_COUNT:
        raise HandoffMaterializerError("candidate manifest file list mismatch")

    entries: list[CandidateEntry] = []
    seen: set[str] = set()
    for item in files:
        if type(item) is not dict or set(item) != {"path", "bytes", "sha256"}:
            raise HandoffMaterializerError("candidate manifest file entry shape mismatch")
        path, size, digest = item["path"], item["bytes"], item["sha256"]
        if type(path) is not str or path in seen:
            raise HandoffMaterializerError("candidate manifest path is invalid or duplicated")
        _safe_parts(path)
        seen.add(path)
        if type(size) is not int or size < 0 or size > EXPECTED_TOTAL_BYTES:
            raise HandoffMaterializerError("candidate manifest file size is invalid")
        if type(digest) is not str or SHA256.fullmatch(digest) is None:
            raise HandoffMaterializerError("candidate manifest file digest is invalid")
        entries.append(CandidateEntry(path, size, digest))

    if [entry.path for entry in entries] != sorted(entry.path for entry in entries):
        raise HandoffMaterializerError("candidate manifest files are not deterministically sorted")
    if sum(entry.bytes for entry in entries) != EXPECTED_TOTAL_BYTES:
        raise HandoffMaterializerError("candidate manifest aggregate size mismatch")

    digest = value["candidateSha256"]
    if type(digest) is not str or SHA256.fullmatch(digest) is None:
        raise HandoffMaterializerError("candidate manifest digest is invalid")
    core = {key: value[key] for key in (
        "schema", "sourceSha", "releasePath", "nodeMajor", "hashAlgorithm",
        "fileCount", "totalBytes", "files",
    )}
    if hashlib.sha256(_canonical_json(core)).hexdigest() != digest:
        raise HandoffMaterializerError("candidate manifest self-digest mismatch")
    if digest != EXPECTED_CANDIDATE_SHA256:
        raise HandoffMaterializerError("candidate manifest digest differs from reviewed preverification")
    return CandidateManifest(REVIEWED_SOURCE_SHA, digest, EXPECTED_TOTAL_BYTES, tuple(entries), raw_bytes)


def _open_abs_dir(path: Path, label: str) -> int:
    _require_descriptor_safety()
    if not path.is_absolute():
        raise HandoffMaterializerError(f"{label} must be absolute")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            if not stat.S_ISDIR(os.fstat(nxt).st_mode):
                os.close(nxt)
                raise HandoffMaterializerError(f"{label} must be a real directory")
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
                raise HandoffMaterializerError(f"{label} must be a real directory")
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
        raise HandoffMaterializerError(f"{label} must be a regular file")
    return fd


def _assert_metadata(st: os.stat_result, *, uid: int, gid: int, mode: int, label: str, directory: bool) -> None:
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(st.st_mode) or st.st_uid != uid or st.st_gid != gid or _mode(st) != mode:
        raise HandoffMaterializerError(f"{label} metadata mismatch")


def _read_bounded(fd: int, maximum: int, label: str) -> bytes:
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_size > maximum:
        raise HandoffMaterializerError(f"{label} exceeds reviewed size bound")
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(COPY_BUFFER_BYTES, maximum + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > maximum:
            raise HandoffMaterializerError(f"{label} exceeds reviewed size bound")
        chunks.append(chunk)
    if os.fstat(fd).st_size != total:
        raise HandoffMaterializerError(f"{label} changed while being read")
    return b"".join(chunks)


def _collect_ingress_tree(fd: int, *, uid: int, gid: int, prefix: str = "") -> list[str]:
    files: list[str] = []
    for name in sorted(os.listdir(fd)):
        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
        rel = f"{prefix}/{name}" if prefix else name
        if stat.S_ISLNK(st.st_mode):
            raise HandoffMaterializerError(f"preverified ingress symlink forbidden: {rel}")
        if stat.S_ISDIR(st.st_mode):
            _assert_metadata(st, uid=uid, gid=gid, mode=INGRESS_DIRECTORY_MODE, label=f"preverified ingress directory {rel}", directory=True)
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                files.extend(_collect_ingress_tree(child, uid=uid, gid=gid, prefix=rel))
            finally:
                os.close(child)
        elif stat.S_ISREG(st.st_mode):
            _assert_metadata(st, uid=uid, gid=gid, mode=INGRESS_FILE_MODE, label=f"preverified ingress file {rel}", directory=False)
            files.append(rel)
        else:
            raise HandoffMaterializerError(f"preverified ingress special file forbidden: {rel}")
    return files


def _hash_fd(fd: int, expected_size: int, label: str) -> str:
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_size != expected_size:
        raise HandoffMaterializerError(f"{label} size/type mismatch")
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    total = 0
    while True:
        chunk = os.read(fd, COPY_BUFFER_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > expected_size:
            raise HandoffMaterializerError(f"{label} changed while reading")
        digest.update(chunk)
    if total != expected_size or os.fstat(fd).st_size != expected_size:
        raise HandoffMaterializerError(f"{label} changed while reading")
    return digest.hexdigest()


def _load_and_verify_ingress(*, uid: int, gid: int) -> CandidateManifest:
    root = _open_abs_dir(INGRESS_ROOT, "preverified ingress root")
    try:
        _assert_metadata(os.fstat(root), uid=uid, gid=gid, mode=INGRESS_DIRECTORY_MODE, label="preverified ingress root", directory=True)
        manifest_fd = os.open(MANIFEST_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
        try:
            _assert_metadata(os.fstat(manifest_fd), uid=uid, gid=gid, mode=INGRESS_FILE_MODE, label="preverified ingress manifest", directory=False)
            raw = _read_bounded(manifest_fd, MAX_MANIFEST_BYTES, "preverified ingress manifest")
        finally:
            os.close(manifest_fd)
        manifest = _parse_manifest(raw)
        source_fd = os.open(SOURCE_NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        try:
            _assert_metadata(os.fstat(source_fd), uid=uid, gid=gid, mode=INGRESS_DIRECTORY_MODE, label="preverified ingress source", directory=True)
            actual = _collect_ingress_tree(source_fd, uid=uid, gid=gid)
            expected = [entry.path for entry in manifest.entries]
            if actual != expected:
                raise HandoffMaterializerError("preverified ingress tree does not exactly match manifest")
            for entry in manifest.entries:
                fd = _open_rel_file(source_fd, entry.path, f"preverified ingress {entry.path}")
                try:
                    _assert_metadata(os.fstat(fd), uid=uid, gid=gid, mode=INGRESS_FILE_MODE, label=f"preverified ingress {entry.path}", directory=False)
                    if _hash_fd(fd, entry.bytes, f"preverified ingress {entry.path}") != entry.sha256:
                        raise HandoffMaterializerError(f"preverified ingress digest mismatch: {entry.path}")
                finally:
                    os.close(fd)
        finally:
            os.close(source_fd)
        return manifest
    finally:
        os.close(root)


def _path_absent(base_fd: int, name: str, label: str) -> None:
    try:
        os.stat(name, dir_fd=base_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise HandoffMaterializerError(f"{label} already exists")


def _open_handoff_base(*, uid: int, gid: int) -> int:
    base = _open_abs_dir(HANDOFF_BASE, "handoff namespace root")
    try:
        _assert_metadata(os.fstat(base), uid=uid, gid=gid, mode=HANDOFF_BASE_MODE, label="handoff namespace root", directory=True)
    except Exception:
        os.close(base)
        raise
    return base


def _ensure_build_parent(root_fd: int, parts: tuple[str, ...], *, uid: int, gid: int) -> int:
    fd = os.dup(root_fd)
    try:
        for part in parts:
            created = False
            try:
                os.mkdir(part, BUILD_DIRECTORY_MODE, dir_fd=fd)
                created = True
            except FileExistsError:
                pass
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            if created:
                os.fchown(nxt, uid, gid)
                os.fchmod(nxt, BUILD_DIRECTORY_MODE)
            _assert_metadata(os.fstat(nxt), uid=uid, gid=gid, mode=BUILD_DIRECTORY_MODE, label=f"handoff build directory {part}", directory=True)
            os.close(fd)
            fd = nxt
        return fd
    except Exception:
        os.close(fd)
        raise


def _copy_verified_file(input_root_fd: int, output_root_fd: int, entry: CandidateEntry, *, input_uid: int, input_gid: int, build_uid: int, build_gid: int) -> None:
    source_fd = _open_rel_file(input_root_fd, entry.path, f"preverified ingress {entry.path}")
    try:
        _assert_metadata(os.fstat(source_fd), uid=input_uid, gid=input_gid, mode=INGRESS_FILE_MODE, label=f"preverified ingress {entry.path}", directory=False)
        parts = _safe_parts(entry.path)
        parent = _ensure_build_parent(output_root_fd, parts[:-1], uid=build_uid, gid=build_gid)
        try:
            dest_fd = os.open(parts[-1], os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        finally:
            os.close(parent)
        try:
            os.fchown(dest_fd, build_uid, build_gid)
            digest = hashlib.sha256()
            os.lseek(source_fd, 0, os.SEEK_SET)
            total = 0
            while True:
                chunk = os.read(source_fd, COPY_BUFFER_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > entry.bytes:
                    raise HandoffMaterializerError(f"preverified ingress changed while materializing: {entry.path}")
                digest.update(chunk)
                view = memoryview(chunk)
                while view:
                    written = os.write(dest_fd, view)
                    if written <= 0:
                        raise HandoffMaterializerError("handoff destination write made no progress")
                    view = view[written:]
            if total != entry.bytes or os.fstat(source_fd).st_size != entry.bytes or digest.hexdigest() != entry.sha256:
                raise HandoffMaterializerError(f"preverified ingress digest drift while materializing: {entry.path}")
            os.fsync(dest_fd)
            if _hash_fd(dest_fd, entry.bytes, f"handoff build {entry.path}") != entry.sha256:
                raise HandoffMaterializerError(f"handoff destination digest mismatch: {entry.path}")
            os.fchmod(dest_fd, BUILD_FILE_MODE)
        finally:
            os.close(dest_fd)
    finally:
        os.close(source_fd)


def _write_manifest(output_root_fd: int, manifest: CandidateManifest, *, uid: int, gid: int) -> None:
    fd = os.open(MANIFEST_NAME, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=output_root_fd)
    try:
        os.fchown(fd, uid, gid)
        view = memoryview(manifest.raw_bytes)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise HandoffMaterializerError("handoff manifest write made no progress")
            view = view[written:]
        os.fsync(fd)
        if _read_bounded(fd, MAX_MANIFEST_BYTES, "handoff build manifest") != manifest.raw_bytes:
            raise HandoffMaterializerError("handoff destination manifest mismatch")
        os.fchmod(fd, BUILD_FILE_MODE)
    finally:
        os.close(fd)


def _finalize_directories(fd: int, *, build_uid: int, build_gid: int, final_uid: int, final_gid: int, finalize_self: bool = True) -> None:
    for name in sorted(os.listdir(fd)):
        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if stat.S_ISDIR(st.st_mode):
            _assert_metadata(st, uid=build_uid, gid=build_gid, mode=BUILD_DIRECTORY_MODE, label=f"handoff build directory {name}", directory=True)
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                _finalize_directories(child, build_uid=build_uid, build_gid=build_gid, final_uid=final_uid, final_gid=final_gid)
            finally:
                os.close(child)
        elif stat.S_ISREG(st.st_mode):
            _assert_metadata(st, uid=build_uid, gid=build_gid, mode=BUILD_FILE_MODE, label=f"handoff build file {name}", directory=False)
            child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            try:
                os.fchown(child, final_uid, final_gid)
                os.fchmod(child, HANDOFF_FILE_MODE)
            finally:
                os.close(child)
        else:
            raise HandoffMaterializerError(f"handoff build contains non-regular entry: {name}")
    if finalize_self:
        os.fchmod(fd, HANDOFF_DIRECTORY_MODE)
        os.fchown(fd, final_uid, final_gid)
        os.fsync(fd)


def _verify_final_tree(source_fd: int, manifest: CandidateManifest, *, uid: int, gid: int) -> None:
    _assert_metadata(os.fstat(source_fd), uid=uid, gid=gid, mode=HANDOFF_DIRECTORY_MODE, label="final handoff source", directory=True)
    actual = _collect_ingress_tree_with_modes(source_fd, uid=uid, gid=gid)
    expected = [entry.path for entry in manifest.entries]
    if actual != expected:
        raise HandoffMaterializerError("final handoff tree does not exactly match manifest")
    for entry in manifest.entries:
        fd = _open_rel_file(source_fd, entry.path, f"final handoff {entry.path}")
        try:
            _assert_metadata(os.fstat(fd), uid=uid, gid=gid, mode=HANDOFF_FILE_MODE, label=f"final handoff {entry.path}", directory=False)
            if _hash_fd(fd, entry.bytes, f"final handoff {entry.path}") != entry.sha256:
                raise HandoffMaterializerError(f"final handoff digest mismatch: {entry.path}")
        finally:
            os.close(fd)


def _collect_ingress_tree_with_modes(fd: int, *, uid: int, gid: int, prefix: str = "") -> list[str]:
    files: list[str] = []
    for name in sorted(os.listdir(fd)):
        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
        rel = f"{prefix}/{name}" if prefix else name
        if stat.S_ISLNK(st.st_mode):
            raise HandoffMaterializerError(f"final handoff symlink forbidden: {rel}")
        if stat.S_ISDIR(st.st_mode):
            _assert_metadata(st, uid=uid, gid=gid, mode=HANDOFF_DIRECTORY_MODE, label=f"final handoff directory {rel}", directory=True)
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                files.extend(_collect_ingress_tree_with_modes(child, uid=uid, gid=gid, prefix=rel))
            finally:
                os.close(child)
        elif stat.S_ISREG(st.st_mode):
            _assert_metadata(st, uid=uid, gid=gid, mode=HANDOFF_FILE_MODE, label=f"final handoff file {rel}", directory=False)
            files.append(rel)
        else:
            raise HandoffMaterializerError(f"final handoff special file forbidden: {rel}")
    return files


def _rename_noreplace(base_fd: int, source: str, destination: str) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise HandoffMaterializerError("atomic no-replace publish requires renameat2")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(base_fd, os.fsencode(source), base_fd, os.fsencode(destination), RENAME_NOREPLACE)
    if result != 0:
        err = ctypes.get_errno()
        if err == errno.EEXIST:
            raise HandoffMaterializerError("handoff target appeared before atomic publish")
        raise OSError(err, os.strerror(err), destination)


def _materialize_handoff(manifest: CandidateManifest, *, ingress_uid: int, ingress_gid: int, handoff_uid: int, handoff_gid: int, build_uid: int = ROOT_UID, build_gid: int = ROOT_GID) -> dict[str, Any]:
    ingress_root = _open_abs_dir(INGRESS_ROOT, "preverified ingress root")
    try:
        _assert_metadata(os.fstat(ingress_root), uid=ingress_uid, gid=ingress_gid, mode=INGRESS_DIRECTORY_MODE, label="preverified ingress root", directory=True)
        input_source = os.open(SOURCE_NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=ingress_root)
        try:
            _assert_metadata(os.fstat(input_source), uid=ingress_uid, gid=ingress_gid, mode=INGRESS_DIRECTORY_MODE, label="preverified ingress source", directory=True)
            base = _open_handoff_base(uid=build_uid, gid=build_gid)
            try:
                _path_absent(base, REVIEWED_SOURCE_SHA, "handoff target")
                _path_absent(base, PARTIAL_NAME, "handoff partial")
                os.mkdir(PARTIAL_NAME, BUILD_DIRECTORY_MODE, dir_fd=base)
                partial = os.open(PARTIAL_NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=base)
                try:
                    os.fchown(partial, build_uid, build_gid)
                    os.fchmod(partial, BUILD_DIRECTORY_MODE)
                    os.mkdir(SOURCE_NAME, BUILD_DIRECTORY_MODE, dir_fd=partial)
                    output_source = os.open(SOURCE_NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=partial)
                    try:
                        os.fchown(output_source, build_uid, build_gid)
                        os.fchmod(output_source, BUILD_DIRECTORY_MODE)
                        for entry in manifest.entries:
                            _copy_verified_file(
                                input_source,
                                output_source,
                                entry,
                                input_uid=ingress_uid,
                                input_gid=ingress_gid,
                                build_uid=build_uid,
                                build_gid=build_gid,
                            )
                        _finalize_directories(output_source, build_uid=build_uid, build_gid=build_gid, final_uid=handoff_uid, final_gid=handoff_gid)
                        _verify_final_tree(output_source, manifest, uid=handoff_uid, gid=handoff_gid)
                    finally:
                        os.close(output_source)
                    _write_manifest(partial, manifest, uid=build_uid, gid=build_gid)
                    manifest_fd = os.open(MANIFEST_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=partial)
                    try:
                        _assert_metadata(os.fstat(manifest_fd), uid=build_uid, gid=build_gid, mode=BUILD_FILE_MODE, label="handoff build manifest", directory=False)
                        os.fchown(manifest_fd, handoff_uid, handoff_gid)
                        os.fchmod(manifest_fd, HANDOFF_FILE_MODE)
                    finally:
                        os.close(manifest_fd)
                    os.fchmod(partial, HANDOFF_DIRECTORY_MODE)
                    os.fchown(partial, handoff_uid, handoff_gid)
                    os.fsync(partial)
                finally:
                    os.close(partial)
                _rename_noreplace(base, PARTIAL_NAME, REVIEWED_SOURCE_SHA)
                os.fsync(base)
            finally:
                os.close(base)
        finally:
            os.close(input_source)
    finally:
        os.close(ingress_root)

    return {
        "status": "MATERIALIZED",
        "capability": CAPABILITY,
        "source_sha": REVIEWED_SOURCE_SHA,
        "source_tree_sha": REVIEWED_SOURCE_TREE_SHA,
        "parent_sha": REVIEWED_PARENT_SHA,
        "producer_blob_sha": REVIEWED_PRODUCER_BLOB_SHA,
        "candidate_sha256": EXPECTED_CANDIDATE_SHA256,
        "file_count": EXPECTED_FILE_COUNT,
        "total_bytes": EXPECTED_TOTAL_BYTES,
        "ingress_root": str(INGRESS_ROOT),
        "handoff_root": str(HANDOFF_ROOT),
        "normal_candidate_stager_invocations": 0,
        "production_candidate_staging_mutations": 0,
        "production_release_materializations": 0,
        "current_pointer_swaps": 0,
        "apply_lock_mutations": 0,
        "candidate_javascript_executed_as_root": False,
        "automatic_retry_cleanup_rollback": False,
    }


def _identity_ids() -> tuple[int, int, int, int]:
    try:
        ingress_uid = pwd.getpwnam(INGRESS_OWNER).pw_uid
        ingress_gid = grp.getgrnam(INGRESS_GROUP).gr_gid
        handoff_uid = pwd.getpwnam(HANDOFF_OWNER).pw_uid
        handoff_gid = grp.getgrnam(HANDOFF_GROUP).gr_gid
    except KeyError as exc:
        raise HandoffMaterializerError("fixed ingress or handoff identity is unavailable") from exc
    return ingress_uid, ingress_gid, handoff_uid, handoff_gid


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize the exact preverified Dashboard P10 handoff")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--ack", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if os.geteuid() != 0:
        raise HandoffMaterializerError("handoff materializer must run as root through a separately authorized LIVE gate")
    if not args.apply:
        raise HandoffMaterializerError("handoff materialization requires explicit --apply")
    if args.ack != ACK:
        raise HandoffMaterializerError("handoff materialization acknowledgement mismatch")
    _require_descriptor_safety()
    ingress_uid, ingress_gid, handoff_uid, handoff_gid = _identity_ids()
    manifest = _load_and_verify_ingress(uid=ingress_uid, gid=ingress_gid)
    receipt = _materialize_handoff(
        manifest,
        ingress_uid=ingress_uid,
        ingress_gid=ingress_gid,
        handoff_uid=handoff_uid,
        handoff_gid=handoff_gid,
    )
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"P10_DASHBOARD_HANDOFF_MATERIALIZER=STOP reason={type(exc).__name__}:{exc}", file=sys.stderr)
        raise SystemExit(1)