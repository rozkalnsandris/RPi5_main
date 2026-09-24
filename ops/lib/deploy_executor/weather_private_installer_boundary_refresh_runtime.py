from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
from typing import Any, Mapping, Protocol, Sequence

from .p9_canary import require_isolated_auth_surface
from .p9_isolated_auth_surface import load_contract
from .p9_runtime import build_p9_read_clients
from .protocol import (
    AUTHORIZATION_REPOSITORY,
    AUTHORIZATION_REPOSITORY_ID,
    QUEUE_REPOSITORY,
    AcceptedAuthorization,
    accept_issue,
    validate_queue_binding,
    verify_authorization_unchanged,
)
from .queue_normalizer import normalize_ready_queue
from .registry import BaselineContract, MutationBudget, OperationRegistry, OperationSpec, QueueMatch
from .weather_private_bigquery_host_bindings import (
    FixedPublicGitHubReadClient,
    PublicExactSourceEvidenceProvider,
)
from .weather_private_bigquery_host_installer_runtime import DurableInstallReplayAuthority
from .weather_private_bigquery_host_runtime import RPI5_MAIN_REPOSITORY_ID
from .weather_private_installer_boundary_refresh import (
    ENTRYPOINT_DESTINATION,
    ENTRYPOINT_MODE,
    ENTRYPOINT_SOURCE,
    MANAGER_CHECKOUT_RESOLVER,
    MUTATION_BUDGET,
    OPERATION_ID,
    REVIEWED_ORIGIN,
    ROLLBACK_POLICY,
    ROOT_GID,
    ROOT_UID,
    SOURCE_REPOSITORY,
    TARGET_ALIAS,
    TRUSTED_CHECKOUT,
    TRUSTED_CHECKOUT_MODE,
    BoundaryEvidence,
    BoundaryRefreshError,
    RefreshPlan,
    build_refresh_plan,
    public_plan,
)

IMPLEMENTATION_ISSUE = 721
AUTH_SURFACE = Path("/etc/rozkalns-deploy-executor-p9/executor-p9-isolated-auth-surface.json")
EXECUTOR_PRIVATE_KEY = Path("/etc/rozkalns-deploy-executor/github-app.pem")
EXECUTION_LOCATION_CLASS = "trusted-home-host"
DEPLOY_CLASS = "STRICT_LIVE_AUTH_REQUIRED"
ADAPTER_ID = "rpi5.weathernext-private-installer-boundary-refresh.fixed-v1"
BASELINE_RESOLVER_ID = "rpi5.weathernext-private-installer-boundary-refresh.fixed-state-v1"
MANAGER_CHECKOUT_BASENAME = "RPi5_main"
MAX_COMMAND_OUTPUT_BYTES = 64 * 1024
MAX_ENTRYPOINT_BYTES = 2 * 1024 * 1024
_SHA40 = re.compile(r"^[0-9a-f]{40}$")

REQUIRED_EXCLUSIONS = (
    "no clone reset clean pull merge rebase force or manager branch switch",
    "no caller-selected repository path command argv or environment authority",
    "no generic root shell or generic sudo authority",
    "no backend install",
    "no Weather application or private runtime materialization",
    "no Google ADC IAM project Analytics Hub or BigQuery action",
    "no SQLite schema corpus or snapshot mutation",
    "no Docker systemd package network or Cloudflare mutation",
    "no automatic retry cleanup rollback or alternate mutation path after consume",
)
DEPENDENCIES = (
    "source-contract:RPi5_main#700",
    "transport-source:RPi5_main#721",
    "weather-gate:rozkalns_weather#122",
)


class WeatherNextPrivateInstallerBoundaryRefreshRuntimeError(BoundaryRefreshError):
    pass


def _fail(message: str) -> None:
    raise WeatherNextPrivateInstallerBoundaryRefreshRuntimeError(message)


class CommandResultLike(Protocol):
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Any


@dataclass(frozen=True)
class ManagerCheckout:
    path: Path
    username: str
    uid: int
    gid: int
    home: Path


@dataclass(frozen=True)
class PreparedBoundary:
    exact_source_sha: str
    exact_entrypoint_sha256: str
    stale_head_sha: str
    stale_entrypoint_sha256: str
    manager: ManagerCheckout
    manager_snapshot: tuple[str, str]
    plan: RefreshPlan


@dataclass(frozen=True)
class CanonicalBoundaryRefreshEvidence:
    authorization_issue_number: int
    authorization_issue_id: int
    authorization_created_at: str
    request_id: str
    request_body_sha256: str
    current_source_sha: str
    queue_issue_number: int
    exact_entrypoint_sha256: str
    stale_head_sha: str
    plan: Mapping[str, object]


def _server_time(response: Any) -> datetime:
    value = getattr(response, "server_time", None)
    if not isinstance(value, datetime) or value.tzinfo is None:
        _fail("GitHub server time is unavailable")
    return value.astimezone(timezone.utc)


def _bounded_run(argv: Sequence[str], *, env: Mapping[str, str], runner: CommandRunner) -> CommandResultLike:
    try:
        result = runner(tuple(argv), env=dict(env))
    except TypeError:
        result = runner(tuple(argv))
    except Exception as exc:
        raise WeatherNextPrivateInstallerBoundaryRefreshRuntimeError(
            "fixed boundary-refresh command failed to run"
        ) from exc
    returncode = getattr(result, "returncode", None)
    stdout = getattr(result, "stdout", None)
    stderr = getattr(result, "stderr", None)
    if type(returncode) is not int or type(stdout) is not str or type(stderr) is not str:
        _fail("fixed boundary-refresh command returned unsupported result")
    if len(stdout.encode("utf-8")) > MAX_COMMAND_OUTPUT_BYTES or len(stderr.encode("utf-8")) > MAX_COMMAND_OUTPUT_BYTES:
        _fail("fixed boundary-refresh command output exceeded source limit")
    return result


def _default_runner(argv: Sequence[str], *, env: Mapping[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        tuple(argv),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=dict(env),
        shell=False,
        close_fds=True,
        timeout=60,
        check=False,
    )


def _root_env() -> Mapping[str, str]:
    return {
        "PATH": "/usr/sbin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "HOME": "/nonexistent",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }


def _manager_env(manager: ManagerCheckout) -> Mapping[str, str]:
    return {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "HOME": str(manager.home),
        "USER": manager.username,
        "LOGNAME": manager.username,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
    }


def _git_argv(checkout: Path, *args: str) -> tuple[str, ...]:
    return (
        "/usr/bin/git",
        "-c",
        f"safe.directory={checkout}",
        "--no-optional-locks",
        "-C",
        str(checkout),
        *args,
    )


def _root_git(checkout: Path, *args: str, runner: CommandRunner) -> CommandResultLike:
    allowed = {"rev-parse", "symbolic-ref", "status", "remote", "merge-base", "checkout"}
    if checkout != Path(TRUSTED_CHECKOUT) or not args or args[0] not in allowed:
        _fail("trusted-checkout Git escaped fixed allowlist")
    if args[0] == "checkout" and tuple(args[:2]) != ("checkout", "--detach"):
        _fail("trusted-checkout Git mutation escaped fixed detach-only allowlist")
    return _bounded_run(_git_argv(checkout, *args), env=_root_env(), runner=runner)


def _root_git_success(checkout: Path, *args: str, runner: CommandRunner) -> str:
    result = _root_git(checkout, *args, runner=runner)
    if result.returncode != 0:
        _fail("trusted-checkout Git failed closed")
    return result.stdout.strip()


def _manager_git(
    manager: ManagerCheckout,
    *args: str,
    mutation: bool,
    runner: CommandRunner,
) -> CommandResultLike:
    read_ops = {"rev-parse", "status", "remote", "merge-base"}
    mutation_ops = {"fetch"}
    if not args or (args[0] not in (mutation_ops if mutation else read_ops)):
        _fail("manager Git escaped fixed allowlist")
    git_argv = _git_argv(manager.path, *args)
    if os.geteuid() == manager.uid:
        return _bounded_run(git_argv, env=_manager_env(manager), runner=runner)
    if os.geteuid() != ROOT_UID:
        _fail("manager Git requires repository owner or root boundary")
    argv = (
        "/usr/sbin/runuser",
        "-u",
        manager.username,
        "--",
        "/usr/bin/env",
        "-i",
        f"HOME={manager.home}",
        f"USER={manager.username}",
        f"LOGNAME={manager.username}",
        "PATH=/usr/bin:/bin",
        "LANG=C.UTF-8",
        "LC_ALL=C.UTF-8",
        "GIT_TERMINAL_PROMPT=0",
        "GIT_CONFIG_NOSYSTEM=1",
        *git_argv,
    )
    return _bounded_run(argv, env=_root_env(), runner=runner)


def _manager_git_success(manager: ManagerCheckout, *args: str, mutation: bool, runner: CommandRunner) -> str:
    result = _manager_git(manager, *args, mutation=mutation, runner=runner)
    if result.returncode != 0:
        _fail("manager Git failed closed")
    return result.stdout.strip()


def _meta(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise WeatherNextPrivateInstallerBoundaryRefreshRuntimeError(
            f"fixed path metadata failed: {path.name}"
        ) from exc


def _require_dir(path: Path, *, uid: int | None = None, gid: int | None = None, mode: int | None = None) -> os.stat_result:
    value = _meta(path)
    if value is None or not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode):
        _fail(f"required fixed directory is unavailable: {path}")
    if uid is not None and value.st_uid != uid:
        _fail(f"required fixed directory owner drifted: {path}")
    if gid is not None and value.st_gid != gid:
        _fail(f"required fixed directory group drifted: {path}")
    if mode is not None and stat.S_IMODE(value.st_mode) != mode:
        _fail(f"required fixed directory mode drifted: {path}")
    return value


def _require_regular(path: Path, *, uid: int | None = None, gid: int | None = None, mode: int | None = None) -> os.stat_result:
    value = _meta(path)
    if value is None or not stat.S_ISREG(value.st_mode) or stat.S_ISLNK(value.st_mode) or value.st_nlink != 1:
        _fail(f"required fixed file is unavailable: {path}")
    if uid is not None and value.st_uid != uid:
        _fail(f"required fixed file owner drifted: {path}")
    if gid is not None and value.st_gid != gid:
        _fail(f"required fixed file group drifted: {path}")
    if mode is not None and stat.S_IMODE(value.st_mode) != mode:
        _fail(f"required fixed file mode drifted: {path}")
    if not 0 < value.st_size <= MAX_ENTRYPOINT_BYTES:
        _fail("required fixed file size drifted")
    return value


def _read_regular(path: Path) -> bytes:
    before = _require_regular(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size):
            _fail("fixed file changed before read")
        raw = b""
        while len(raw) <= MAX_ENTRYPOINT_BYTES:
            chunk = os.read(fd, min(65536, MAX_ENTRYPOINT_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        if len(raw) != opened.st_size or len(raw) > MAX_ENTRYPOINT_BYTES:
            _fail("fixed file changed during read")
        after = path.lstat()
        if (after.st_dev, after.st_ino, after.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
            _fail("fixed file path changed during read")
        return raw
    finally:
        os.close(fd)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _resolve_manager_checkout(*, runner: CommandRunner) -> ManagerCheckout:
    trusted = Path(TRUSTED_CHECKOUT)
    _require_dir(trusted, uid=ROOT_UID, gid=ROOT_GID, mode=TRUSTED_CHECKOUT_MODE)
    common = Path(
        _root_git_success(
            trusted,
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
            runner=runner,
        )
    )
    if not common.is_absolute() or common.name != ".git":
        _fail("manager Git common directory identity drifted")
    common_info = _require_dir(common)
    manager_path = common.parent
    manager_info = _require_dir(manager_path)
    if manager_info.st_uid == ROOT_UID or common_info.st_uid != manager_info.st_uid:
        _fail("manager checkout ownership drifted")
    try:
        account = pwd.getpwuid(manager_info.st_uid)
    except KeyError as exc:
        raise WeatherNextPrivateInstallerBoundaryRefreshRuntimeError(
            "manager checkout owner account is unavailable"
        ) from exc
    home = Path(account.pw_dir)
    if not home.is_absolute() or ".." in home.parts or manager_path != home / MANAGER_CHECKOUT_BASENAME:
        _fail("manager checkout does not match repo-owner-home resolver")
    return ManagerCheckout(manager_path, account.pw_name, account.pw_uid, account.pw_gid, home)


def _manager_snapshot(manager: ManagerCheckout, *, runner: CommandRunner) -> tuple[str, str]:
    head = _manager_git_success(manager, "rev-parse", "HEAD", mutation=False, runner=runner)
    status_text = _manager_git_success(
        manager,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        mutation=False,
        runner=runner,
    )
    return head, _sha256(status_text.encode("utf-8", "strict"))


def _public_entrypoint(public_client: FixedPublicGitHubReadClient, source_sha: str) -> bytes:
    response = public_client.get_json(
        f"/repos/{SOURCE_REPOSITORY}/contents/{ENTRYPOINT_SOURCE}?ref={source_sha}"
    ).value
    if type(response) is not dict or response.get("encoding") != "base64" or type(response.get("content")) is not str:
        _fail("reviewed exact-source entrypoint response is malformed")
    try:
        raw = base64.b64decode(response["content"], validate=True)
    except (ValueError, TypeError) as exc:
        raise WeatherNextPrivateInstallerBoundaryRefreshRuntimeError(
            "reviewed exact-source entrypoint payload is malformed"
        ) from exc
    if not 0 < len(raw) <= MAX_ENTRYPOINT_BYTES:
        _fail("reviewed exact-source entrypoint size drifted")
    return raw


def _reviewed_ancestor(public_client: FixedPublicGitHubReadClient, stale_sha: str, current_sha: str) -> bool:
    if not _SHA40.fullmatch(stale_sha) or not _SHA40.fullmatch(current_sha):
        return False
    value = public_client.get_json(
        f"/repos/{SOURCE_REPOSITORY}/compare/{stale_sha}...{current_sha}"
    ).value
    return type(value) is dict and value.get("status") in {"ahead", "identical"}


class PosixBoundaryRefreshBackend:
    def __init__(self, *, runner: CommandRunner = _default_runner):
        self._runner = runner
        self._prepared: PreparedBoundary | None = None

    def prepare(
        self,
        exact_source_sha: str,
        *,
        exact_entrypoint: bytes,
        reviewed_ancestor: bool,
        exact_main_ci_success: bool,
    ) -> PreparedBoundary:
        if type(exact_source_sha) is not str or _SHA40.fullmatch(exact_source_sha) is None:
            _fail("exact boundary-refresh source SHA is invalid")
        manager = _resolve_manager_checkout(runner=self._runner)
        if _manager_git_success(manager, "remote", "get-url", "origin", mutation=False, runner=self._runner) != REVIEWED_ORIGIN:
            _fail("manager checkout origin drifted")
        manager_snapshot = _manager_snapshot(manager, runner=self._runner)
        trusted = Path(TRUSTED_CHECKOUT)
        installed = Path(ENTRYPOINT_DESTINATION)
        trusted_meta = _require_dir(trusted, uid=ROOT_UID, gid=ROOT_GID, mode=TRUSTED_CHECKOUT_MODE)
        installed_meta = _require_regular(installed, uid=ROOT_UID, gid=ROOT_GID, mode=ENTRYPOINT_MODE)
        del trusted_meta, installed_meta
        trusted_origin = _root_git_success(trusted, "remote", "get-url", "origin", runner=self._runner)
        trusted_head = _root_git_success(trusted, "rev-parse", "HEAD", runner=self._runner)
        detached = _root_git(trusted, "symbolic-ref", "-q", "HEAD", runner=self._runner)
        clean = _root_git_success(
            trusted,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            runner=self._runner,
        ) == ""
        trusted_entrypoint = _read_regular(trusted / ENTRYPOINT_SOURCE)
        installed_entrypoint = _read_regular(installed)
        exact_hash = _sha256(exact_entrypoint)
        stale_hash = _sha256(trusted_entrypoint)
        evidence = BoundaryEvidence(
            exact_source_sha=exact_source_sha,
            current_main_sha=exact_source_sha,
            exact_main_ci_success=exact_main_ci_success,
            manager_origin=REVIEWED_ORIGIN,
            manager_snapshot_stable=True,
            trusted_present=True,
            entrypoint_present=True,
            trusted_uid=ROOT_UID,
            trusted_gid=ROOT_GID,
            trusted_mode=TRUSTED_CHECKOUT_MODE,
            trusted_origin=trusted_origin,
            trusted_head_sha=trusted_head,
            trusted_detached=detached.returncode == 1 and detached.stdout == "" and detached.stderr == "",
            trusted_clean=clean,
            trusted_head_reviewed_ancestor=reviewed_ancestor,
            trusted_entrypoint_matches_head=installed_entrypoint == trusted_entrypoint,
            installed_uid=ROOT_UID,
            installed_gid=ROOT_GID,
            installed_mode=ENTRYPOINT_MODE,
            installed_entrypoint_matches_head=installed_entrypoint == trusted_entrypoint,
            trusted_entrypoint_matches_exact_source=trusted_entrypoint == exact_entrypoint,
            installed_entrypoint_matches_exact_source=installed_entrypoint == exact_entrypoint,
        )
        plan = build_refresh_plan(evidence)
        prepared = PreparedBoundary(
            exact_source_sha,
            exact_hash,
            trusted_head,
            stale_hash,
            manager,
            manager_snapshot,
            plan,
        )
        self._prepared = prepared
        return prepared

    def _require_prepared_unchanged(self, prepared: PreparedBoundary) -> None:
        if self._prepared != prepared:
            _fail("boundary-refresh prepared identity drifted")
        if _manager_snapshot(prepared.manager, runner=self._runner) != prepared.manager_snapshot:
            _fail("manager HEAD/index/worktree snapshot drifted")

    def apply(self, prepared: PreparedBoundary) -> Mapping[str, object]:
        if os.geteuid() != ROOT_UID:
            _fail("installer-boundary refresh mutation requires root boundary")
        self._require_prepared_unchanged(prepared)
        plan = prepared.plan
        if plan.operation_id != OPERATION_ID or plan.target_alias != TARGET_ALIAS or plan.source_sha != prepared.exact_source_sha:
            _fail("boundary-refresh plan identity drifted")
        if plan.prior_state == "EXACT":
            if plan.steps:
                _fail("exact boundary-refresh state cannot contain mutations")
            return {
                "status": "ALREADY_EXACT",
                "operation_id": OPERATION_ID,
                "target_alias": TARGET_ALIAS,
                "source_sha": prepared.exact_source_sha,
                "authorization_consumed": False,
                "production_mutation_started": False,
                "mutation_categories": [],
                "rollback_policy": ROLLBACK_POLICY,
            }
        if plan.prior_state != "STALE" or tuple((step.category, step.maximum) for step in plan.steps) != MUTATION_BUDGET:
            _fail("boundary-refresh mutation budget drifted")

        executed: list[str] = []
        manager = prepared.manager
        trusted = Path(TRUSTED_CHECKOUT)
        installed = Path(ENTRYPOINT_DESTINATION)
        _manager_git_success(
            manager,
            "fetch",
            "--no-tags",
            "origin",
            "refs/heads/main:refs/remotes/origin/main",
            mutation=True,
            runner=self._runner,
        )
        executed.append(MUTATION_BUDGET[0][0])
        if _manager_git_success(manager, "rev-parse", "refs/remotes/origin/main", mutation=False, runner=self._runner) != prepared.exact_source_sha:
            _fail("fetched origin/main does not equal authorized source SHA")
        if _manager_git(manager, "merge-base", "--is-ancestor", prepared.stale_head_sha, prepared.exact_source_sha, mutation=False, runner=self._runner).returncode != 0:
            _fail("stale trusted checkout is not a reviewed ancestor after fetch")
        self._require_prepared_unchanged(prepared)

        if _root_git_success(trusted, "rev-parse", "HEAD", runner=self._runner) != prepared.stale_head_sha:
            _fail("trusted checkout HEAD drifted before advance")
        if _sha256(_read_regular(trusted / ENTRYPOINT_SOURCE)) != prepared.stale_entrypoint_sha256:
            _fail("trusted entrypoint changed before advance")
        if _sha256(_read_regular(installed)) != prepared.stale_entrypoint_sha256:
            _fail("installed entrypoint changed before advance")
        _root_git_success(trusted, "checkout", "--detach", prepared.exact_source_sha, runner=self._runner)
        executed.append(MUTATION_BUDGET[1][0])
        if _root_git_success(trusted, "rev-parse", "HEAD", runner=self._runner) != prepared.exact_source_sha:
            _fail("trusted checkout did not advance to exact source")
        if _root_git(trusted, "symbolic-ref", "-q", "HEAD", runner=self._runner).returncode != 1:
            _fail("trusted checkout is not detached after advance")
        if _root_git_success(trusted, "status", "--porcelain=v1", "--untracked-files=all", runner=self._runner):
            _fail("trusted checkout is not clean after advance")
        if _root_git_success(trusted, "remote", "get-url", "origin", runner=self._runner) != REVIEWED_ORIGIN:
            _fail("trusted checkout origin drifted after advance")
        exact_raw = _read_regular(trusted / ENTRYPOINT_SOURCE)
        if _sha256(exact_raw) != prepared.exact_entrypoint_sha256:
            _fail("trusted exact-source entrypoint bytes drifted")
        self._require_prepared_unchanged(prepared)

        if _sha256(_read_regular(installed)) != prepared.exact_entrypoint_sha256:
            before = _require_regular(installed, uid=ROOT_UID, gid=ROOT_GID, mode=ENTRYPOINT_MODE)
            flags = os.O_WRONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(installed, flags)
            try:
                opened = os.fstat(fd)
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                    _fail("installed entrypoint changed before replacement")
                os.ftruncate(fd, 0)
                offset = 0
                while offset < len(exact_raw):
                    written = os.write(fd, exact_raw[offset:])
                    if written <= 0:
                        _fail("installed entrypoint replacement failed closed")
                    offset += written
                os.fchmod(fd, ENTRYPOINT_MODE)
                os.fchown(fd, ROOT_UID, ROOT_GID)
                os.fsync(fd)
            finally:
                os.close(fd)
            executed.append(MUTATION_BUDGET[2][0])
        _require_regular(installed, uid=ROOT_UID, gid=ROOT_GID, mode=ENTRYPOINT_MODE)
        if _sha256(_read_regular(installed)) != prepared.exact_entrypoint_sha256:
            _fail("installed entrypoint postcondition failed")
        self._require_prepared_unchanged(prepared)
        return {
            "status": "BOUNDARY_EXACT",
            "operation_id": OPERATION_ID,
            "target_alias": TARGET_ALIAS,
            "source_sha": prepared.exact_source_sha,
            "authorization_consumed": True,
            "production_mutation_started": True,
            "mutation_categories": executed,
            "rollback_policy": ROLLBACK_POLICY,
        }


def _fixed_registry() -> OperationRegistry:
    operation = OperationSpec(
        operation_id=OPERATION_ID,
        source_repository=SOURCE_REPOSITORY,
        queue_match=QueueMatch(
            target_alias=TARGET_ALIAS,
            execution_location_class=EXECUTION_LOCATION_CLASS,
            repository_entrypoint="ops/bin/rpi5-weathernext-private-host-privileged-install",
            deploy_class=DEPLOY_CLASS,
        ),
        target_alias=TARGET_ALIAS,
        adapter_id=ADAPTER_ID,
        authorization_class="STRICT",
        ordinary_live_all_eligible=False,
        baseline=BaselineContract(kind="resolver", resolver_id=BASELINE_RESOLVER_ID),
        mutation_budget=tuple(MutationBudget(category=c, max_operations=m) for c, m in MUTATION_BUDGET),
        rollback_policy=ROLLBACK_POLICY,
        exclusions=REQUIRED_EXCLUSIONS,
        dependencies=DEPENDENCIES,
        preflight=(
            "owner LIVE-AUTH and READY Queue are independently revalidated",
            "exact current RPi5_main required CI is revalidated",
            "fixed manager origin and HEAD/index/worktree snapshot are stable",
            "fixed installed boundary classifies through the #700 classifier",
            "stale trusted head is a reviewed ancestor of exact current source",
        ),
        postconditions=(
            "fixed trusted checkout is clean detached at exact current source with reviewed origin",
            "installed entrypoint is root-owned 0755 and byte-exact to reviewed exact-source blob",
            "manager HEAD/index/worktree snapshot remains unchanged",
        ),
        required_github_evidence=(
            "owner-authored non-App LIVE-AUTH",
            "READY Queue exact operation target source and mutation budget binding",
            "current RPi5_main exact-main required CI",
        ),
    )
    return OperationRegistry(schema_version=1, execution_enabled=False, operations=(operation,))


def _require_live_authority(accepted: AcceptedAuthorization) -> Mapping[str, Any]:
    payload = accepted.payload
    expected = {
        "queue_repository": QUEUE_REPOSITORY,
        "source_repository": SOURCE_REPOSITORY,
        "target_alias": TARGET_ALIAS,
        "operation_id": OPERATION_ID,
        "expected_baseline": {"kind": "resolver", "value": BASELINE_RESOLVER_ID},
        "mutation_budget": [
            {"category": category, "max_operations": maximum}
            for category, maximum in MUTATION_BUDGET
        ],
        "rollback_policy": ROLLBACK_POLICY,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            _fail(f"canonical boundary-refresh LIVE-AUTH {field} drifted")
    exclusions = payload.get("exclusions")
    if type(exclusions) is not list or not set(REQUIRED_EXCLUSIONS).issubset(set(exclusions)):
        _fail("canonical boundary-refresh LIVE-AUTH exclusions drifted")
    return payload


def _require_queue(normalized: Any) -> Mapping[str, Any]:
    if getattr(normalized, "execution_enabled", None) is not False:
        _fail("boundary-refresh registry unexpectedly enables execution")
    operation = getattr(normalized, "operation", None)
    expected = {
        "operation_id": OPERATION_ID,
        "source_repository": SOURCE_REPOSITORY,
        "target_alias": TARGET_ALIAS,
        "adapter_id": ADAPTER_ID,
        "authorization_class": "STRICT",
        "ordinary_live_all_eligible": False,
        "rollback_policy": ROLLBACK_POLICY,
    }
    for field, value in expected.items():
        if getattr(operation, field, None) != value:
            _fail(f"boundary-refresh Queue {field} drifted")
    observed_budget = tuple((item.category, item.max_operations) for item in getattr(operation, "mutation_budget", ()))
    if observed_budget != MUTATION_BUDGET:
        _fail("boundary-refresh Queue mutation budget drifted")
    baseline = getattr(operation, "baseline", None)
    if getattr(baseline, "kind", None) != "resolver" or getattr(baseline, "resolver_id", None) != BASELINE_RESOLVER_ID:
        _fail("boundary-refresh Queue baseline drifted")
    return normalized.as_protocol_queue()


class ConcreteBoundaryRefreshRevalidator:
    def __init__(
        self,
        *,
        authorization_client: Any,
        queue_client: Any,
        sources: PublicExactSourceEvidenceProvider,
        public_client: FixedPublicGitHubReadClient,
        auth_surface: Any,
        replay: DurableInstallReplayAuthority,
        backend: PosixBoundaryRefreshBackend,
    ):
        require_isolated_auth_surface(auth_surface)
        self._authorization_client = authorization_client
        self._queue_client = queue_client
        self._sources = sources
        self._public_client = public_client
        self._auth_surface = auth_surface
        self._replay = replay
        self._backend = backend
        self._registry = _fixed_registry()
        self.accepted: AcceptedAuthorization | None = None
        self.prepared: PreparedBoundary | None = None

    def revalidate(self, issue_number: int) -> CanonicalBoundaryRefreshEvidence:
        if type(issue_number) is not int or not 1 <= issue_number <= 2_147_483_647:
            _fail("authorization issue number is invalid")
        require_isolated_auth_surface(self._auth_surface)
        issue_response = self._authorization_client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{issue_number}"
        )
        accepted = accept_issue(
            issue_response.value,
            repository_id=AUTHORIZATION_REPOSITORY_ID,
            repository_full_name=AUTHORIZATION_REPOSITORY,
            server_time=_server_time(issue_response),
            governance_ok=True,
            approved_operator_app_ids=frozenset(),
        )
        payload = _require_live_authority(accepted)
        queue_issue_number = payload.get("queue_issue")
        if type(queue_issue_number) is not int or queue_issue_number < 1:
            _fail("boundary-refresh Queue issue number is invalid")
        queue_response = self._queue_client.get_json(
            f"/repos/{QUEUE_REPOSITORY}/issues/{queue_issue_number}"
        )
        normalized = normalize_ready_queue(
            queue_response.value,
            repository_full_name=QUEUE_REPOSITORY,
            registry=self._registry,
        )
        validate_queue_binding(accepted, _require_queue(normalized))
        rpi = self._sources.load_exact_source(SOURCE_REPOSITORY, RPI5_MAIN_REPOSITORY_ID)
        if payload.get("source_sha") != rpi.source_sha or rpi.current_main_sha != rpi.source_sha or not rpi.required_ci_success:
            _fail("boundary-refresh source is not exact current RPi5_main")
        exact_entrypoint = _public_entrypoint(self._public_client, rpi.source_sha)

        trusted = Path(TRUSTED_CHECKOUT)
        trusted_head = _root_git_success(trusted, "rev-parse", "HEAD", runner=self._backend._runner)
        ancestor = _reviewed_ancestor(self._public_client, trusted_head, rpi.source_sha)
        prepared = self._backend.prepare(
            rpi.source_sha,
            exact_entrypoint=exact_entrypoint,
            reviewed_ancestor=ancestor,
            exact_main_ci_success=True,
        )
        if self._replay.is_available(accepted) is not True:
            _fail("boundary-refresh LIVE-AUTH is unavailable for one-shot consume")
        final = self._authorization_client.get_json(
            f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{issue_number}"
        )
        verify_authorization_unchanged(
            accepted,
            final.value,
            server_time=_server_time(final),
            governance_ok=True,
            approved_operator_app_ids=frozenset(),
        )
        if self._replay.is_available(accepted) is not True:
            _fail("boundary-refresh LIVE-AUTH replay state drifted")
        self.accepted = accepted
        self.prepared = prepared
        return CanonicalBoundaryRefreshEvidence(
            issue_number,
            accepted.issue_id,
            accepted.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            accepted.request_id,
            accepted.raw_body_sha256,
            rpi.source_sha,
            queue_issue_number,
            prepared.exact_entrypoint_sha256,
            prepared.stale_head_sha,
            public_plan(prepared.plan),
        )


def _stable(first: CanonicalBoundaryRefreshEvidence, final: CanonicalBoundaryRefreshEvidence) -> None:
    if first != final:
        _fail("canonical boundary-refresh evidence drifted")


def execute_prevalidated_refresh(
    evidence: CanonicalBoundaryRefreshEvidence,
    *,
    prepared: PreparedBoundary,
    accepted: AcceptedAuthorization,
    replay: DurableInstallReplayAuthority,
    backend: PosixBoundaryRefreshBackend,
) -> Mapping[str, object]:
    if evidence.request_id != accepted.request_id or evidence.current_source_sha != prepared.exact_source_sha:
        _fail("boundary-refresh accepted authorization identity drifted")
    if public_plan(prepared.plan) != evidence.plan:
        _fail("boundary-refresh plan drifted immediately before consume")
    if prepared.plan.prior_state == "EXACT":
        return {
            "status": "ALREADY_EXACT",
            "operation_id": OPERATION_ID,
            "target_alias": TARGET_ALIAS,
            "source_sha": evidence.current_source_sha,
            "authorization_consumed": False,
            "production_mutation_started": False,
            "mutation_categories": [],
            "rollback_policy": ROLLBACK_POLICY,
        }
    replay.consume(accepted.request_id)
    receipt = dict(backend.apply(prepared))
    replay.mark_succeeded(accepted.request_id)
    receipt["authorization_consumed"] = True
    return receipt


def run_privileged_installer_boundary_refresh(authorization_issue_number: int) -> Mapping[str, object]:
    if os.geteuid() != ROOT_UID:
        _fail("installer-boundary refresh must run as root")
    replay = DurableInstallReplayAuthority()
    try:
        auth_surface = load_contract(AUTH_SURFACE)
        require_isolated_auth_surface(auth_surface)
        clients = build_p9_read_clients(auth_surface=auth_surface, private_key=EXECUTOR_PRIVATE_KEY)
        public_client = FixedPublicGitHubReadClient()
        sources = PublicExactSourceEvidenceProvider(client=public_client)
        backend = PosixBoundaryRefreshBackend()
        revalidator = ConcreteBoundaryRefreshRevalidator(
            authorization_client=clients.authorization,
            queue_client=clients.queue,
            sources=sources,
            public_client=public_client,
            auth_surface=auth_surface,
            replay=replay,
            backend=backend,
        )
        first = revalidator.revalidate(authorization_issue_number)
        final = revalidator.revalidate(authorization_issue_number)
        _stable(first, final)
        preconsume = revalidator.revalidate(authorization_issue_number)
        _stable(final, preconsume)
        accepted = revalidator.accepted
        prepared = revalidator.prepared
        if accepted is None or prepared is None:
            _fail("boundary-refresh canonical revalidation did not prepare execution")
        return execute_prevalidated_refresh(
            preconsume,
            prepared=prepared,
            accepted=accepted,
            replay=replay,
            backend=backend,
        )
    except WeatherNextPrivateInstallerBoundaryRefreshRuntimeError:
        raise
    except BoundaryRefreshError as exc:
        raise WeatherNextPrivateInstallerBoundaryRefreshRuntimeError(str(exc)) from exc
    except Exception:
        raise WeatherNextPrivateInstallerBoundaryRefreshRuntimeError(
            "WeatherNext private installer-boundary refresh failed closed"
        ) from None


def source_readiness() -> Mapping[str, object]:
    return {
        "implementation_issue": IMPLEMENTATION_ISSUE,
        "source_contract_issue": 700,
        "operation_id": OPERATION_ID,
        "target_alias": TARGET_ALIAS,
        "source_repository": SOURCE_REPOSITORY,
        "caller_authority": ("authorization_issue_number",),
        "manager_checkout_resolver": MANAGER_CHECKOUT_RESOLVER,
        "trusted_checkout": TRUSTED_CHECKOUT,
        "entrypoint_source": ENTRYPOINT_SOURCE,
        "entrypoint_destination": ENTRYPOINT_DESTINATION,
        "mutation_budget": MUTATION_BUDGET,
        "rollback_policy": ROLLBACK_POLICY,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
        "generic_shell_authority": False,
        "backend_install_allowed": False,
        "weather_application_stage_allowed": False,
        "private_runtime_materialization_allowed": False,
        "google_action_allowed": False,
        "bigquery_action_allowed": False,
        "sqlite_write_allowed": False,
        "docker_systemd_package_network_cloudflare_allowed": False,
        "source_merge_authorizes_live": False,
        "production_mutation_started": False,
    }
