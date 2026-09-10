from __future__ import annotations

import ctypes
from dataclasses import dataclass
import errno
import json
import os
from pathlib import Path
import pwd
import re
import sqlite3
import stat
import subprocess
from typing import Any, Callable, Mapping, Protocol, Sequence

from .p9_canary import require_isolated_auth_surface
from .p9_isolated_auth_surface import load_contract
from .p9_runtime import build_p9_read_clients
from .protocol import (
    AUTHORIZATION_REPOSITORY_ID,
    QUEUE_REPOSITORY,
    AcceptedAuthorization,
)
from .registry import load_registry
from .state import EXPECTED_COLUMNS, STATE_DB_APPLICATION_ID, STATE_DB_SCHEMA_VERSION, StateStore
from .weather_public_runtime_adapter import BASELINE_RESOLVER_ID, OPERATION_ID, SOURCE_REPOSITORY, TARGET_ALIAS
from .weather_public_runtime_bootstrap import (
    BASELINE_EVIDENCE_SCHEMA,
    FORECAST_MODELS,
    RUN_HOURS,
    TRUTH_STATION_ID,
    parse_weather_bootstrap_baseline,
)
from .weather_public_runtime_composite import (
    COMPOSITE_GATE_ORDER,
    FULL_MUTATION_BUDGET,
    HOST_ALIAS,
    RPI5_MIN_REVIEWED_ANCESTOR,
    ConcreteCanonicalWeatherCompositeRevalidator,
    FixedPublicGitHubReadClient,
    WeatherCompositeAuthorityEvidence,
)
from .weather_public_runtime_execution import (
    ACTIVATION_FILE,
    ACTIVATION_SCHEMA,
    RELEASE_ROOT,
    WeatherExecutablePlan,
    build_weather_executable_plan,
)
from .weather_public_runtime_helper_launch import WeatherHelperLaunchReceipt, WeatherOneShotStageLauncher
from .weather_public_runtime_host_wiring import build_weather_host_wiring_plan, expected_helper_bindings
from .weather_public_runtime_privileged_install import (
    TRUSTED_INSTALL_CHECKOUT_NAME as PRIVILEGED_INSTALL_CHECKOUT_NAME,
    expected_install_artifacts,
)
from .weather_public_runtime_preactivation import (
    ENVELOPE_SCHEMA,
    RESULT as PREACTIVATION_RESULT,
    WeatherPreactivationEnvelope,
    WeatherPreactivationStageBinding,
)
from .weather_public_runtime_stage_helper import HOST_VOLUME, TIMER_NAME

OPERATOR_SCHEMA = "rozkalns-weather.public-runtime-composite-operator.v1"
OPERATOR_RESULT = "WEATHER_PUBLIC_RUNTIME_COMPOSITE_COMPLETE"
OPERATOR_STATUS = "SOURCE_READY_HOST_NOT_INSTALLED"
CALLER_AUTHORITY = ("authorization_issue_number",)
FIXED_OWNER_ACCOUNT = "andris"
MANAGER_CHECKOUT_NAME = "RPi5_main"
TRUSTED_CHECKOUT_NAME = PRIVILEGED_INSTALL_CHECKOUT_NAME
RPi5_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
STATE_DB_PATH = Path("/var/lib/rozkalns-deploy-executor-p9/state.sqlite3")
AUTH_SURFACE_PATH = Path("/etc/rozkalns-deploy-executor-p9/executor-p9-isolated-auth-surface.json")
EXECUTOR_KEY_PATH = Path("/etc/rozkalns-deploy-executor/github-app.pem")
OPERATOR_SUPPORT_ROOT = Path("/usr/local/libexec/rozkalns-weather-public-runtime-operator")
OPERATOR_REGISTRY_PATH = OPERATOR_SUPPORT_ROOT / "executor-operations.json"
HELPER_MANIFEST_RELATIVE = Path("ops/deploy/weather-public-runtime-helper-install.json")
HELPER_SUPPORT_ROOT = Path("/usr/local/libexec/rozkalns-weather-public-runtime")
HELPER_EXECUTABLE = Path("/usr/local/libexec/rozkalns-weather-public-runtime-stage-helper")
ACTIVATION_PATH = Path(ACTIVATION_FILE)
SYSTEMD_TIMER_PATH = Path("/etc/systemd/system") / TIMER_NAME
COMPOSE_PROJECT = "rozkalns-weather-public"
COMPOSE_RELATIVE = Path("deploy/docker-compose.public.yml")
ROOT_UID = 0
ROOT_GID = 0
MAX_COMMAND_OUTPUT = 65536
RENAME_NOREPLACE = 1
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FIXED_COMMAND_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
}


class WeatherCompositeOperatorError(RuntimeError):
    def __init__(
        self,
        stage: str,
        *,
        authorization_reuse_forbidden: bool = False,
        host_mutation_started: bool = False,
        production_mutation_started: bool = False,
    ):
        self.stage = stage
        self.authorization_reuse_forbidden = authorization_reuse_forbidden
        self.host_mutation_started = host_mutation_started
        self.production_mutation_started = production_mutation_started
        super().__init__(stage)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class WeatherReplayConsumptionReceipt:
    request_id: str
    state: str
    availability_checks: int
    durable_replay_consumed: bool
    replay_mutation_started: bool
    production_mutation_started: bool = False


@dataclass(frozen=True)
class WeatherOperatorMutationReceipt:
    gate_id: str
    mutation_categories: tuple[tuple[str, int], ...]
    host_mutation_started: bool
    production_mutation_started: bool = False


@dataclass(frozen=True)
class WeatherCompositeOperatorReceipt:
    schema: str
    result: str
    authorization_issue_number: int
    request_id: str
    source_sha: str
    rpi5_main_sha: str
    target_alias: str
    completed_gates: tuple[str, ...]
    mutation_counts: tuple[tuple[str, int], ...]
    read_only_invocations: tuple[tuple[str, int], ...]
    durable_replay_consumed: bool
    authorization_reuse_forbidden: bool
    host_mutation_started: bool
    production_mutation_started: bool
    automatic_retry: bool = False
    automatic_cleanup: bool = False
    automatic_rollback: bool = False


class FixedCommandRunner(Protocol):
    def __call__(self, argv: Sequence[str], *, env: Mapping[str, str] | None = None, user: int | None = None, group: int | None = None) -> CommandResult: ...


class WeatherOperatorHostMutator(Protocol):
    def trusted_checkout_fetch(self, expected_sha: str) -> WeatherOperatorMutationReceipt: ...
    def trusted_checkout_worktree_add(self, expected_sha: str) -> WeatherOperatorMutationReceipt: ...
    def install_helper(self, expected_sha: str) -> WeatherOperatorMutationReceipt: ...
    def publish_activation(self, plan: WeatherExecutablePlan) -> WeatherOperatorMutationReceipt: ...


def _fail(message: str) -> None:
    raise RuntimeError(message)


def run_fixed_command(
    argv: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    user: int | None = None,
    group: int | None = None,
) -> CommandResult:
    fixed = tuple(argv)
    if not fixed or any(type(item) is not str or not item for item in fixed):
        _fail("fixed command argv is invalid")
    kwargs: dict[str, Any] = {}
    if user is not None:
        kwargs.update(user=user, group=group, extra_groups=())
    try:
        result = subprocess.run(
            fixed,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
            check=False,
            shell=False,
            env=dict(FIXED_COMMAND_ENV if env is None else env),
            **kwargs,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("fixed command failed closed") from exc
    if len(result.stdout.encode()) > MAX_COMMAND_OUTPUT or len(result.stderr.encode()) > MAX_COMMAND_OUTPUT:
        _fail("fixed command output exceeded source limit")
    return CommandResult(result.returncode, result.stdout, result.stderr)


def _require_success(result: CommandResult, where: str) -> str:
    if type(result) is not CommandResult or result.returncode != 0:
        _fail(f"{where} failed closed")
    return result.stdout


def _write_all(fd: int, raw: bytes) -> None:
    view = memoryview(raw)
    offset = 0
    while offset < len(view):
        written = os.write(fd, view[offset:])
        if written <= 0:
            _fail("Weather bounded file write made no progress")
        offset += written


def _safe_relative(value: Any, where: str) -> Path:
    if type(value) is not str or not value or "\x00" in value:
        _fail(f"{where} path is invalid")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        _fail(f"{where} path escapes fixed source root")
    return path


def _require_regular(path: Path, *, uid: int | None = None, gid: int | None = None, mode: int | None = None) -> os.stat_result:
    try:
        meta = path.lstat()
    except OSError as exc:
        raise RuntimeError(f"required file is absent: {path.name}") from exc
    if not stat.S_ISREG(meta.st_mode) or stat.S_ISLNK(meta.st_mode) or meta.st_nlink != 1:
        _fail(f"required file identity is unsafe: {path.name}")
    if uid is not None and meta.st_uid != uid:
        _fail(f"required file owner drifted: {path.name}")
    if gid is not None and meta.st_gid != gid:
        _fail(f"required file group drifted: {path.name}")
    if mode is not None and stat.S_IMODE(meta.st_mode) != mode:
        _fail(f"required file mode drifted: {path.name}")
    return meta


def _read_replay_row(accepted: AcceptedAuthorization) -> sqlite3.Row | None:
    _require_regular(STATE_DB_PATH, uid=ROOT_UID, gid=ROOT_GID, mode=0o600)
    try:
        conn = sqlite3.connect(f"file:{STATE_DB_PATH}?mode=ro", uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            _fail("Weather replay database quick_check failed")
        if conn.execute("PRAGMA application_id").fetchone()[0] != STATE_DB_APPLICATION_ID:
            _fail("Weather replay database application_id drifted")
        if conn.execute("PRAGMA user_version").fetchone()[0] != STATE_DB_SCHEMA_VERSION:
            _fail("Weather replay database schema version drifted")
        columns = tuple((row["name"], row["type"], row["notnull"], row["pk"]) for row in conn.execute("PRAGMA table_info(requests)"))
        if columns != EXPECTED_COLUMNS:
            _fail("Weather replay database columns drifted")
        rows = conn.execute(
            "SELECT repository_id, issue_id, request_id, canonical_payload_sha256, raw_body_sha256, state, consumed_at FROM requests WHERE (repository_id=? AND issue_id=?) OR request_id=?",
            (accepted.repository_id, accepted.issue_id, accepted.request_id),
        ).fetchall()
        if len(rows) > 1:
            _fail("Weather replay database returned ambiguous identity")
        return rows[0] if rows else None
    except sqlite3.DatabaseError as exc:
        raise RuntimeError("Weather replay database read failed closed") from exc
    finally:
        if "conn" in locals():
            conn.close()


class ConcreteWeatherReplayAuthority:
    """Read-only availability plus exactly one durable SQLite consume boundary."""

    def __init__(self):
        self._accepted: AcceptedAuthorization | None = None
        self._availability_checks = 0
        self._consume_attempted = False

    def is_available(self, accepted: AcceptedAuthorization) -> bool:
        if type(accepted) is not AcceptedAuthorization or self._consume_attempted:
            return False
        if self._accepted is not None and self._accepted != accepted:
            _fail("Weather replay authority changed between JIT checks")
        if _read_replay_row(accepted) is not None:
            return False
        self._accepted = accepted
        self._availability_checks += 1
        return True

    def consume(self, request_id: str) -> WeatherReplayConsumptionReceipt:
        if self._consume_attempted:
            _fail("Weather replay consume boundary already entered")
        accepted = self._accepted
        if accepted is None or request_id != accepted.request_id or self._availability_checks < 2:
            _fail("Weather replay consume lacks double canonical availability")
        self._consume_attempted = True
        store: StateStore | None = None
        try:
            store = StateStore(STATE_DB_PATH)
            store.discover(
                repository_id=accepted.repository_id,
                issue_id=accepted.issue_id,
                request_id=accepted.request_id,
                canonical_payload_sha256=accepted.canonical_payload_sha256,
                raw_body_sha256=accepted.raw_body_sha256,
            )
            store.transition(request_id, "VALIDATING")
            store.transition(request_id, "ACCEPTED")
            row = store.consume(request_id)
        except Exception as exc:
            raise RuntimeError("Weather durable replay consume failed closed after attempt boundary") from exc
        finally:
            if store is not None:
                store.close()
        if row.state != "CONSUMED":
            _fail("Weather durable replay did not reach CONSUMED")
        return WeatherReplayConsumptionReceipt(
            request_id=request_id,
            state=row.state,
            availability_checks=self._availability_checks,
            durable_replay_consumed=True,
            replay_mutation_started=True,
        )

    def is_consumed(self, accepted: AcceptedAuthorization) -> bool:
        if type(accepted) is not AcceptedAuthorization or not self._consume_attempted:
            return False
        if self._accepted != accepted:
            return False
        row = _read_replay_row(accepted)
        return bool(
            row is not None
            and row["repository_id"] == AUTHORIZATION_REPOSITORY_ID
            and row["issue_id"] == accepted.issue_id
            and row["request_id"] == accepted.request_id
            and row["canonical_payload_sha256"] == accepted.canonical_payload_sha256
            and row["raw_body_sha256"] == accepted.raw_body_sha256
            and row["state"] == "CONSUMED"
            and row["consumed_at"] is not None
        )


class ConcreteSanitizedWeatherBaselineProvider:
    """Collect only public-safe first-rollout runtime state using fixed identities."""

    def __init__(self, runner: FixedCommandRunner = run_fixed_command):
        self._runner = runner

    def _run(self, argv: Sequence[str], where: str, *, allowed: tuple[int, ...] = (0,)) -> CommandResult:
        result = self._runner(tuple(argv), env=FIXED_COMMAND_ENV)
        if type(result) is not CommandResult or result.returncode not in allowed:
            _fail(f"Weather baseline {where} failed closed")
        return result

    def resolve(self, *, source_sha: str, target_alias: str) -> Mapping[str, Any]:
        if target_alias != TARGET_ALIAS or type(source_sha) is not str or _SHA40_RE.fullmatch(source_sha) is None:
            _fail("Weather baseline identity drifted")
        release = Path(RELEASE_ROOT) / source_sha
        compose = release / COMPOSE_RELATIVE
        project = self._run(
            ("/usr/bin/docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={COMPOSE_PROJECT}", "--format", "{{.ID}}"),
            "project discovery",
        ).stdout.strip().splitlines()
        project_ids = tuple(item.strip() for item in project if item.strip())
        if len(set(project_ids)) != len(project_ids):
            _fail("Weather baseline project identity is ambiguous")

        volume_out = self._run(
            ("/usr/bin/docker", "volume", "ls", "--filter", f"name=^{HOST_VOLUME}$", "--format", "{{.Name}}"),
            "volume discovery",
        ).stdout.strip()
        if volume_out not in {"", HOST_VOLUME}:
            _fail("Weather baseline volume identity is ambiguous")
        volume_state = "present" if volume_out == HOST_VOLUME else "absent"

        if project_ids:
            _require_regular(compose)
            head = self._run(
                ("/usr/bin/git", "--no-optional-locks", "-C", str(release), "rev-parse", "HEAD"),
                "release HEAD",
            ).stdout.strip()
            clean = self._run(
                ("/usr/bin/git", "--no-optional-locks", "-C", str(release), "status", "--porcelain=v1", "--untracked-files=all"),
                "release cleanliness",
            ).stdout
            if head != source_sha or clean:
                _fail("Weather deployed release provenance drifted")
            exact_ids = self._run(
                ("/usr/bin/docker", "compose", "-p", COMPOSE_PROJECT, "-f", str(compose), "ps", "-aq", "weather"),
                "exact service discovery",
            ).stdout.strip().splitlines()
            exact = tuple(item.strip() for item in exact_ids if item.strip())
            if len(exact) != 1 or exact[0] not in set(project_ids):
                _fail("Weather baseline project is not bound to one exact weather service")
            container_image = self._run(
                ("/usr/bin/docker", "inspect", "--format", "{{.Image}}", exact[0]),
                "container image identity",
            ).stdout.strip()
            compose_image = self._run(
                ("/usr/bin/docker", "compose", "-p", COMPOSE_PROJECT, "-f", str(compose), "images", "-q", "weather"),
                "compose image identity",
            ).stdout.strip()
            if not container_image or container_image != compose_image:
                _fail("Weather running image is not the exact release image")
            deployment_state = "deployed"
            current_source_sha: str | None = source_sha
        else:
            deployment_state = "not_deployed"
            current_source_sha = None

        schema_state = "absent"
        schema_version: int | None = None
        if deployment_state == "deployed":
            readiness = self._run(
                ("/usr/bin/docker", "compose", "-p", COMPOSE_PROJECT, "-f", str(compose), "exec", "-T", "weather", "rozkalns-weather", "readiness"),
                "readiness",
                allowed=(0, 1),
            )
            try:
                payload = json.loads(readiness.stdout)
            except (json.JSONDecodeError, TypeError) as exc:
                raise RuntimeError("Weather baseline readiness JSON is invalid") from exc
            privacy = payload.get("privacy") if type(payload) is dict else None
            database = payload.get("database") if type(payload) is dict else None
            if type(privacy) is not dict or any(privacy.get(key) is not False for key in ("coordinates_exposed", "credentials_exposed", "database_path_exposed")):
                _fail("Weather baseline readiness privacy contract drifted")
            if type(database) is not dict:
                _fail("Weather baseline readiness database state is missing")
            if database.get("state") == "ready" and payload.get("schema_version") == 1:
                schema_state, schema_version = "ready", 1
            elif database.get("state") == "missing":
                schema_state = "absent"
            else:
                schema_state = "unknown"

        if SYSTEMD_TIMER_PATH.exists():
            _require_regular(SYSTEMD_TIMER_PATH, uid=ROOT_UID, gid=ROOT_GID, mode=0o644)
            enabled = self._run(("/usr/bin/systemctl", "is-enabled", TIMER_NAME), "timer state", allowed=(0, 1, 3, 4))
            schedule_state = "enabled" if enabled.returncode == 0 and enabled.stdout.strip() == "enabled" else "installed"
        else:
            schedule_state = "absent"

        if deployment_state == "not_deployed":
            stage_state = "not_started"
        elif schema_state != "ready":
            stage_state = "application_ready"
        elif schedule_state == "enabled":
            stage_state = "recurring_ingest_enabled"
        else:
            stage_state = "schema_ready"
        return {
            "schema": BASELINE_EVIDENCE_SCHEMA,
            "target_alias": TARGET_ALIAS,
            "deployment_state": deployment_state,
            "current_source_sha": current_source_sha,
            "persistent_volume_state": volume_state,
            "schema_state": schema_state,
            "schema_version": schema_version,
            "public_ingest_schedule_state": schedule_state,
            "bootstrap_stage_state": stage_state,
            "privacy_safe": True,
        }


def _owner_paths() -> tuple[pwd.struct_passwd, Path, Path]:
    try:
        account = pwd.getpwnam(FIXED_OWNER_ACCOUNT)
    except KeyError as exc:
        raise RuntimeError("fixed RPi5 owner account is absent") from exc
    home = Path(account.pw_dir)
    manager = home / MANAGER_CHECKOUT_NAME
    trusted = home / TRUSTED_CHECKOUT_NAME
    return account, manager, trusted


def _fixed_git(runner: FixedCommandRunner, manager: Path, account: pwd.struct_passwd, *args: str) -> CommandResult:
    env = {**FIXED_COMMAND_ENV, "HOME": account.pw_dir, "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"}
    return runner(("/usr/bin/git", *args), env=env, user=account.pw_uid, group=account.pw_gid)


def _rename_noreplace(parent_fd: int, old_name: str, new_name: str) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        _fail("renameat2 is required for Weather atomic publication")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(parent_fd, old_name.encode(), parent_fd, new_name.encode(), RENAME_NOREPLACE) != 0:
        err = ctypes.get_errno()
        raise RuntimeError(f"Weather atomic publication failed closed: errno={err}")


def _safe_root_parent(path: Path) -> int:
    parent = path.parent
    meta = parent.lstat()
    if not stat.S_ISDIR(meta.st_mode) or stat.S_ISLNK(meta.st_mode) or meta.st_uid != ROOT_UID or meta.st_gid != ROOT_GID or stat.S_IMODE(meta.st_mode) & 0o022:
        _fail("Weather mutation parent is unsafe")
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    return os.open(parent, flags)


class ConcreteWeatherOperatorHostMutator:
    """Fixed first-rollout mutations. No path/argv/environment selector is exposed."""

    def __init__(self, runner: FixedCommandRunner = run_fixed_command):
        self._runner = runner
        self._fetch_done = False
        self._worktree_done = False
        self._helper_done = False
        self._activation_done = False

    def _manager_preflight(self, expected_sha: str) -> tuple[pwd.struct_passwd, Path, Path]:
        if type(expected_sha) is not str or _SHA40_RE.fullmatch(expected_sha) is None:
            _fail("Weather expected RPi5_main SHA is invalid")
        account, manager, trusted = _owner_paths()
        if trusted.exists() or trusted.is_symlink():
            _fail("Weather trusted checkout target must be absent")
        top = _require_success(_fixed_git(self._runner, manager, account, "-C", str(manager), "rev-parse", "--show-toplevel"), "manager root").strip()
        if top != str(manager):
            _fail("Weather manager checkout root drifted")
        origin = _require_success(_fixed_git(self._runner, manager, account, "-C", str(manager), "remote", "get-url", "origin"), "manager origin").strip()
        if origin != RPi5_ORIGIN:
            _fail("Weather manager origin drifted")
        return account, manager, trusted

    def trusted_checkout_fetch(self, expected_sha: str) -> WeatherOperatorMutationReceipt:
        if self._fetch_done:
            _fail("Weather trusted-checkout fetch budget already consumed")
        account, manager, _trusted = self._manager_preflight(expected_sha)
        self._fetch_done = True
        _require_success(_fixed_git(self._runner, manager, account, "-C", str(manager), "fetch", "origin", "main"), "trusted checkout fetch")
        origin_main = _require_success(_fixed_git(self._runner, manager, account, "-C", str(manager), "rev-parse", "refs/remotes/origin/main"), "origin/main proof").strip()
        if origin_main != expected_sha:
            _fail("fresh origin/main differs from authorized RPi5_main SHA")
        ancestor = _fixed_git(self._runner, manager, account, "-C", str(manager), "merge-base", "--is-ancestor", RPI5_MIN_REVIEWED_ANCESTOR, expected_sha)
        if ancestor.returncode != 0:
            _fail("authorized RPi5_main SHA does not descend from reviewed minimum")
        return WeatherOperatorMutationReceipt("trusted_checkout_fetch", (("git.trusted-checkout-fetch", 1),), True)

    def trusted_checkout_worktree_add(self, expected_sha: str) -> WeatherOperatorMutationReceipt:
        if not self._fetch_done or self._worktree_done:
            _fail("Weather trusted-checkout worktree gate order drifted")
        account, manager, trusted = self._manager_preflight(expected_sha)
        origin_main = _require_success(_fixed_git(self._runner, manager, account, "-C", str(manager), "rev-parse", "refs/remotes/origin/main"), "origin/main recheck").strip()
        if origin_main != expected_sha:
            _fail("origin/main drifted before worktree creation")
        self._worktree_done = True
        _require_success(_fixed_git(self._runner, manager, account, "-C", str(manager), "worktree", "add", "--detach", str(trusted), expected_sha), "trusted checkout worktree add")
        head = _require_success(_fixed_git(self._runner, trusted, account, "-C", str(trusted), "rev-parse", "HEAD"), "trusted checkout HEAD").strip()
        status_out = _require_success(_fixed_git(self._runner, trusted, account, "-C", str(trusted), "status", "--porcelain=v1", "--untracked-files=all"), "trusted checkout status")
        symbolic = _fixed_git(self._runner, trusted, account, "-C", str(trusted), "symbolic-ref", "-q", "HEAD")
        origin = _require_success(_fixed_git(self._runner, trusted, account, "-C", str(trusted), "remote", "get-url", "origin"), "trusted checkout origin").strip()
        if head != expected_sha or status_out or symbolic.returncode != 1 or origin != RPI5_ORIGIN:
            _fail("trusted checkout postcondition failed")
        return WeatherOperatorMutationReceipt("trusted_checkout_worktree_add", (("git.trusted-checkout-worktree-add", 1),), True)

    def _manifest(self, trusted: Path) -> dict[str, Any]:
        manifest_path = trusted / HELPER_MANIFEST_RELATIVE
        _require_regular(manifest_path)
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Weather helper manifest is invalid") from exc
        if value.get("contract") != "rozkalns-weather.public-runtime-helper-install.v1" or value.get("artifact_count") != 13:
            _fail("Weather helper manifest identity drifted")
        artifacts = value.get("artifacts")
        if type(artifacts) is not list or len(artifacts) != 13:
            _fail("Weather helper manifest closure drifted")
        try:
            observed = tuple(
                (item["source"], item["destination"], int(item["mode"], 8))
                for item in artifacts
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Weather helper manifest artifact encoding drifted") from exc
        if observed != expected_install_artifacts():
            _fail("Weather helper manifest differs from canonical privileged-install allowlist")
        return value

    def install_helper(self, expected_sha: str) -> WeatherOperatorMutationReceipt:
        if not self._worktree_done or self._helper_done:
            _fail("Weather helper install gate order drifted")
        account, _manager, trusted = _owner_paths()
        manifest = self._manifest(trusted)
        head = _require_success(_fixed_git(self._runner, trusted, account, "-C", str(trusted), "rev-parse", "HEAD"), "trusted helper source HEAD").strip()
        clean = _require_success(_fixed_git(self._runner, trusted, account, "-C", str(trusted), "status", "--porcelain=v1", "--untracked-files=all"), "trusted helper source status")
        if head != expected_sha or clean:
            _fail("trusted helper source drifted")
        if HELPER_SUPPORT_ROOT.exists() or HELPER_SUPPORT_ROOT.is_symlink() or HELPER_EXECUTABLE.exists() or HELPER_EXECUTABLE.is_symlink():
            _fail("Weather helper install targets must be absent")
        parent_fd = _safe_root_parent(HELPER_SUPPORT_ROOT)
        stage_dir = ".rozkalns-weather-public-runtime.install"
        entry_temp = ".rozkalns-weather-public-runtime-stage-helper.install"
        try:
            for name in (stage_dir, entry_temp, HELPER_SUPPORT_ROOT.name, HELPER_EXECUTABLE.name):
                try:
                    os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                _fail("Weather helper install namespace is not pristine")
            self._helper_done = True
            os.mkdir(stage_dir, 0o700, dir_fd=parent_fd)
            stage_root = HELPER_SUPPORT_ROOT.parent / stage_dir
            entry_bytes: bytes | None = None
            for artifact in manifest["artifacts"]:
                if type(artifact) is not dict or set(artifact) != {"source", "destination", "kind", "mode"}:
                    _fail("Weather helper artifact manifest entry drifted")
                source_relative = _safe_relative(artifact["source"], "Weather helper source")
                source = trusted / source_relative
                destination_value = artifact["destination"]
                if type(destination_value) is not str or not destination_value.startswith("/") or "\x00" in destination_value:
                    _fail("Weather helper destination path is invalid")
                destination = Path(destination_value)
                source_meta = _require_regular(source)
                if source_meta.st_uid != account.pw_uid:
                    _fail("Weather helper source owner drifted")
                raw = source.read_bytes()
                mode = int(artifact["mode"], 8)
                if destination == HELPER_EXECUTABLE:
                    entry_bytes = raw
                    entry_mode = mode
                    continue
                try:
                    relative = destination.relative_to(HELPER_SUPPORT_ROOT)
                except ValueError:
                    _fail("Weather helper destination escaped support root")
                if not relative.parts or ".." in relative.parts:
                    _fail("Weather helper destination traversal is forbidden")
                target = stage_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                os.chown(target.parent, ROOT_UID, ROOT_GID)
                os.chmod(target.parent, 0o755)
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0), mode)
                try:
                    _write_all(fd, raw)
                    os.fchown(fd, ROOT_UID, ROOT_GID)
                    os.fchmod(fd, mode)
                    os.fsync(fd)
                finally:
                    os.close(fd)
            if entry_bytes is None:
                _fail("Weather helper entrypoint is missing from manifest")
            os.chown(stage_root, ROOT_UID, ROOT_GID)
            os.chmod(stage_root, 0o755)
            entry_fd = os.open(entry_temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=parent_fd)
            try:
                _write_all(entry_fd, entry_bytes)
                os.fchown(entry_fd, ROOT_UID, ROOT_GID)
                os.fchmod(entry_fd, entry_mode)
                os.fsync(entry_fd)
            finally:
                os.close(entry_fd)
            _rename_noreplace(parent_fd, stage_dir, HELPER_SUPPORT_ROOT.name)
            os.fsync(parent_fd)
            _rename_noreplace(parent_fd, entry_temp, HELPER_EXECUTABLE.name)
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        _require_regular(HELPER_EXECUTABLE, uid=ROOT_UID, gid=ROOT_GID, mode=0o755)
        final_manifest = self._manifest(trusted)
        for artifact in final_manifest["artifacts"]:
            destination = Path(artifact["destination"])
            _require_regular(destination, uid=ROOT_UID, gid=ROOT_GID, mode=int(artifact["mode"], 8))
        return WeatherOperatorMutationReceipt("helper_install", (("filesystem.weather-helper-install-transaction", 1),), True)

    def publish_activation(self, plan: WeatherExecutablePlan) -> WeatherOperatorMutationReceipt:
        if not self._helper_done or self._activation_done:
            _fail("Weather activation gate order drifted")
        if plan.activation_schema != ACTIVATION_SCHEMA or Path(plan.activation_file) != ACTIVATION_PATH:
            _fail("Weather activation plan identity drifted")
        parent = ACTIVATION_PATH.parent
        if not parent.exists():
            parent.parent.mkdir(parents=True, exist_ok=True)
            os.mkdir(parent, 0o700)
            os.chown(parent, ROOT_UID, ROOT_GID)
        parent_meta = parent.lstat()
        if not stat.S_ISDIR(parent_meta.st_mode) or stat.S_ISLNK(parent_meta.st_mode) or parent_meta.st_uid != ROOT_UID or parent_meta.st_gid != ROOT_GID or stat.S_IMODE(parent_meta.st_mode) & 0o022:
            _fail("Weather activation directory is unsafe")
        if ACTIVATION_PATH.exists() or ACTIVATION_PATH.is_symlink():
            _fail("Weather activation target must be absent for first rollout")
        value = {
            "schema": ACTIVATION_SCHEMA,
            "enabled": True,
            "target_alias": TARGET_ALIAS,
            "operation_id": OPERATION_ID,
            "source_sha": plan.source_sha,
            "preactivation_sha256": plan.preactivation_sha256,
            "start_date": plan.start_date,
            "end_date": plan.end_date,
            "recovery_decision": plan.recovery_decision,
            "allowed_helper_ids": [stage.helper_id for stage in plan.stages],
        }
        raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        parent_fd = _safe_root_parent(ACTIVATION_PATH)
        temp = ".public-runtime-helper-activation.json.install"
        try:
            for name in (temp, ACTIVATION_PATH.name):
                try:
                    os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                _fail("Weather activation namespace is not pristine")
            self._activation_done = True
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=parent_fd)
            try:
                _write_all(fd, raw)
                os.fchown(fd, ROOT_UID, ROOT_GID)
                os.fchmod(fd, 0o600)
                os.fsync(fd)
            finally:
                os.close(fd)
            _rename_noreplace(parent_fd, temp, ACTIVATION_PATH.name)
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        _require_regular(ACTIVATION_PATH, uid=ROOT_UID, gid=ROOT_GID, mode=0o600)
        return WeatherOperatorMutationReceipt("activation_publish", (("filesystem.weather-helper-activation-publish", 1),), True)


_AUTHORITY_FIELDS = (
    "authorization_issue_number", "authorization_issue_id", "request_id",
    "authorization_payload_sha256", "authorization_raw_body_sha256", "composite_authorization_sha256",
    "queue_issue_number", "queue_contract_sha256", "source_sha", "weather_current_main_sha", "weather_ci_run_id",
    "rpi5_main_sha", "rpi5_main_ci_run_id", "host_alias", "target_alias", "expected_bootstrap_baseline_token",
    "start_date", "end_date", "recovery_decision", "release_mutation_budget", "additional_mutation_budget", "full_mutation_budget",
)


def _require_same_authority(initial: WeatherCompositeAuthorityEvidence, current: WeatherCompositeAuthorityEvidence) -> None:
    if any(getattr(initial, field) != getattr(current, field) for field in _AUTHORITY_FIELDS):
        _fail("Weather Composite canonical authority drifted after durable consume")
    if current.authorization_replay_consumed is not True or current.authorization_replay_available is not False:
        _fail("Weather Composite post-consume replay state is invalid")


def _baseline_for_gate(provider: ConcreteSanitizedWeatherBaselineProvider, authority: WeatherCompositeAuthorityEvidence, gate: str) -> Mapping[str, Any]:
    raw = provider.resolve(source_sha=authority.source_sha, target_alias=authority.target_alias)
    baseline = parse_weather_bootstrap_baseline(raw)
    if gate in COMPOSITE_GATE_ORDER[:6]:
        if baseline.canonical_token != authority.expected_bootstrap_baseline_token:
            _fail("Weather initial bootstrap baseline drifted before first deployment apply")
        return raw
    if baseline.deployment_state != "deployed" or baseline.current_source_sha != authority.source_sha or baseline.persistent_volume_state != "present":
        _fail("Weather deployed baseline identity drifted")
    if gate == "explicit_schema_init":
        if baseline.schema_state != "absent" or baseline.public_ingest_schedule_state != "absent":
            _fail("Weather pre-schema baseline drifted")
    elif gate == "recurring_public_ingest_schedule":
        if baseline.schema_state != "ready" or baseline.schema_version != 1 or baseline.public_ingest_schedule_state != "absent":
            _fail("Weather pre-schedule baseline drifted")
    else:
        if baseline.schema_state != "ready" or baseline.schema_version != 1 or baseline.public_ingest_schedule_state != "absent":
            _fail("Weather post-schema baseline drifted")
    return raw


def _build_preactivation(authority: WeatherCompositeAuthorityEvidence) -> WeatherPreactivationEnvelope:
    stages = tuple(
        WeatherPreactivationStageBinding(binding.stage_id, binding.capability_id, binding.mutation_class, binding.max_operations, binding.read_only)
        for binding in expected_helper_bindings()
    )
    return WeatherPreactivationEnvelope(
        schema=ENVELOPE_SCHEMA,
        result=PREACTIVATION_RESULT,
        authorization_issue_number=authority.authorization_issue_number,
        authorization_issue_id=authority.authorization_issue_id,
        request_id=authority.request_id,
        authorization_payload_sha256=authority.authorization_payload_sha256,
        authorization_raw_body_sha256=authority.authorization_raw_body_sha256,
        queue_repository=QUEUE_REPOSITORY,
        queue_issue_number=authority.queue_issue_number,
        queue_contract_sha256=authority.queue_contract_sha256,
        source_repository=SOURCE_REPOSITORY,
        source_sha=authority.source_sha,
        target_alias=TARGET_ALIAS,
        release_operation_id=OPERATION_ID,
        release_baseline_resolver_id=BASELINE_RESOLVER_ID,
        bootstrap_baseline_token=authority.expected_bootstrap_baseline_token,
        start_date=authority.start_date,
        end_date=authority.end_date,
        recovery_decision=authority.recovery_decision,
        truth_station_id=TRUTH_STATION_ID,
        forecast_models=FORECAST_MODELS,
        run_hours=RUN_HOURS,
        stages=stages,
    )


_STAGE_MUTATIONS: dict[str, tuple[tuple[str, int], ...]] = {
    "application_release": (("filesystem.release-materialization", 1), ("docker.compose-build", 1)),
    "persistent_volume_ensure": (("docker.named-volume-ensure", 1), ("docker.compose-application-apply", 1)),
    "explicit_schema_init": (("sqlite.schema-init", 1),),
    "bounded_dwd_truth_backfill": (("sqlite.corpus-truth-backfill", 1),),
    "bounded_deterministic_forecast_backfill": (("sqlite.corpus-forecast-backfill", len(FORECAST_MODELS)),),
    "recurring_public_ingest_schedule": (("systemd.public-ingest-schedule-install-or-update", 1),),
}
_READ_ONLY_LIMITS = {"readiness_schema_privacy": 1, "public_smoke_read_only": 1, "corpus_integrity_check": len(FORECAST_MODELS)}


class WeatherCompositeOperator:
    def __init__(
        self,
        *,
        revalidator: ConcreteCanonicalWeatherCompositeRevalidator,
        replay_authority: ConcreteWeatherReplayAuthority,
        baseline_provider: ConcreteSanitizedWeatherBaselineProvider,
        host_mutator: WeatherOperatorHostMutator,
        launcher: WeatherOneShotStageLauncher,
    ):
        self._revalidator = revalidator
        self._replay = replay_authority
        self._baseline = baseline_provider
        self._host = host_mutator
        self._launcher = launcher

    def execute(self, authorization_issue_number: int) -> WeatherCompositeOperatorReceipt:
        if type(authorization_issue_number) is not int or not 1 <= authorization_issue_number <= 2_147_483_647:
            raise WeatherCompositeOperatorError("request_validation")
        consumed = False
        host_started = False
        production_started = False
        active_stage = "pre_consume"
        completed: list[str] = []
        counts = {category: 0 for category, _limit in FULL_MUTATION_BUDGET}
        read_only = {name: 0 for name in _READ_ONLY_LIMITS}
        try:
            authority = self._revalidator.revalidate_composite(authorization_issue_number)
            if authority.host_alias != HOST_ALIAS or authority.target_alias != TARGET_ALIAS:
                _fail("Weather operator host/target drifted")
            _baseline_for_gate(self._baseline, authority, "trusted_checkout_fetch")
            envelope = _build_preactivation(authority)
            host_plan = build_weather_host_wiring_plan(envelope)
            executable = build_weather_executable_plan(host_plan, envelope)

            # First mutation boundary: durable replay consume. From the instant this
            # call is attempted the authorization is non-reusable, even if SQLite
            # fails before a CONSUMED receipt can be returned.
            active_stage = "durable_replay_consume"
            consumed = True
            replay = self._replay.consume(authority.request_id)
            if not replay.durable_replay_consumed or replay.state != "CONSUMED" or replay.request_id != authority.request_id:
                _fail("Weather durable replay consume receipt drifted")

            def jit(gate: str) -> None:
                current = self._revalidator.revalidate_consumed_composite(authorization_issue_number)
                _require_same_authority(authority, current)
                _baseline_for_gate(self._baseline, authority, gate)

            def add_mutations(rows: tuple[tuple[str, int], ...]) -> None:
                nonlocal host_started
                for category, operations in rows:
                    if category not in counts or type(operations) is not int or operations < 0:
                        _fail("Weather operator mutation category drifted")
                    counts[category] += operations
                    maximum = dict(FULL_MUTATION_BUDGET)[category]
                    if counts[category] > maximum:
                        _fail("Weather operator mutation budget exceeded")
                    if operations:
                        host_started = True

            active_stage = "trusted_checkout_fetch"
            jit("trusted_checkout_fetch")
            host_started = True
            receipt = self._host.trusted_checkout_fetch(authority.rpi5_main_sha)
            add_mutations(receipt.mutation_categories)
            completed.append("trusted_checkout_fetch")

            active_stage = "trusted_checkout_worktree_add"
            jit("trusted_checkout_worktree_add")
            host_started = True
            receipt = self._host.trusted_checkout_worktree_add(authority.rpi5_main_sha)
            add_mutations(receipt.mutation_categories)
            completed.append("trusted_checkout_worktree_add")

            active_stage = "helper_install"
            jit("helper_install")
            host_started = True
            receipt = self._host.install_helper(authority.rpi5_main_sha)
            add_mutations(receipt.mutation_categories)
            completed.append("helper_install")

            active_stage = "activation_publish"
            jit("activation_publish")
            host_started = True
            receipt = self._host.publish_activation(executable)
            add_mutations(receipt.mutation_categories)
            completed.append("activation_publish")

            for stage in executable.stages:
                active_stage = stage.stage_id
                jit(stage.stage_id)
                if not stage.read_only:
                    host_started = True
                    production_started = True
                launch = self._launcher.launch_stage(executable, host_plan, envelope, stage.stage_id)
                if type(launch) is not WeatherHelperLaunchReceipt or not launch.output_validated:
                    _fail("Weather helper launch receipt is invalid")
                if stage.read_only:
                    read_only[stage.stage_id] += max(1, launch.operations_performed)
                    if read_only[stage.stage_id] > _READ_ONLY_LIMITS[stage.stage_id]:
                        _fail("Weather read-only invocation budget exceeded")
                else:
                    expected_rows = _STAGE_MUTATIONS.get(stage.stage_id)
                    if expected_rows is None:
                        _fail("Weather mutation stage has no fixed budget mapping")
                    if launch.operations_performed != stage.max_operations:
                        _fail("Weather first-rollout mutation stage did not consume its exact fixed operation count")
                    add_mutations(expected_rows)
                completed.append(stage.stage_id)

            active_stage = "final_verification"
            final = self._revalidator.revalidate_consumed_composite(authorization_issue_number)
            _require_same_authority(authority, final)
            final_baseline = parse_weather_bootstrap_baseline(self._baseline.resolve(source_sha=authority.source_sha, target_alias=authority.target_alias))
            if (
                final_baseline.deployment_state != "deployed"
                or final_baseline.current_source_sha != authority.source_sha
                or final_baseline.persistent_volume_state != "present"
                or final_baseline.schema_state != "ready"
                or final_baseline.schema_version != 1
                or final_baseline.public_ingest_schedule_state != "enabled"
            ):
                _fail("Weather final runtime baseline failed closed")
            if tuple(completed) != COMPOSITE_GATE_ORDER:
                _fail("Weather operator gate order drifted")
            return WeatherCompositeOperatorReceipt(
                schema=OPERATOR_SCHEMA,
                result=OPERATOR_RESULT,
                authorization_issue_number=authorization_issue_number,
                request_id=authority.request_id,
                source_sha=authority.source_sha,
                rpi5_main_sha=authority.rpi5_main_sha,
                target_alias=TARGET_ALIAS,
                completed_gates=tuple(completed),
                mutation_counts=tuple((category, counts[category]) for category, _limit in FULL_MUTATION_BUDGET),
                read_only_invocations=tuple((name, read_only[name]) for name in _READ_ONLY_LIMITS),
                durable_replay_consumed=True,
                authorization_reuse_forbidden=True,
                host_mutation_started=host_started,
                production_mutation_started=production_started,
            )
        except WeatherCompositeOperatorError:
            raise
        except Exception:
            raise WeatherCompositeOperatorError(
                active_stage,
                authorization_reuse_forbidden=consumed,
                host_mutation_started=host_started,
                production_mutation_started=production_started,
            ) from None


def build_runtime_operator() -> WeatherCompositeOperator:
    if os.geteuid() != ROOT_UID:
        raise WeatherCompositeOperatorError("runtime_requires_root")
    auth_surface = load_contract(AUTH_SURFACE_PATH)
    require_isolated_auth_surface(auth_surface)
    registry = load_registry(OPERATOR_REGISTRY_PATH)
    if registry.execution_enabled or len(registry.operations) != 1 or registry.operations[0].operation_id != OPERATION_ID:
        raise WeatherCompositeOperatorError("operator_registry")
    replay = ConcreteWeatherReplayAuthority()
    clients = build_p9_read_clients(auth_surface=auth_surface, private_key=EXECUTOR_KEY_PATH)
    revalidator = ConcreteCanonicalWeatherCompositeRevalidator(
        authorization_client=clients.authorization,
        queue_client=clients.queue,
        source_client=FixedPublicGitHubReadClient(),
        auth_surface=auth_surface,
        registry=registry,
        replay_availability=replay,
    )
    return WeatherCompositeOperator(
        revalidator=revalidator,
        replay_authority=replay,
        baseline_provider=ConcreteSanitizedWeatherBaselineProvider(),
        host_mutator=ConcreteWeatherOperatorHostMutator(),
        launcher=WeatherOneShotStageLauncher(),
    )


def source_readiness() -> Mapping[str, Any]:
    return {
        "schema": OPERATOR_SCHEMA,
        "status": OPERATOR_STATUS,
        "caller_authority": CALLER_AUTHORITY,
        "fixed_host_alias": HOST_ALIAS,
        "fixed_target_alias": TARGET_ALIAS,
        "gate_order": COMPOSITE_GATE_ORDER,
        "first_mutation": "durable_replay_consume",
        "post_consume_revalidation": True,
        "jit_before_each_privileged_boundary": True,
        "trusted_checkout_mutations_implemented": True,
        "helper_install_transaction_implemented": True,
        "activation_publication_implemented": True,
        "fixed_helper_launcher_wired": True,
        "distinct_mutation_budget_enforced": True,
        "sanitized_stage_baseline_revalidation": True,
        "host_installed": False,
        "runtime_live_authority": False,
        "production_mutation_started": False,
        "generic_shell_authority": False,
        "caller_supplied_path": False,
        "caller_supplied_argv": False,
        "caller_supplied_environment": False,
        "caller_supplied_repository_url": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }
