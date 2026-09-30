from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
sys.dont_write_bytecode = True
from typing import Any, Callable, Mapping

REQUEST_SCHEMA = "rozkalns.rpi5-main.weather-v9-predecessor-bootstrap-request.v1"
RECEIPT_SCHEMA = "rozkalns.rpi5-main.weather-v9-predecessor-bootstrap-broker-receipt.v1"
FAILURE_SCHEMA = "rozkalns.rpi5-main.weather-v9-predecessor-bootstrap-broker-failure.v1"
REGISTRATION_SCHEMA = "rozkalns.rpi5-main.weather-v9-predecessor-bootstrap-capability-registration.v1"
AUTH_SCHEMA = "rozkalns.rpi5-main.weather-v9-predecessor-bootstrap-live-auth.v1"
AUTH_START = "<!-- rozkalns-weather-v9-predecessor-bootstrap-live-auth:v1 -->"
AUTH_END = "<!-- /rozkalns-weather-v9-predecessor-bootstrap-live-auth:v1 -->"
AUTH_TITLE = "[LIVE-AUTH][PENDING] rpi5-weather-v9-predecessor-bootstrap"
AUTH_TTL_SECONDS = 600
MAX_GITHUB_SPREAD_SECONDS = 30
OWNER_NUMERIC_ID = 277435981
REPOSITORY = "rozkalnsandris/RPi5_main"
REVIEWED_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
PREDECESSOR_SHA = "80261255b3be2aa7dd40986254d4ea478b4e2e1b"
TARGET_ALIAS = "weather-v9-predecessor-state-bootstrap"
APPLY_OPERATION = "weather-v9.predecessor-state-bootstrap.apply.v1"
PREFLIGHT = "preflight"
APPLY = "apply"
REQUEST_MAX_BYTES = 256
MAX_RECEIPT_BYTES = 65536
ROOT_UID = 0
ROOT_GID = 0
RELEASE_ROOT = Path("/usr/local/libexec/rozkalns-weather-v9-predecessor-bootstrap/current")
CAPABILITY_ROOT = RELEASE_ROOT.parent
REGISTRATION_PATH = Path("/etc/rozkalns-weather-v9-predecessor-bootstrap/registration.json")
REPLAY_ROOT = Path("/var/lib/rozkalns-weather-v9-predecessor-bootstrap")
REPLAY_PATH = REPLAY_ROOT / "consumed.json"
SOCKET_UNIT_PATH = Path("/etc/systemd/system/rozkalns-weather-v9-predecessor-bootstrap.socket")
SERVICE_UNIT_PATH = Path("/etc/systemd/system/rozkalns-weather-v9-predecessor-bootstrap@.service")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

RELEASE_FILES: Mapping[str, int] = {
    "ops/bin/rozkalns-weather-v9-predecessor-bootstrap-broker": 0o755,
    "ops/lib/deploy_executor/__init__.py": 0o644,
    "ops/lib/deploy_executor/state.py": 0o644,
    "ops/lib/deploy_executor/weather_v9_predecessor_bootstrap_privileged.py": 0o644,
    "ops/recovery/weather_v9_capability_state_bootstrap.py": 0o644,
    "ops/recovery/weather_v9_capability_state_bootstrap.contract.json": 0o644,
    "ops/recovery/weather_v9_predecessor_state_bootstrap.py": 0o644,
    "ops/recovery/weather_v9_predecessor_state_bootstrap.contract.json": 0o644,
    "scripts/install-weather-operator-v9-host-capability.py": 0o755,
}

class BootstrapPrivilegedError(RuntimeError):
    pass

def fail(message: str) -> None:
    raise BootstrapPrivilegedError(message)

def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            fail(f"duplicate JSON field is forbidden: {key}")
        value[key] = item
    return value

@dataclass(frozen=True)
class Request:
    operation: str
    authorization_issue_number: int | None

@dataclass(frozen=True)
class Registration:
    source_sha: str
    source_checkout: Path
    manager_checkout: Path
    manager_uid: int
    manager_gid: int
    release_files: Mapping[str, str]
    socket_sha256: str
    service_sha256: str

def parse_request(raw: bytes) -> Request:
    if type(raw) is not bytes or not raw or len(raw) > REQUEST_MAX_BYTES:
        fail("request size is invalid")
    if b"\x00" in raw or b"\r" in raw or not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        fail("request framing is invalid")
    try:
        value = json.loads(raw[:-1].decode("utf-8", "strict"), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BootstrapPrivilegedError("request is not strict UTF-8 JSON") from exc
    if type(value) is not dict:
        fail("request must be an object")
    if value.get("schema") != REQUEST_SCHEMA:
        fail("request schema mismatch")
    operation = value.get("operation")
    if operation == PREFLIGHT:
        if set(value) != {"schema", "operation"}:
            fail("preflight request fields are not exact")
        return Request(PREFLIGHT, None)
    if operation == APPLY:
        if set(value) != {"schema", "operation", "authorization_issue_number"}:
            fail("apply request fields are not exact")
        number = value.get("authorization_issue_number")
        if type(number) is not int or not (1 <= number <= 2_147_483_647):
            fail("authorization_issue_number is invalid")
        return Request(APPLY, number)
    fail("operation is not a fixed bootstrap operation")

def _regular_bytes(path: Path, *, mode: int, max_bytes: int = 2 * 1024 * 1024) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise BootstrapPrivilegedError(f"required file metadata unavailable: {path}") from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != ROOT_UID
        or before.st_gid != ROOT_GID
        or stat.S_IMODE(before.st_mode) != mode
        or before.st_size < 1
        or before.st_size > max_bytes
    ):
        fail(f"required file metadata drifted: {path}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise BootstrapPrivilegedError(f"required file cannot be read: {path}") from exc
    after = path.lstat()
    if (
        before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns
    ) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
    ):
        fail(f"required file changed while being read: {path}")
    return data

def _root_dir(path: Path, mode: int) -> None:
    try:
        meta = path.lstat()
    except OSError as exc:
        raise BootstrapPrivilegedError(f"required directory metadata unavailable: {path}") from exc
    if (
        not stat.S_ISDIR(meta.st_mode)
        or stat.S_ISLNK(meta.st_mode)
        or meta.st_uid != ROOT_UID
        or meta.st_gid != ROOT_GID
        or stat.S_IMODE(meta.st_mode) != mode
    ):
        fail(f"required directory metadata drifted: {path}")

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def load_registration(path: Path = REGISTRATION_PATH) -> Registration:
    _root_dir(CAPABILITY_ROOT, 0o755)
    _root_dir(RELEASE_ROOT, 0o755)
    _root_dir(REGISTRATION_PATH.parent, 0o700)
    _root_dir(REPLAY_ROOT, 0o700)
    raw = _regular_bytes(path, mode=0o600, max_bytes=65536)
    try:
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BootstrapPrivilegedError("bootstrap registration is malformed") from exc
    fields = {
        "schema", "source_sha", "source_checkout", "manager_checkout",
        "manager_uid", "manager_gid", "release_files", "socket_sha256", "service_sha256"
    }
    if type(value) is not dict or set(value) != fields or value.get("schema") != REGISTRATION_SCHEMA:
        fail("bootstrap registration fields drifted")
    source_sha = value["source_sha"]
    source_checkout = Path(str(value["source_checkout"]))
    manager = Path(str(value["manager_checkout"]))
    uid, gid = value["manager_uid"], value["manager_gid"]
    release_files = value["release_files"]
    if type(source_sha) is not str or _SHA40.fullmatch(source_sha) is None or source_sha == PREDECESSOR_SHA:
        fail("bootstrap registration source SHA is invalid")
    if not source_checkout.is_absolute() or not manager.is_absolute() or manager.name != "RPi5_main":
        fail("bootstrap registration checkout identity is invalid")
    if source_checkout.parent != manager.parent or source_checkout == manager:
        fail("bootstrap source checkout is outside canonical manager parent")
    if type(uid) is not int or type(gid) is not int or uid <= 0 or gid <= 0:
        fail("bootstrap registration manager identity is invalid")
    if type(release_files) is not dict or set(release_files) != set(RELEASE_FILES):
        fail("bootstrap release manifest drifted")
    for rel, digest in release_files.items():
        if type(digest) is not str or _SHA256.fullmatch(digest) is None:
            fail(f"bootstrap release digest invalid: {rel}")
        observed = _sha256(_regular_bytes(RELEASE_ROOT / rel, mode=RELEASE_FILES[rel]))
        if observed != digest:
            fail(f"bootstrap release file drifted: {rel}")
    for field in ("socket_sha256", "service_sha256"):
        if type(value[field]) is not str or _SHA256.fullmatch(value[field]) is None:
            fail(f"bootstrap registration {field} invalid")
    if _sha256(_regular_bytes(SOCKET_UNIT_PATH, mode=0o644, max_bytes=65536)) != value["socket_sha256"]:
        fail("bootstrap socket unit drifted")
    if _sha256(_regular_bytes(SERVICE_UNIT_PATH, mode=0o644, max_bytes=65536)) != value["service_sha256"]:
        fail("bootstrap service unit drifted")
    return Registration(
        source_sha=source_sha,
        source_checkout=source_checkout,
        manager_checkout=manager,
        manager_uid=uid,
        manager_gid=gid,
        release_files=dict(release_files),
        socket_sha256=value["socket_sha256"],
        service_sha256=value["service_sha256"],
    )

class ManagerGitAdapter:
    def __init__(self, registration: Registration, installer: Any):
        self.registration = registration
        self.installer = installer
        for name in (
            "ARTIFACTS", "SERVICE_SOURCE", "REGISTRATION_SCHEMA", "TARGET_ROOT", "PACKAGE_ROOT",
            "BROKER_TARGET", "CONFIG_ROOT", "REGISTRATION", "STATE_ROOT", "STATE_DB",
            "SYSTEMD_ROOT", "SOCKET_NAME", "SERVICE_NAME"
        ):
            if hasattr(installer, name):
                setattr(self, name, getattr(installer, name))

    def _run(self, repo: Path, args: tuple[str, ...], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        allowed_repos = {self.registration.manager_checkout, self.registration.source_checkout}
        if repo not in allowed_repos:
            fail("Git repository escaped fixed bootstrap checkout set")
        allowed = (
            args == ("rev-parse", "HEAD")
            or args == ("remote", "get-url", "origin")
            or args == ("status", "--porcelain", "--untracked-files=all")
            or args == ("rev-parse", "--path-format=absolute", "--git-common-dir")
            or (
                len(args) == 4 and args[:2] == ("merge-base", "--is-ancestor")
                and args[2] == PREDECESSOR_SHA and args[3] == self.registration.source_sha
            )
            or (len(args) == 4 and args[:2] == ("ls-tree", PREDECESSOR_SHA) and args[2] == "--")
            or (len(args) == 2 and args[0] == "show" and args[1].startswith(PREDECESSOR_SHA + ":"))
        )
        if not allowed:
            fail("Git argv escaped fixed bootstrap allowlist")
        cmd = ["/usr/bin/git", "-C", str(repo), *args]
        try:
            return subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
                user=self.registration.manager_uid,
                group=self.registration.manager_gid,
                extra_groups=(),
                shell=False,
                close_fds=True,
                check=check,
            )
        except subprocess.CalledProcessError as exc:
            raise BootstrapPrivilegedError("manager-identity Git subprocess failed") from exc

    def source_sha(self) -> str:
        checkout = self.registration.source_checkout
        if self._run(checkout, ("rev-parse", "HEAD")).stdout.strip() != self.registration.source_sha:
            fail("bootstrap source checkout HEAD drifted")
        if self._run(checkout, ("remote", "get-url", "origin")).stdout.strip() != REVIEWED_ORIGIN:
            fail("bootstrap source checkout origin drifted")
        if self._run(checkout, ("status", "--porcelain", "--untracked-files=all")).stdout != "":
            fail("bootstrap source checkout is dirty")
        source_common = Path(
            self._run(checkout, ("rev-parse", "--path-format=absolute", "--git-common-dir")).stdout.strip()
        ).resolve()
        manager_common = Path(
            self._run(self.registration.manager_checkout, ("rev-parse", "--path-format=absolute", "--git-common-dir")).stdout.strip()
        ).resolve()
        if source_common != manager_common or manager_common != (self.registration.manager_checkout / ".git").resolve():
            fail("bootstrap checkout is not linked to canonical manager Git directory")
        return self.registration.source_sha

    def run_git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self._run(self.registration.source_checkout, tuple(args), check=check)

    def canonical_manager_checkout(self) -> Path:
        manager = self.registration.manager_checkout
        try:
            info = manager.lstat()
        except OSError as exc:
            raise BootstrapPrivilegedError("canonical manager metadata unavailable") from exc
        if (
            not stat.S_ISDIR(info.st_mode) or manager.is_symlink()
            or info.st_uid != self.registration.manager_uid
            or info.st_gid != self.registration.manager_gid
        ):
            fail("canonical manager filesystem identity drifted")
        return manager

    def manager_identity(self, manager: Path) -> tuple[int, int]:
        if manager != self.registration.manager_checkout:
            fail("canonical manager path drifted")
        return self.registration.manager_uid, self.registration.manager_gid

    def render_service_unit(self, data: bytes, manager: Path) -> bytes:
        return self.installer.render_service_unit(data, manager)

def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        fail(f"reviewed module cannot be loaded: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def _recovery_and_adapter(registration: Registration) -> tuple[Any, ManagerGitAdapter]:
    recovery = _load_module(
        RELEASE_ROOT / "ops/recovery/weather_v9_predecessor_state_bootstrap.py",
        "weather_v9_predecessor_state_bootstrap_privileged_runtime",
    )
    installer = _load_module(
        RELEASE_ROOT / "scripts/install-weather-operator-v9-host-capability.py",
        "weather_v9_host_capability_installer_privileged_runtime",
    )
    adapter = ManagerGitAdapter(registration, installer)
    if adapter.source_sha() != registration.source_sha:
        fail("bootstrap execution source drifted")
    recovery._load_installer = lambda: adapter
    return recovery, adapter

def run_preflight(registration: Registration) -> Mapping[str, Any]:
    recovery, _adapter = _recovery_and_adapter(registration)
    result = recovery.preflight()
    if type(result) is not dict or result.get("result") != "PASS":
        fail("canonical predecessor preflight did not pass")
    if result.get("execution_source_sha") != registration.source_sha:
        fail("canonical predecessor preflight source SHA drifted")
    if result.get("host_mutation_started") is not False:
        fail("preflight unexpectedly reported host mutation")
    return result

@dataclass(frozen=True)
class FetchedIssue:
    value: Mapping[str, Any]
    server_time: datetime

def fetch_issue(issue_number: int) -> FetchedIssue:
    conn = http.client.HTTPSConnection("api.github.com", timeout=10)
    path = f"/repos/{REPOSITORY}/issues/{issue_number}"
    try:
        conn.request(
            "GET", path,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "rozkalns-weather-v9-predecessor-bootstrap/1",
            },
        )
        response = conn.getresponse()
        body = response.read(65537)
        if response.status != 200 or len(body) > 65536:
            fail("authorization issue fetch failed")
        date = response.getheader("Date")
        if not date:
            fail("authorization response omitted Date")
        server_time = parsedate_to_datetime(date).astimezone(timezone.utc)
        value = json.loads(body.decode("utf-8", "strict"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise BootstrapPrivilegedError("authorization issue transport failed") from exc
    finally:
        conn.close()
    if type(value) is not dict:
        fail("authorization issue response is malformed")
    return FetchedIssue(value, server_time)

def _parse_auth_body(body: str) -> Mapping[str, Any]:
    if type(body) is not str or body.count(AUTH_START) != 1 or body.count(AUTH_END) != 1:
        fail("authorization markers are invalid")
    prefix, rest = body.split(AUTH_START, 1)
    encoded, suffix = rest.split(AUTH_END, 1)
    if prefix.strip() or suffix.strip():
        fail("authorization body contains content outside canonical markers")
    try:
        value = json.loads(encoded.strip(), object_pairs_hook=_strict_object)
    except json.JSONDecodeError as exc:
        raise BootstrapPrivilegedError("authorization body JSON is malformed") from exc
    fields = {
        "schema", "operation", "target_alias", "source_sha", "predecessor_sha",
        "host", "live_authorized", "no_retry", "no_cleanup", "no_rollback"
    }
    if type(value) is not dict or set(value) != fields:
        fail("authorization body fields drifted")
    return value

def validate_authorization(
    fetched: FetchedIssue,
    *,
    issue_number: int,
    registration: Registration,
) -> str:
    issue = fetched.value
    if (
        issue.get("number") != issue_number
        or issue.get("state") != "open"
        or issue.get("title") != AUTH_TITLE
        or "pull_request" in issue
        or type(issue.get("user")) is not dict
        or issue["user"].get("id") != OWNER_NUMERIC_ID
        or issue["user"].get("type") != "User"
        or issue.get("performed_via_github_app") is not None
    ):
        fail("authorization GitHub identity drifted")
    value = _parse_auth_body(issue.get("body"))
    exact = {
        "schema": AUTH_SCHEMA,
        "operation": APPLY_OPERATION,
        "target_alias": TARGET_ALIAS,
        "source_sha": registration.source_sha,
        "predecessor_sha": PREDECESSOR_SHA,
        "host": "rpi5",
        "live_authorized": True,
        "no_retry": True,
        "no_cleanup": True,
        "no_rollback": True,
    }
    if value != exact:
        fail("authorization payload drifted")
    created_raw = issue.get("created_at")
    if type(created_raw) is not str or not created_raw.endswith("Z"):
        fail("authorization created_at is invalid")
    try:
        created = datetime.fromisoformat(created_raw[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError as exc:
        raise BootstrapPrivilegedError("authorization created_at is invalid") from exc
    if not isinstance(fetched.server_time, datetime) or fetched.server_time.tzinfo is None:
        fail("authorization server time is invalid")
    age = (fetched.server_time.astimezone(timezone.utc) - created).total_seconds()
    if age < -30 or age > AUTH_TTL_SECONDS:
        fail("authorization TTL is invalid")
    return _sha256(str(issue["body"]).encode("utf-8"))

def revalidate_authorization(
    issue_number: int,
    registration: Registration,
    fetcher: Callable[[int], FetchedIssue] = fetch_issue,
) -> tuple[Mapping[str, Any], str]:
    first = fetcher(issue_number)
    body_sha = validate_authorization(first, issue_number=issue_number, registration=registration)
    second = fetcher(issue_number)
    second_sha = validate_authorization(second, issue_number=issue_number, registration=registration)
    first_id = first.value.get("id")
    second_id = second.value.get("id")
    if (
        first_id != second_id
        or first.value.get("updated_at") != second.value.get("updated_at")
        or body_sha != second_sha
        or abs((second.server_time - first.server_time).total_seconds()) > MAX_GITHUB_SPREAD_SECONDS
    ):
        fail("authorization changed during canonical revalidation")
    return second.value, body_sha

def consume_authorization(
    issue: Mapping[str, Any],
    body_sha256: str,
    registration: Registration,
    replay_path: Path = REPLAY_PATH,
    *,
    chown_fn: Callable[[Path, int, int], None] = os.chown,
    chmod_fn: Callable[[Path, int], None] = os.chmod,
) -> None:
    try:
        replay_path.lstat()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise BootstrapPrivilegedError("authorization replay metadata unavailable") from exc
    else:
        fail("bootstrap authorization was already consumed")
    payload = {
        "schema": "rozkalns.rpi5-main.weather-v9-predecessor-bootstrap-consumed.v1",
        "issue_id": issue.get("id"),
        "issue_number": issue.get("number"),
        "body_sha256": body_sha256,
        "source_sha": registration.source_sha,
    }
    if type(payload["issue_id"]) is not int or payload["issue_id"] <= 0:
        fail("authorization issue id is invalid")
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(replay_path, flags, 0o600)
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        chown_fn(replay_path, ROOT_UID, ROOT_GID)
        chmod_fn(replay_path, 0o600)
        dirfd = os.open(replay_path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    except OSError as exc:
        raise BootstrapPrivilegedError("authorization consumption failed closed") from exc

def run_apply(
    registration: Registration,
    authorization_issue_number: int,
    *,
    fetcher: Callable[[int], FetchedIssue] = fetch_issue,
    replay_path: Path = REPLAY_PATH,
) -> Mapping[str, Any]:
    recovery, _adapter = _recovery_and_adapter(registration)
    issue, body_sha = revalidate_authorization(
        authorization_issue_number, registration, fetcher=fetcher
    )
    # The authorization becomes non-reusable before the first Weather durable-state mutation.
    consume_authorization(issue, body_sha, registration, replay_path=replay_path)
    try:
        result = recovery.apply()
    except Exception as exc:
        raise BootstrapPrivilegedError(
            "predecessor bootstrap apply failed closed after authorization consumption"
        ) from exc
    if type(result) is not dict or result.get("result") != "PASS":
        fail("canonical predecessor bootstrap apply did not pass")
    if result.get("execution_source_sha") != registration.source_sha:
        fail("canonical predecessor bootstrap apply source SHA drifted")
    return result

class PrivilegedBootstrapRuntime:
    def __init__(
        self,
        registration_loader: Callable[[], Registration] = load_registration,
        fetcher: Callable[[int], FetchedIssue] = fetch_issue,
    ):
        self._registration_loader = registration_loader
        self._fetcher = fetcher

    def preflight(self) -> Mapping[str, Any]:
        registration = self._registration_loader()
        result = dict(run_preflight(registration))
        result["broker_operation"] = PREFLIGHT
        return result

    def apply(self, issue_number: int) -> Mapping[str, Any]:
        registration = self._registration_loader()
        result = dict(run_apply(registration, issue_number, fetcher=self._fetcher))
        result["broker_operation"] = APPLY
        return result

def execute_request(raw: bytes, runtime: Any | None = None) -> Mapping[str, Any]:
    request = parse_request(raw)
    runtime = PrivilegedBootstrapRuntime() if runtime is None else runtime
    try:
        if request.operation == PREFLIGHT:
            result = dict(runtime.preflight())
            mutation_started = False
        else:
            assert request.authorization_issue_number is not None
            result = dict(runtime.apply(request.authorization_issue_number))
            mutation_started = bool(result.get("host_mutation_started"))
    except BootstrapPrivilegedError:
        raise
    except Exception as exc:
        raise BootstrapPrivilegedError("fixed bootstrap runtime failed closed") from exc
    return {
        "schema": RECEIPT_SCHEMA,
        "result": "PASS",
        "operation": request.operation,
        "source_sha": result.get("execution_source_sha"),
        "registration_source_sha": result.get("registration_source_sha"),
        "host_mutation_started": mutation_started,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
        "source_merge_authorizes_live": False,
    }

def encode_receipt(value: Mapping[str, Any]) -> bytes:
    raw = (json.dumps(dict(value), sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(raw) > MAX_RECEIPT_BYTES or raw.count(b"\n") != 1:
        fail("broker receipt framing invariant failed")
    return raw

def source_readiness() -> Mapping[str, Any]:
    return {
        "implementation_issue": 628,
        "request_schema": REQUEST_SCHEMA,
        "caller_operations": (PREFLIGHT, APPLY),
        "caller_apply_authority": ("authorization_issue_number",),
        "caller_command_allowed": False,
        "caller_path_allowed": False,
        "caller_argv_allowed": False,
        "caller_environment_allowed": False,
        "caller_identity_allowed": False,
        "caller_hash_or_sha_allowed": False,
        "caller_target_allowed": False,
        "generic_shell_allowed": False,
        "generic_sudo_allowed": False,
        "preflight_live_auth_required": False,
        "apply_live_auth_required": True,
        "authorization_ttl_seconds": AUTH_TTL_SECONDS,
        "authorization_refetch_required": True,
        "authorization_replay_consumed_before_weather_mutation": True,
        "root_git_runs_as_manager_identity": True,
        "source_merge_authorizes_live": False,
        "runtime_activation_enabled": False,
    }
