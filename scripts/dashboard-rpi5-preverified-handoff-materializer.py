#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

TRUSTED_EXEC_BASE = Path("/var/lib/rozkalns-dashboard-handoff-exec")
TRUSTED_EXEC_ROOT = TRUSTED_EXEC_BASE / "v1"
TRUSTED_ENTRYPOINT = TRUSTED_EXEC_ROOT / "dashboard-rpi5-preverified-handoff-materializer.py"
TRUSTED_CORE = TRUSTED_EXEC_ROOT / "dashboard-rpi5-preverified-handoff-materializer-core.py"
TRUSTED_MANIFEST = TRUSTED_EXEC_ROOT / "execution-manifest.json"

HANDOFF_BASE = Path("/var/lib/rozkalns-dashboard-candidate-input")
REVIEWED_SOURCE_SHA = "066b9a24008dd57439f9e66eae198416c4dfc590"
HANDOFF_ROOT = HANDOFF_BASE / REVIEWED_SOURCE_SHA
HANDOFF_SOURCE = HANDOFF_ROOT / "source"
HANDOFF_MANIFEST = HANDOFF_ROOT / "candidate-manifest.json"

ROOT_UID = 0
ROOT_GID = 0
BASE_MODE = 0o755
BUNDLE_MODE = 0o555
FILE_MODE = 0o444
MAX_EXEC_MANIFEST_BYTES = 64 * 1024
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

EXEC_MANIFEST_SCHEMA = "dashboard-rpi5.handoff-execution-bundle.v1"
EXEC_CAPABILITY = "dashboard-rpi5.preverified-handoff-materializer.v1"
SOURCE_REPOSITORY = "rozkalnsandris/RPi5_main"

ENTRYPOINT_REPO_PATH = "scripts/dashboard-rpi5-preverified-handoff-materializer.py"
CORE_REPO_PATH = "scripts/dashboard-rpi5-preverified-handoff-materializer-core.py"

HANDOFF_MUTATION_BUDGET = (
    ("handoff-namespace-root-create", 1),
    ("handoff-candidate-partial-root-create", 1),
    ("handoff-source-root-create", 1),
    ("handoff-file-materialization", 72),
    ("handoff-manifest-materialization", 1),
    ("handoff-final-no-replace-rename", 1),
)


class ExecutionProvenanceError(RuntimeError):
    pass


def _mode(st: os.stat_result) -> int:
    return stat.S_IMODE(st.st_mode)


def _assert_metadata(
    st: os.stat_result,
    *,
    uid: int,
    gid: int,
    mode: int,
    label: str,
    directory: bool,
) -> None:
    if directory:
        if not stat.S_ISDIR(st.st_mode):
            raise ExecutionProvenanceError(f"{label} is not a directory")
    else:
        if not stat.S_ISREG(st.st_mode):
            raise ExecutionProvenanceError(f"{label} is not a regular file")
    if st.st_uid != uid or st.st_gid != gid:
        raise ExecutionProvenanceError(f"{label} ownership mismatch")
    if _mode(st) != mode:
        raise ExecutionProvenanceError(
            f"{label} mode mismatch: expected {mode:04o}, got {_mode(st):04o}"
        )


def _open_abs_dir(path: Path, label: str) -> int:
    try:
        return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise ExecutionProvenanceError(f"{label} open failed: {exc}") from exc


def _read_bounded(fd: int, maximum: int, label: str) -> bytes:
    chunks: list[bytes] = []
    total = 0
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(fd, min(64 * 1024, maximum + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > maximum:
            raise ExecutionProvenanceError(f"{label} exceeds reviewed size bound")
        chunks.append(chunk)
    return b"".join(chunks)


def _strict_json(raw: bytes) -> dict[str, Any]:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ExecutionProvenanceError(
                    f"duplicate execution-manifest key: {key}"
                )
            out[key] = value
        return out

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=hook)
    except ExecutionProvenanceError:
        raise
    except Exception as exc:
        raise ExecutionProvenanceError(
            "execution manifest is not strict UTF-8 JSON"
        ) from exc
    if type(value) is not dict:
        raise ExecutionProvenanceError("execution manifest root is not an object")
    return value


def _git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _verify_file(
    root_fd: int,
    name: str,
    *,
    expected_git_blob: str,
    expected_sha256: str,
    uid: int,
    gid: int,
    label: str,
) -> bytes:
    try:
        fd = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=root_fd,
        )
    except OSError as exc:
        raise ExecutionProvenanceError(f"{label} open failed: {exc}") from exc
    try:
        st = os.fstat(fd)
        _assert_metadata(
            st,
            uid=uid,
            gid=gid,
            mode=FILE_MODE,
            label=label,
            directory=False,
        )
        data = _read_bounded(fd, 1024 * 1024, label)
        if _git_blob_sha(data) != expected_git_blob:
            raise ExecutionProvenanceError(f"{label} Git blob mismatch")
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            raise ExecutionProvenanceError(f"{label} SHA-256 mismatch")
        return data
    finally:
        os.close(fd)


def _parse_execution_manifest(raw: bytes) -> dict[str, Any]:
    value = _strict_json(raw)
    required = {
        "schema",
        "capability",
        "source_repository",
        "source_main_sha",
        "source_tree_sha",
        "entrypoint",
        "core",
    }
    if set(value) != required:
        raise ExecutionProvenanceError("execution manifest shape mismatch")
    if value["schema"] != EXEC_MANIFEST_SCHEMA:
        raise ExecutionProvenanceError("execution manifest schema mismatch")
    if value["capability"] != EXEC_CAPABILITY:
        raise ExecutionProvenanceError("execution capability mismatch")
    if value["source_repository"] != SOURCE_REPOSITORY:
        raise ExecutionProvenanceError("execution source repository mismatch")
    for key in ("source_main_sha", "source_tree_sha"):
        if type(value[key]) is not str or SHA40.fullmatch(value[key]) is None:
            raise ExecutionProvenanceError(f"execution manifest {key} invalid")

    expected = {
        "entrypoint": ENTRYPOINT_REPO_PATH,
        "core": CORE_REPO_PATH,
    }
    for key, path in expected.items():
        item = value[key]
        if type(item) is not dict or set(item) != {
            "repo_path",
            "git_blob_sha",
            "sha256",
        }:
            raise ExecutionProvenanceError(f"execution manifest {key} shape mismatch")
        if item["repo_path"] != path:
            raise ExecutionProvenanceError(f"execution manifest {key} path mismatch")
        if (
            type(item["git_blob_sha"]) is not str
            or SHA40.fullmatch(item["git_blob_sha"]) is None
        ):
            raise ExecutionProvenanceError(
                f"execution manifest {key} Git blob invalid"
            )
        if (
            type(item["sha256"]) is not str
            or SHA256.fullmatch(item["sha256"]) is None
        ):
            raise ExecutionProvenanceError(
                f"execution manifest {key} SHA-256 invalid"
            )
    return value


def _verify_execution_bundle(
    *,
    base: Path = TRUSTED_EXEC_BASE,
    root: Path = TRUSTED_EXEC_ROOT,
    entrypoint: Path = TRUSTED_ENTRYPOINT,
    core_path: Path = TRUSTED_CORE,
    manifest_path: Path = TRUSTED_MANIFEST,
    uid: int = ROOT_UID,
    gid: int = ROOT_GID,
) -> dict[str, Any]:
    if Path(os.path.abspath(__file__)) != entrypoint:
        raise ExecutionProvenanceError(
            "privileged execution is allowed only from the trusted root-owned bundle"
        )

    parent = _open_abs_dir(base.parent, "trusted execution parent")
    try:
        _assert_metadata(
            os.fstat(parent),
            uid=uid,
            gid=gid,
            mode=BASE_MODE,
            label="trusted execution parent",
            directory=True,
        )
    finally:
        os.close(parent)

    base_fd = _open_abs_dir(base, "trusted execution base")
    try:
        _assert_metadata(
            os.fstat(base_fd),
            uid=uid,
            gid=gid,
            mode=BASE_MODE,
            label="trusted execution base",
            directory=True,
        )
    finally:
        os.close(base_fd)

    root_fd = _open_abs_dir(root, "trusted execution bundle")
    try:
        _assert_metadata(
            os.fstat(root_fd),
            uid=uid,
            gid=gid,
            mode=BUNDLE_MODE,
            label="trusted execution bundle",
            directory=True,
        )

        names = sorted(os.listdir(root_fd))
        expected_names = sorted(
            [entrypoint.name, core_path.name, manifest_path.name]
        )
        if names != expected_names:
            raise ExecutionProvenanceError(
                "trusted execution bundle tree is not exact"
            )

        manifest_fd = os.open(
            manifest_path.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=root_fd,
        )
        try:
            _assert_metadata(
                os.fstat(manifest_fd),
                uid=uid,
                gid=gid,
                mode=FILE_MODE,
                label="trusted execution manifest",
                directory=False,
            )
            raw_manifest = _read_bounded(
                manifest_fd,
                MAX_EXEC_MANIFEST_BYTES,
                "trusted execution manifest",
            )
        finally:
            os.close(manifest_fd)

        manifest = _parse_execution_manifest(raw_manifest)

        _verify_file(
            root_fd,
            entrypoint.name,
            expected_git_blob=manifest["entrypoint"]["git_blob_sha"],
            expected_sha256=manifest["entrypoint"]["sha256"],
            uid=uid,
            gid=gid,
            label="trusted execution entrypoint",
        )
        _verify_file(
            root_fd,
            core_path.name,
            expected_git_blob=manifest["core"]["git_blob_sha"],
            expected_sha256=manifest["core"]["sha256"],
            uid=uid,
            gid=gid,
            label="trusted execution core",
        )
        return manifest
    finally:
        os.close(root_fd)


def _load_core_from_trusted_bundle() -> Any:
    loader = importlib.machinery.SourceFileLoader(
        "dashboard_handoff_materializer_core",
        str(TRUSTED_CORE),
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise ExecutionProvenanceError("unable to load trusted handoff core")
    core = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = core
    loader.exec_module(core)
    return core


def _configure_core(core: Any) -> None:
    core.HANDOFF_OWNER = "root"
    core.HANDOFF_GROUP = "root"
    core.HANDOFF_BASE = HANDOFF_BASE
    core.HANDOFF_ROOT = HANDOFF_ROOT
    core.HANDOFF_SOURCE = HANDOFF_SOURCE
    core.HANDOFF_MANIFEST = HANDOFF_MANIFEST
    core.HANDOFF_MUTATION_BUDGET = HANDOFF_MUTATION_BUDGET

    original_materialize = core._materialize_handoff

    def open_or_create_handoff_base(*, uid: int, gid: int) -> int:
        if uid != ROOT_UID or gid != ROOT_GID:
            raise core.HandoffMaterializerError(
                "handoff namespace must remain root-owned"
            )
        parent = core._open_abs_dir(
            core.HANDOFF_BASE.parent,
            "handoff namespace parent",
        )
        try:
            core._assert_metadata(
                os.fstat(parent),
                uid=ROOT_UID,
                gid=ROOT_GID,
                mode=BASE_MODE,
                label="handoff namespace parent",
                directory=True,
            )
            created = False
            try:
                os.mkdir(core.HANDOFF_BASE.name, 0o700, dir_fd=parent)
                created = True
            except FileExistsError:
                pass
            base_fd = os.open(
                core.HANDOFF_BASE.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent,
            )
            if created:
                os.fchown(base_fd, ROOT_UID, ROOT_GID)
                os.fchmod(base_fd, BASE_MODE)
                os.fsync(base_fd)
                os.fsync(parent)
        finally:
            os.close(parent)

        core._assert_metadata(
            os.fstat(base_fd),
            uid=ROOT_UID,
            gid=ROOT_GID,
            mode=BASE_MODE,
            label="handoff namespace root",
            directory=True,
        )
        return base_fd

    def verify_published_absolute(manifest: Any) -> None:
        root_fd = core._open_abs_dir(
            core.HANDOFF_ROOT,
            "published handoff root",
        )
        try:
            core._assert_metadata(
                os.fstat(root_fd),
                uid=ROOT_UID,
                gid=ROOT_GID,
                mode=core.HANDOFF_DIRECTORY_MODE,
                label="published handoff root",
                directory=True,
            )
            manifest_fd = os.open(
                core.MANIFEST_NAME,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=root_fd,
            )
            try:
                core._assert_metadata(
                    os.fstat(manifest_fd),
                    uid=ROOT_UID,
                    gid=ROOT_GID,
                    mode=core.HANDOFF_FILE_MODE,
                    label="published handoff manifest",
                    directory=False,
                )
                if core._read_bounded(
                    manifest_fd,
                    core.MAX_MANIFEST_BYTES,
                    "published handoff manifest",
                ) != manifest.raw_bytes:
                    raise core.HandoffMaterializerError(
                        "published handoff manifest changed after publish"
                    )
            finally:
                os.close(manifest_fd)

            source_fd = os.open(
                core.SOURCE_NAME,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=root_fd,
            )
            try:
                core._verify_final_tree(
                    source_fd,
                    manifest,
                    uid=ROOT_UID,
                    gid=ROOT_GID,
                )
            finally:
                os.close(source_fd)
        finally:
            os.close(root_fd)

    def materialize_handoff(
        manifest: Any,
        *,
        ingress_uid: int,
        ingress_gid: int,
        handoff_uid: int,
        handoff_gid: int,
        build_uid: int = ROOT_UID,
        build_gid: int = ROOT_GID,
    ) -> dict[str, object]:
        if (handoff_uid, handoff_gid, build_uid, build_gid) != (0, 0, 0, 0):
            raise core.HandoffMaterializerError(
                "accepted handoff must remain root-owned"
            )
        receipt = original_materialize(
            manifest,
            ingress_uid=ingress_uid,
            ingress_gid=ingress_gid,
            handoff_uid=ROOT_UID,
            handoff_gid=ROOT_GID,
            build_uid=ROOT_UID,
            build_gid=ROOT_GID,
        )
        verify_published_absolute(manifest)
        return receipt

    core._open_handoff_base = open_or_create_handoff_base
    core._materialize_handoff = materialize_handoff


def main(argv: list[str] | None = None) -> int:
    if os.geteuid() != ROOT_UID:
        raise ExecutionProvenanceError(
            "handoff materializer must run as root through a separately authorized LIVE gate"
        )
    _verify_execution_bundle()
    core = _load_core_from_trusted_bundle()
    _configure_core(core)
    return core.main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            f"P10_DASHBOARD_HANDOFF_MATERIALIZER=STOP "
            f"reason={type(exc).__name__}:{exc}",
            file=sys.stderr,
        )
        raise SystemExit(1)
