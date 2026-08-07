#!/usr/bin/env python3
"""Fail-closed environment and fixture boundary for V11 AdGuard collectors."""
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass


class SafetyError(ValueError):
    pass


REAL_PROC = pathlib.Path("/proc")
REAL_CGROUP = pathlib.Path("/sys/fs/cgroup")
TEST_ONLY_ENV = (
    "ADGUARD_ATTR_TEST_UID",
    "ADGUARD_ATTR_TEST_COMMIT",
    "ADGUARD_ATTR_FIXED_UTC",
    "ADGUARD_ATTR_DISABLE_DOCKER",
    "ADGUARD_ATTR_TEST_NO_SLEEP",
)


@dataclass(frozen=True)
class CollectionEnvironment:
    proc_root: pathlib.Path
    cgroup_root: pathlib.Path
    fixture_mode: bool


def _inside(path: pathlib.Path, parent: pathlib.Path) -> bool:
    return path == parent or parent in path.parents


def _safe_fixture_root(path: pathlib.Path, repo: pathlib.Path) -> bool:
    evidence = (repo / "evidence").resolve()
    exports = (repo / "exports").resolve()
    resolved = path.resolve()
    return _inside(resolved, evidence) or _inside(resolved, exports)


def collection_environment(repo: pathlib.Path) -> CollectionEnvironment:
    proc_raw = os.environ.get("ADGUARD_ATTR_PROC_ROOT")
    cgroup_raw = os.environ.get("ADGUARD_ATTR_CGROUP_ROOT")
    has_test_only = any(key in os.environ for key in TEST_ONLY_ENV)

    if (proc_raw is None) != (cgroup_raw is None):
        raise SafetyError("proc/cgroup overrides must be supplied together")

    if proc_raw is None:
        if has_test_only:
            raise SafetyError("test-only overrides require isolated fake proc/cgroup roots")
        return CollectionEnvironment(REAL_PROC, REAL_CGROUP, False)

    proc = pathlib.Path(proc_raw).resolve()
    cgroup = pathlib.Path(cgroup_raw).resolve()
    if proc in {pathlib.Path("/"), REAL_PROC} or cgroup in {pathlib.Path("/"), REAL_CGROUP}:
        raise SafetyError("test roots may never be the real host proc/cgroup roots")
    if not proc.is_dir() or not cgroup.is_dir():
        raise SafetyError("test proc/cgroup roots must already exist")
    if not _safe_fixture_root(proc, repo) or not _safe_fixture_root(cgroup, repo):
        raise SafetyError("test proc/cgroup roots must stay under repository evidence/exports")
    return CollectionEnvironment(proc, cgroup, True)


def effective_uid(environment: CollectionEnvironment) -> int:
    override = os.environ.get("ADGUARD_ATTR_TEST_UID")
    if override is None:
        return os.geteuid()
    if not environment.fixture_mode:
        raise SafetyError("test uid override requires isolated fixture mode")
    try:
        value = int(override)
    except ValueError as exc:
        raise SafetyError("invalid test uid override") from exc
    if value < 0:
        raise SafetyError("invalid test uid override")
    return value


def test_override(name: str, environment: CollectionEnvironment) -> str | None:
    value = os.environ.get(name)
    if value is not None and not environment.fixture_mode:
        raise SafetyError(f"{name} is test-only")
    return value
