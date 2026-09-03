#!/usr/bin/env python3
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys

HERE = Path(__file__).resolve().parent
CORE_PATH = HERE / "dashboard-rpi5-preverified-handoff-materializer-core.py"
loader = importlib.machinery.SourceFileLoader("dashboard_handoff_materializer_core", str(CORE_PATH))
spec = importlib.util.spec_from_loader(loader.name, loader)
if spec is None:
    raise RuntimeError("unable to load handoff materializer core")
core = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = core
loader.exec_module(core)

core.HANDOFF_OWNER = "root"
core.HANDOFF_GROUP = "root"
core.HANDOFF_BASE = Path("/var/lib/rozkalns-dashboard-candidate-input")
core.HANDOFF_ROOT = core.HANDOFF_BASE / core.REVIEWED_SOURCE_SHA
core.HANDOFF_SOURCE = core.HANDOFF_ROOT / core.SOURCE_NAME
core.HANDOFF_MANIFEST = core.HANDOFF_ROOT / core.MANIFEST_NAME
core.HANDOFF_MUTATION_BUDGET = (
    ("handoff-namespace-root-create", 1),
    ("handoff-candidate-partial-root-create", 1),
    ("handoff-source-root-create", 1),
    ("handoff-file-materialization", core.EXPECTED_FILE_COUNT),
    ("handoff-manifest-materialization", 1),
    ("handoff-final-no-replace-rename", 1),
)

ROOT_UID = 0
ROOT_GID = 0
BASE_MODE = 0o755
_ORIGINAL_MATERIALIZE = core._materialize_handoff


def _open_or_create_handoff_base(*, uid: int, gid: int) -> int:
    if uid != ROOT_UID or gid != ROOT_GID:
        raise core.HandoffMaterializerError("handoff namespace must remain root-owned")
    parent = core._open_abs_dir(core.HANDOFF_BASE.parent, "handoff namespace parent")
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
        base = os.open(
            core.HANDOFF_BASE.name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=parent,
        )
        if created:
            os.fchown(base, ROOT_UID, ROOT_GID)
            os.fchmod(base, BASE_MODE)
            os.fsync(base)
            os.fsync(parent)
    finally:
        os.close(parent)
    core._assert_metadata(
        os.fstat(base),
        uid=ROOT_UID,
        gid=ROOT_GID,
        mode=BASE_MODE,
        label="handoff namespace root",
        directory=True,
    )
    return base


def _verify_published_absolute(manifest: core.CandidateManifest) -> None:
    root = core._open_abs_dir(core.HANDOFF_ROOT, "published handoff root")
    try:
        core._assert_metadata(
            os.fstat(root),
            uid=ROOT_UID,
            gid=ROOT_GID,
            mode=core.HANDOFF_DIRECTORY_MODE,
            label="published handoff root",
            directory=True,
        )
        manifest_fd = os.open(
            core.MANIFEST_NAME,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=root,
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
                raise core.HandoffMaterializerError("published handoff manifest changed after publish")
        finally:
            os.close(manifest_fd)

        source_fd = os.open(
            core.SOURCE_NAME,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=root,
        )
        try:
            core._verify_final_tree(source_fd, manifest, uid=ROOT_UID, gid=ROOT_GID)
        finally:
            os.close(source_fd)
    finally:
        os.close(root)


def _materialize_handoff(
    manifest: core.CandidateManifest,
    *,
    ingress_uid: int,
    ingress_gid: int,
    handoff_uid: int,
    handoff_gid: int,
    build_uid: int = ROOT_UID,
    build_gid: int = ROOT_GID,
) -> dict[str, object]:
    if (handoff_uid, handoff_gid, build_uid, build_gid) != (0, 0, 0, 0):
        raise core.HandoffMaterializerError("accepted handoff must remain root-owned")
    receipt = _ORIGINAL_MATERIALIZE(
        manifest,
        ingress_uid=ingress_uid,
        ingress_gid=ingress_gid,
        handoff_uid=ROOT_UID,
        handoff_gid=ROOT_GID,
        build_uid=ROOT_UID,
        build_gid=ROOT_GID,
    )
    _verify_published_absolute(manifest)
    return receipt


core._open_handoff_base = _open_or_create_handoff_base
core._materialize_handoff = _materialize_handoff

CAPABILITY = core.CAPABILITY
REVIEWED_SOURCE_SHA = core.REVIEWED_SOURCE_SHA
EXPECTED_CANDIDATE_SHA256 = core.EXPECTED_CANDIDATE_SHA256
HANDOFF_BASE = core.HANDOFF_BASE
HANDOFF_ROOT = core.HANDOFF_ROOT
HANDOFF_SOURCE = core.HANDOFF_SOURCE
HANDOFF_MANIFEST = core.HANDOFF_MANIFEST
HANDOFF_MUTATION_BUDGET = core.HANDOFF_MUTATION_BUDGET
ACK = core.ACK


def main(argv: list[str] | None = None) -> int:
    return core.main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            f"P10_DASHBOARD_HANDOFF_MATERIALIZER=STOP reason={type(exc).__name__}:{exc}",
            file=sys.stderr,
        )
        raise SystemExit(1)
