from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY = "rozkalnsandris/hermes-tech"
_BRANCH = "main"


class PublicationGuardError(ValueError):
    """Fail-closed source-only publication request validation error."""


@dataclass(frozen=True)
class PublicationSpec:
    expected_repository: str
    expected_branch: str
    expected_base_sha: str
    expected_publication_sha: str
    expected_parent_sha: str
    expected_subject: str
    expected_changed_paths: tuple[str, ...]
    expected_remote_main_sha: str


@dataclass(frozen=True)
class ObservedPublication:
    repository: str
    branch: str
    base_sha: str
    publication_sha: str
    parent_sha: str
    subject: str
    changed_paths: tuple[str, ...]
    remote_main_sha: str


def _sha(value: str, field: str) -> None:
    if not _SHA40.fullmatch(value):
        raise PublicationGuardError(f"{field}_invalid")


def _paths(values: Iterable[str], field: str) -> tuple[str, ...]:
    paths = tuple(values)
    if not paths:
        raise PublicationGuardError(f"{field}_empty")
    if len(paths) != len(set(paths)):
        raise PublicationGuardError(f"{field}_duplicate")
    for path in paths:
        if not path or path.startswith("/") or path.startswith("../") or "/../" in path:
            raise PublicationGuardError(f"{field}_unsafe")
        if path.endswith("/") or "\\x00" in path:
            raise PublicationGuardError(f"{field}_unsafe")
    return tuple(sorted(paths))


def validate_publication(spec: PublicationSpec, observed: ObservedPublication) -> dict[str, object]:
    """Validate immutable publication evidence without executing Git, SSH or shell."""

    if spec.expected_repository != _REPOSITORY or observed.repository != _REPOSITORY:
        raise PublicationGuardError("repository_mismatch")
    if spec.expected_branch != _BRANCH or observed.branch != _BRANCH:
        raise PublicationGuardError("branch_mismatch")

    for field, value in (
        ("expected_base_sha", spec.expected_base_sha),
        ("expected_publication_sha", spec.expected_publication_sha),
        ("expected_parent_sha", spec.expected_parent_sha),
        ("expected_remote_main_sha", spec.expected_remote_main_sha),
        ("base_sha", observed.base_sha),
        ("publication_sha", observed.publication_sha),
        ("parent_sha", observed.parent_sha),
        ("remote_main_sha", observed.remote_main_sha),
    ):
        _sha(value, field)

    if spec.expected_parent_sha != spec.expected_base_sha:
        raise PublicationGuardError("spec_direct_parent_mismatch")
    if observed.parent_sha != observed.base_sha:
        raise PublicationGuardError("observed_direct_parent_mismatch")
    if observed.base_sha != spec.expected_base_sha:
        raise PublicationGuardError("base_sha_mismatch")
    if observed.parent_sha != spec.expected_parent_sha:
        raise PublicationGuardError("parent_sha_mismatch")
    if observed.publication_sha != spec.expected_publication_sha:
        raise PublicationGuardError("publication_sha_mismatch")
    if observed.remote_main_sha != spec.expected_remote_main_sha:
        raise PublicationGuardError("remote_main_mismatch")
    if spec.expected_remote_main_sha != spec.expected_base_sha:
        raise PublicationGuardError("spec_remote_main_not_base")
    if observed.remote_main_sha != observed.base_sha:
        raise PublicationGuardError("remote_main_race_detected")

    if not spec.expected_subject or observed.subject != spec.expected_subject:
        raise PublicationGuardError("subject_mismatch")

    expected_paths = _paths(spec.expected_changed_paths, "expected_changed_paths")
    observed_paths = _paths(observed.changed_paths, "changed_paths")
    if observed_paths != expected_paths:
        raise PublicationGuardError("changed_paths_mismatch")

    return {
        "decision": "SOURCE_VALIDATED_NO_PUSH",
        "repository": _REPOSITORY,
        "branch": _BRANCH,
        "base_sha": observed.base_sha,
        "publication_sha": observed.publication_sha,
        "changed_paths": list(observed_paths),
        "fast_forward_only_intent": True,
        "remote_main_race_guard": "PASS",
        "post_push_exact_sha_required": True,
        "network_push_executed": False,
        "generic_git_authority": False,
        "generic_ssh_authority": False,
        "generic_shell_authority": False,
        "production_wiring_enabled": False,
    }
