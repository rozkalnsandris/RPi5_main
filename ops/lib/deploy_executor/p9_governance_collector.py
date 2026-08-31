from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from pathlib import PurePosixPath
import re
from typing import Iterable

from .p9_evidence import AUTHORIZATION_REPOSITORY, AUTHORIZATION_REPOSITORY_ID
from .p9_producer import GovernanceWriterSurfaceObservation, _REQUIRED_GOVERNANCE_SURFACES


class P9GovernanceCollectorError(RuntimeError):
    pass


AUTHORIZATION_OWNER_ID = 277435981
PINNED_AUTHORIZATION_SOURCE_SHA = "c9d6b3898a9eda98ce83c5ce77e2bfd49f3703d8"
PINNED_AUTHORIZATION_SOURCE_TREE_SHA = "9649c6c38b4bce83ee535557dc7e8e335f8c08ad"
PINNED_WORKFLOW_BLOBS = {
    ".github/workflows/ci.yml": "bd47724a8895530da66749c912850160eafb680e",
    ".github/workflows/fast-lane-policy-drift.yml": "b25e970f966bcadcd7f2522689f738ba699a55c4",
    ".github/workflows/github-only-policy-drift.yml": "3f689c8ec65c3ca7853f1e53438ce095118d0b2f",
    ".github/workflows/github-only-policy-gate.yml": "3b67427d0abfd3dc0d6be1637966e20da0d158d6",
    ".github/workflows/github-only-queue-lint.yml": "b4ae7b810bfc561ea19c3875a8d356616f41da8d",
    ".github/workflows/live-auth-contract.yml": "64736e040291e4b4d9b13ffceaac56fa5c7907ec",
    ".github/workflows/public-repo-baseline.yml": "9f89de6846fbf1ee98e635228ea21473964154eb",
}

COLLABORATOR_PROVENANCE = "github-rest.repository-collaborators.v1"
TEAM_PROVENANCE = "github-repository-owner-user-no-teams.v1"
APP_INTEGRATION_PROVENANCE = "github-admin.repository-installed-apps-integrations.v1"

_ALLOWED_BLOB_MODES = frozenset({"100644", "100755", "120000"})
_ALLOWED_COLLABORATOR_PERMISSIONS = frozenset(
    {"pull", "read", "triage", "push", "write", "maintain", "admin"}
)
_WRITER_COLLABORATOR_PERMISSIONS = frozenset({"push", "write", "maintain", "admin"})
_ALLOWED_APP_ISSUES_PERMISSIONS = frozenset({"none", "read", "write"})
_ALLOWED_INTEGRATION_TYPES = frozenset({"github-app", "oauth-app", "integration"})

_TOP_LEVEL_PERMISSIONS_RE = re.compile(r"^permissions:(?:\s*(?:read-all|\{\}))?\s*(?:#.*)?$")
_DYNAMIC_TOP_LEVEL_PERMISSIONS_RE = re.compile(r"^permissions:\s*.+$")
_ISSUES_WRITE_RE = re.compile(r"^\s*issues:\s*write\s*(?:#.*)?$")
_WRITE_ALL_RE = re.compile(r"^\s*permissions:\s*write-all\s*(?:#.*)?$")
_ISSUE_MUTATION_RE = re.compile(
    r"(?:\bgh\s+issue\s+(?:create|edit|comment|close|reopen|delete|lock|unlock)\b"
    r"|[\"']gh[\"']\s*,\s*[\"']issue[\"']\s*,\s*[\"'](?:create|edit|comment|close|reopen|delete|lock|unlock)[\"']"
    r"|api\.github\.com/repos/[^\s\"']+/[^\s\"']+/issues(?:/|\b)"
    r"|/repos/[^\s\"']+/[^\s\"']+/issues(?:/|\b)"
    r"|\b(?:createIssue|updateIssue|addComment|closeIssue|reopenIssue)\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SourceBlob:
    path: str
    mode: str
    content: bytes


@dataclass(frozen=True)
class CollaboratorAccess:
    user_id: int
    login: str
    permission: str


@dataclass(frozen=True)
class TeamAccess:
    team_id: int
    slug: str
    permission: str


@dataclass(frozen=True)
class InstalledIntegrationAccess:
    integration_type: str
    integration_id: int
    slug: str
    issues_permission: str


@dataclass(frozen=True)
class CollaboratorSurface:
    complete: bool
    provenance: str
    entries: tuple[CollaboratorAccess, ...]


@dataclass(frozen=True)
class TeamSurface:
    complete: bool
    provenance: str
    entries: tuple[TeamAccess, ...]


@dataclass(frozen=True)
class InstalledAppSurface:
    complete: bool
    provenance: str
    entries: tuple[InstalledIntegrationAccess, ...]


@dataclass(frozen=True)
class AuthorizationSourceSnapshot:
    repository: str
    repository_id: int
    owner_type: str
    owner_id: int
    commit_sha: str
    tree_sha: str
    tree_complete: bool
    blobs: tuple[SourceBlob, ...]


@dataclass(frozen=True)
class GovernanceCollectionInput:
    observed_at: datetime
    source: AuthorizationSourceSnapshot
    collaborators: CollaboratorSurface
    teams: TeamSurface
    installed_apps: InstalledAppSurface


def _canonical_path(value: str) -> PurePosixPath:
    if type(value) is not str or not value or "\\" in value or "\x00" in value:
        raise P9GovernanceCollectorError("source blob path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise P9GovernanceCollectorError("source blob path is invalid")
    if path.as_posix() != value:
        raise P9GovernanceCollectorError("source blob path is not canonical")
    return path


def _git_blob_sha(data: bytes) -> str:
    if type(data) is not bytes:
        raise P9GovernanceCollectorError("source blob content must be bytes")
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _source_blob_index(blobs: Iterable[SourceBlob]) -> dict[str, tuple[str, str, str]]:
    index: dict[str, tuple[str, str, str]] = {}
    for blob in blobs:
        if not isinstance(blob, SourceBlob):
            raise P9GovernanceCollectorError("source snapshot contains invalid blob entry")
        path = _canonical_path(blob.path).as_posix()
        if blob.mode not in _ALLOWED_BLOB_MODES:
            raise P9GovernanceCollectorError("source snapshot contains unsupported blob mode")
        if path in index:
            raise P9GovernanceCollectorError("source snapshot contains duplicate blob path")
        try:
            text = blob.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise P9GovernanceCollectorError(
                "source snapshot contains an uninspectable non-UTF-8 blob"
            ) from exc
        index[path] = (blob.mode, _git_blob_sha(blob.content), text)
    if not index:
        raise P9GovernanceCollectorError("source snapshot is empty")
    return index


def _git_tree_sha(index: dict[str, tuple[str, str, str]]) -> str:
    root: dict[str, object] = {}
    for path, (mode, blob_sha, _) in index.items():
        parts = PurePosixPath(path).parts
        node = root
        for part in parts[:-1]:
            existing = node.get(part)
            if existing is None:
                child: dict[str, object] = {}
                node[part] = child
                node = child
            elif isinstance(existing, dict):
                node = existing
            else:
                raise P9GovernanceCollectorError("source snapshot has file/directory conflict")
        leaf = parts[-1]
        if leaf in node:
            raise P9GovernanceCollectorError("source snapshot has duplicate tree entry")
        node[leaf] = (mode, blob_sha)

    def hash_tree(node: dict[str, object]) -> str:
        entries: list[tuple[bytes, bytes]] = []
        for name, child in node.items():
            if isinstance(child, dict):
                mode = "40000"
                object_sha = hash_tree(child)
                sort_key = (name + "/").encode("utf-8")
            else:
                mode, object_sha = child
                sort_key = name.encode("utf-8")
            raw = (
                mode.encode("ascii")
                + b" "
                + name.encode("utf-8")
                + b"\0"
                + bytes.fromhex(object_sha)
            )
            entries.append((sort_key, raw))
        body = b"".join(raw for _, raw in sorted(entries, key=lambda item: item[0]))
        header = f"tree {len(body)}\0".encode("ascii")
        return hashlib.sha1(header + body).hexdigest()

    return hash_tree(root)


def _validate_source_snapshot(
    snapshot: AuthorizationSourceSnapshot,
) -> dict[str, tuple[str, str, str]]:
    if snapshot.repository != AUTHORIZATION_REPOSITORY:
        raise P9GovernanceCollectorError("authorization source repository mismatch")
    if snapshot.repository_id != AUTHORIZATION_REPOSITORY_ID:
        raise P9GovernanceCollectorError("authorization source repository identity mismatch")
    if snapshot.owner_type != "User" or snapshot.owner_id != AUTHORIZATION_OWNER_ID:
        raise P9GovernanceCollectorError("authorization repository owner identity mismatch")
    if snapshot.commit_sha != PINNED_AUTHORIZATION_SOURCE_SHA:
        raise P9GovernanceCollectorError("authorization source commit is not source-pinned")
    if snapshot.tree_sha != PINNED_AUTHORIZATION_SOURCE_TREE_SHA:
        raise P9GovernanceCollectorError("authorization source tree is not source-pinned")
    if snapshot.tree_complete is not True:
        raise P9GovernanceCollectorError("authorization source tree observation is incomplete")

    index = _source_blob_index(snapshot.blobs)
    computed_tree = _git_tree_sha(index)
    if computed_tree != snapshot.tree_sha:
        raise P9GovernanceCollectorError("authorization source tree content mismatch")

    actual_workflows = {
        path
        for path in index
        if path.startswith(".github/workflows/")
        and path.endswith((".yml", ".yaml"))
    }
    if actual_workflows != frozenset(PINNED_WORKFLOW_BLOBS):
        raise P9GovernanceCollectorError("authorization workflow inventory drift")
    for path, expected_blob in PINNED_WORKFLOW_BLOBS.items():
        if index[path][1] != expected_blob:
            raise P9GovernanceCollectorError(
                f"authorization workflow blob drift: {path}"
            )
    return index


def _scan_source_writers(
    index: dict[str, tuple[str, str, str]]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    workflow_writers: set[str] = set()
    token_writers: set[str] = set()
    for path, (_, blob_sha, text) in index.items():
        executable_source = (
            path.startswith(".github/workflows/")
            or path.startswith(".github/actions/")
            or path.startswith("scripts/")
        )
        if not executable_source:
            continue

        if path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml")):
            lines = text.splitlines()
            top_level_permissions = [
                line for line in lines if line.startswith("permissions:")
            ]
            if len(top_level_permissions) != 1:
                raise P9GovernanceCollectorError(
                    f"workflow must declare one explicit top-level permissions block: {path}"
                )
            declaration = top_level_permissions[0]
            if _TOP_LEVEL_PERMISSIONS_RE.fullmatch(declaration) is None:
                if _DYNAMIC_TOP_LEVEL_PERMISSIONS_RE.fullmatch(declaration):
                    raise P9GovernanceCollectorError(
                        f"workflow top-level permissions are dynamic or unsupported: {path}"
                    )
                raise P9GovernanceCollectorError(
                    f"workflow top-level permissions are malformed: {path}"
                )
            if any(_WRITE_ALL_RE.fullmatch(line) for line in lines) or any(
                _ISSUES_WRITE_RE.fullmatch(line) for line in lines
            ):
                workflow_writers.add(f"workflow:{path}@{blob_sha}")

        if _ISSUE_MUTATION_RE.search(text):
            token_writers.add(f"token-source:{path}@{blob_sha}")

    return tuple(sorted(workflow_writers)), tuple(sorted(token_writers))


def _writer_collaborators(surface: CollaboratorSurface) -> tuple[str, ...]:
    if surface.complete is not True or surface.provenance != COLLABORATOR_PROVENANCE:
        raise P9GovernanceCollectorError("collaborator writer surface is incomplete")
    identities: list[str] = []
    seen: set[int] = set()
    for entry in surface.entries:
        if type(entry.user_id) is not int or entry.user_id <= 0:
            raise P9GovernanceCollectorError("collaborator identity is invalid")
        if type(entry.login) is not str or not entry.login or entry.login.strip() != entry.login:
            raise P9GovernanceCollectorError("collaborator login is invalid")
        if entry.permission not in _ALLOWED_COLLABORATOR_PERMISSIONS:
            raise P9GovernanceCollectorError("collaborator permission is unknown")
        if entry.user_id in seen:
            raise P9GovernanceCollectorError("collaborator surface contains duplicates")
        seen.add(entry.user_id)
        if entry.permission in _WRITER_COLLABORATOR_PERMISSIONS:
            identities.append(f"user:{entry.user_id}")
    if AUTHORIZATION_OWNER_ID not in seen:
        raise P9GovernanceCollectorError("authorization repository owner is missing from collaborators")
    return tuple(sorted(identities))


def _writer_teams(surface: TeamSurface) -> tuple[str, ...]:
    if surface.complete is not True or surface.provenance != TEAM_PROVENANCE:
        raise P9GovernanceCollectorError("team writer surface is incomplete")
    if surface.entries:
        raise P9GovernanceCollectorError(
            "authorization repository is user-owned; team writer surface must be empty"
        )
    return ()


def _writer_apps(surface: InstalledAppSurface) -> tuple[str, ...]:
    if surface.complete is not True or surface.provenance != APP_INTEGRATION_PROVENANCE:
        raise P9GovernanceCollectorError("installed App/integration writer surface is incomplete")
    identities: list[str] = []
    seen: set[tuple[str, int]] = set()
    for entry in surface.entries:
        if entry.integration_type not in _ALLOWED_INTEGRATION_TYPES:
            raise P9GovernanceCollectorError("installed integration type is unknown")
        if type(entry.integration_id) is not int or entry.integration_id <= 0:
            raise P9GovernanceCollectorError("installed integration identity is invalid")
        if type(entry.slug) is not str or not entry.slug or entry.slug.strip() != entry.slug:
            raise P9GovernanceCollectorError("installed integration slug is invalid")
        if entry.issues_permission not in _ALLOWED_APP_ISSUES_PERMISSIONS:
            raise P9GovernanceCollectorError("installed integration Issues permission is unknown")
        identity_key = (entry.integration_type, entry.integration_id)
        if identity_key in seen:
            raise P9GovernanceCollectorError("installed integration surface contains duplicates")
        seen.add(identity_key)
        if entry.issues_permission == "write":
            prefix = "app" if entry.integration_type == "github-app" else entry.integration_type
            identities.append(f"{prefix}:{entry.integration_id}")
    return tuple(sorted(identities))


def collect_governance_writer_surface(
    value: GovernanceCollectionInput,
) -> GovernanceWriterSurfaceObservation:
    if not isinstance(value, GovernanceCollectionInput):
        raise P9GovernanceCollectorError("governance collection input is invalid")
    index = _validate_source_snapshot(value.source)
    workflow_writers, token_writers = _scan_source_writers(index)
    human_writers = _writer_collaborators(value.collaborators)
    team_writers = _writer_teams(value.teams)
    app_writers = _writer_apps(value.installed_apps)

    return GovernanceWriterSurfaceObservation(
        repository=AUTHORIZATION_REPOSITORY,
        repository_id=AUTHORIZATION_REPOSITORY_ID,
        observed_at=value.observed_at,
        covered_surfaces=_REQUIRED_GOVERNANCE_SURFACES,
        human_writers=human_writers,
        team_writers=team_writers,
        app_writers=app_writers,
        workflow_writers=workflow_writers,
        token_writers=token_writers,
        unknown_writers=(),
    )
