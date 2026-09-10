from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
from typing import Any, Mapping, Sequence

from .p9_canary import require_isolated_auth_surface
from .p9_isolated_auth_surface import load_contract
from .p9_runtime import build_p9_read_clients
from .protocol import AUTHORIZATION_REPOSITORY, AUTHORIZATION_REPOSITORY_ID, QUEUE_REPOSITORY, AcceptedAuthorization
from .registry import load_registry
from .state import EXPECTED_COLUMNS, STATE_DB_APPLICATION_ID, STATE_DB_SCHEMA_VERSION, StateStore
from .weather_public_runtime_adapter import OPERATION_ID, SOURCE_REPOSITORY, TARGET_ALIAS
from .weather_public_runtime_composite import (
    ConcreteCanonicalWeatherCompositeRevalidator,
    ConcreteWeatherCompositeBaselineResolver,
    FixedPublicGitHubReadClient,
)
from .weather_public_runtime_bootstrap import BASELINE_EVIDENCE_SCHEMA
from .weather_public_runtime_host_wiring import (
    WeatherHostWiringPlan,
    build_weather_host_wiring_plan,
    expected_helper_bindings,
)
from .weather_public_runtime_preactivation import (
    WeatherPreactivationEnvelope,
    prepare_weather_preactivation_envelope,
)
from .weather_public_runtime_stage_helper import parse_activation

BRIDGE_SCHEMA = "rozkalns-weather.public-runtime-privileged-install-activation.v1"
RECEIPT_SCHEMA = "rozkalns-weather.public-runtime-privileged-install-activation-receipt.v1"
TRUSTED_INSTALL_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-install-trusted"
TRUSTED_INSTALL_CHECKOUT_DERIVATION = f"RPi5_CHECKOUT_PARENT/{TRUSTED_INSTALL_CHECKOUT_NAME}"
TRUSTED_INSTALL_CHECKOUT = Path(__file__).resolve().parents[3]
REVIEWED_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
INSTALL_MANIFEST = TRUSTED_INSTALL_CHECKOUT / "ops/deploy/weather-public-runtime-helper-install.json"
INSTALL_ROOT = Path("/usr/local/libexec/rozkalns-weather-public-runtime")
HELPER_EXECUTABLE = Path("/usr/local/libexec/rozkalns-weather-public-runtime-stage-helper")
PACKAGE_ROOT = INSTALL_ROOT / "deploy_executor"
ACTIVATION_FILE = Path("/etc/rozkalns-weather/public-runtime-helper-activation.json")
ACTIVATION_SCHEMA = "rozkalns-weather.public-runtime-helper-activation.v1"
AUTH_SURFACE = Path("/etc/rozkalns-deploy-executor-p9/executor-p9-isolated-auth-surface.json")
EXECUTOR_PRIVATE_KEY = Path("/etc/rozkalns-deploy-executor/github-app.pem")
STATE_DB = Path("/var/lib/rozkalns-deploy-executor-p9/state.sqlite3")
REGISTRY = TRUSTED_INSTALL_CHECKOUT / "ops/deploy/executor-operations.json"
RELEASE_ROOT = Path("/opt/rozkalns-weather/releases")
COMPOSE_PROJECT = "rozkalns-weather-public"
HOST_VOLUME = f"{COMPOSE_PROJECT}_weather_data"
TIMER_NAME = "rozkalns-weather-public-ingest.timer"
SERVICE_NAME = "rozkalns-weather-public-ingest.service"
ROOT_UID = 0
ROOT_GID = 0
RENAME_NOREPLACE = 1
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")

_EXPECTED_ARTIFACTS = (
    ("ops/bin/rozkalns-weather-public-runtime-stage-helper", str(HELPER_EXECUTABLE), 0o755),
    ("ops/lib/weather_public_runtime_helper_package/__init__.py", str(PACKAGE_ROOT / "__init__.py"), 0o644),
    ("ops/lib/deploy_executor/adapters.py", str(PACKAGE_ROOT / "adapters.py"), 0o644),
    ("ops/lib/deploy_executor/queue_normalizer.py", str(PACKAGE_ROOT / "queue_normalizer.py"), 0o644),
    ("ops/lib/deploy_executor/registry.py", str(PACKAGE_ROOT / "registry.py"), 0o644),
    ("ops/lib/deploy_executor/protocol.py", str(PACKAGE_ROOT / "protocol.py"), 0o644),
    ("ops/lib/deploy_executor/weather_public_runtime_adapter.py", str(PACKAGE_ROOT / "weather_public_runtime_adapter.py"), 0o644),
    ("ops/lib/deploy_executor/weather_public_runtime_bootstrap.py", str(PACKAGE_ROOT / "weather_public_runtime_bootstrap.py"), 0o644),
    ("ops/lib/deploy_executor/weather_public_runtime_preactivation.py", str(PACKAGE_ROOT / "weather_public_runtime_preactivation.py"), 0o644),
    ("ops/lib/deploy_executor/weather_public_runtime_host_wiring.py", str(PACKAGE_ROOT / "weather_public_runtime_host_wiring.py"), 0o644),
    ("ops/lib/deploy_executor/weather_public_runtime_execution.py", str(PACKAGE_ROOT / "weather_public_runtime_execution.py"), 0o644),
    ("ops/lib/deploy_executor/weather_public_runtime_candidate_materializer.py", str(PACKAGE_ROOT / "weather_public_runtime_candidate_materializer.py"), 0o644),
    ("ops/lib/deploy_executor/weather_public_runtime_stage_helper.py", str(PACKAGE_ROOT / "weather_public_runtime_stage_helper.py"), 0o644),
)


def expected_install_artifacts() -> tuple[tuple[str, str, int], ...]:
    """Return the immutable helper-install allowlist for trusted controller composition."""
    return _EXPECTED_ARTIFACTS


class WeatherPrivilegedInstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class WeatherPrivilegedInstallReceipt:
    schema: str
    authorization_issue_number: int
    request_id: str
    source_sha: str
    rpi5_main_sha: str
    preactivation_sha256: str
    helper_install_operations: int
    activation_publish_operations: int
    authorization_consumed: bool = True
    stage_invocation_performed: bool = False
    production_mutation_started: bool = True


def _fail(message: str) -> None:
    raise WeatherPrivilegedInstallError(message)


def _mode(meta: os.stat_result) -> int:
    return stat.S_IMODE(meta.st_mode)


def _run_fixed(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
    args = tuple(argv)
    if not args or args[0] not in {"/usr/bin/git", "/usr/bin/docker", "/usr/bin/systemctl"}:
        _fail("privileged bridge command is outside the fixed read-only preflight surface")
    try:
        return subprocess.run(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "HOME": "/nonexistent",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_CONFIG_NOSYSTEM": "1",
            },
            shell=False,
            close_fds=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise WeatherPrivilegedInstallError("fixed preflight command failed to run") from exc


def _require_success(argv: Sequence[str], where: str) -> str:
    result = _run_fixed(argv)
    if result.returncode != 0:
        _fail(f"{where} failed closed")
    if len(result.stdout.encode("utf-8")) > 65536 or len(result.stderr.encode("utf-8")) > 65536:
        _fail(f"{where} output exceeded source limit")
    return result.stdout


def _require_regular(path: Path, *, uid: int | None = None, gid: int | None = None, mode: int | None = None) -> os.stat_result:
    try:
        meta = path.lstat()
    except OSError as exc:
        raise WeatherPrivilegedInstallError(f"required file unavailable: {path}") from exc
    if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:
        _fail(f"required file is not a single-link regular file: {path}")
    if uid is not None and meta.st_uid != uid:
        _fail(f"required file owner drifted: {path}")
    if gid is not None and meta.st_gid != gid:
        _fail(f"required file group drifted: {path}")
    if mode is not None and _mode(meta) != mode:
        _fail(f"required file mode drifted: {path}")
    return meta


def _require_directory(path: Path, *, uid: int | None = None, gid: int | None = None, mode: int | None = None) -> os.stat_result:
    try:
        meta = path.lstat()
    except OSError as exc:
        raise WeatherPrivilegedInstallError(f"required directory unavailable: {path}") from exc
    if not stat.S_ISDIR(meta.st_mode):
        _fail(f"required path is not a directory: {path}")
    if uid is not None and meta.st_uid != uid:
        _fail(f"required directory owner drifted: {path}")
    if gid is not None and meta.st_gid != gid:
        _fail(f"required directory group drifted: {path}")
    if mode is not None and _mode(meta) != mode:
        _fail(f"required directory mode drifted: {path}")
    return meta


def _path_absent(path: Path, label: str) -> None:
    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise WeatherPrivilegedInstallError(f"{label} lstat failed") from exc
    _fail(f"{label} already exists; overwrite/retry is forbidden")


def _validate_trusted_checkout(expected_sha: str) -> None:
    if type(expected_sha) is not str or _SHA40_RE.fullmatch(expected_sha) is None:
        _fail("authorized RPi5_main SHA is invalid")
    if TRUSTED_INSTALL_CHECKOUT.name != TRUSTED_INSTALL_CHECKOUT_NAME:
        _fail("trusted install checkout identity drifted")
    try:
        resolved = TRUSTED_INSTALL_CHECKOUT.resolve(strict=True)
    except OSError as exc:
        raise WeatherPrivilegedInstallError("trusted install checkout is unavailable") from exc
    if resolved != TRUSTED_INSTALL_CHECKOUT:
        _fail("trusted install checkout path drifted")
    _require_directory(TRUSTED_INSTALL_CHECKOUT)
    prefix = ("/usr/bin/git", "--no-optional-locks", "-C", str(TRUSTED_INSTALL_CHECKOUT))
    if _require_success((*prefix, "rev-parse", "HEAD"), "trusted checkout HEAD").strip() != expected_sha:
        _fail("trusted install checkout HEAD does not equal authorized RPi5_main SHA")
    detached = _run_fixed((*prefix, "symbolic-ref", "-q", "HEAD"))
    if detached.returncode != 1 or detached.stdout or detached.stderr:
        _fail("trusted install checkout is not cleanly detached")
    if _require_success((*prefix, "status", "--porcelain=v1", "--untracked-files=all"), "trusted checkout status"):
        _fail("trusted install checkout is not clean")
    if _require_success((*prefix, "remote", "get-url", "origin"), "trusted checkout origin").strip() != REVIEWED_ORIGIN:
        _fail("trusted install checkout origin drifted")
    for relative in (
        "ops/deploy/weather-public-runtime-helper-install.json",
        "ops/deploy/executor-operations.json",
        "ops/bin/rozkalns-weather-public-runtime-privileged-install",
        "ops/lib/deploy_executor/weather_public_runtime_privileged_install.py",
    ):
        _require_regular(TRUSTED_INSTALL_CHECKOUT / relative)


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON field is forbidden: {key}")
        result[key] = value
    return result


def _load_install_manifest() -> tuple[tuple[str, str, int], ...]:
    _require_regular(INSTALL_MANIFEST)
    try:
        value = json.loads(
            INSTALL_MANIFEST.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise WeatherPrivilegedInstallError("helper install manifest is invalid") from exc
    if type(value) is not dict:
        _fail("helper install manifest is not an object")
    required = {
        "contract": "rozkalns-weather.public-runtime-helper-install.v1",
        "status": "SOURCE_ONLY_INSTALL_DISABLED",
        "install_root": str(INSTALL_ROOT),
        "executable_path": str(HELPER_EXECUTABLE),
        "package_root": str(PACKAGE_ROOT),
        "required_owner_uid": ROOT_UID,
        "required_owner_gid": ROOT_GID,
        "artifact_count": len(_EXPECTED_ARTIFACTS),
        "trusted_checkout_bootstrap_contract": "ops/deploy/rpi5-main-weather-public-runtime-install-trusted-checkout-bootstrap.json",
        "trusted_checkout_target": TRUSTED_INSTALL_CHECKOUT_DERIVATION,
        "trusted_checkout_required_before_live_installation": True,
        "ordinary_manager_checkout_install_source_allowed": False,
        "directory_mode": "0755",
        "entrypoint_mode": "0755",
        "module_mode": "0644",
    }
    for key, expected in required.items():
        if value.get(key) != expected:
            _fail(f"helper install manifest field drifted: {key}")
    artifacts = value.get("artifacts")
    if type(artifacts) is not list or len(artifacts) != len(_EXPECTED_ARTIFACTS):
        _fail("helper install artifact list drifted")
    observed = []
    for item in artifacts:
        if type(item) is not dict:
            _fail("helper install artifact entry is invalid")
        try:
            observed.append((item["source"], item["destination"], int(item["mode"], 8)))
        except (KeyError, TypeError, ValueError) as exc:
            raise WeatherPrivilegedInstallError("helper install artifact entry is invalid") from exc
    if tuple(observed) != _EXPECTED_ARTIFACTS:
        _fail("helper install artifact identities drifted")
    return tuple(observed)


class _AuthorizationResolver:
    def __init__(self, client: Any):
        self._client = client

    def resolve(self, issue_number: int) -> Mapping[str, Any]:
        response = self._client.get_json(f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{issue_number}")
        if type(response.value) is not dict:
            _fail("authorization issue response is invalid")
        return response.value


class _QueueResolver:
    def __init__(self, client: Any):
        self._client = client

    def resolve(self, *, repository_full_name: str, issue_number: int) -> Mapping[str, Any]:
        if repository_full_name != QUEUE_REPOSITORY:
            _fail("queue repository drifted")
        response = self._client.get_json(f"/repos/{QUEUE_REPOSITORY}/issues/{issue_number}")
        if type(response.value) is not dict:
            _fail("queue issue response is invalid")
        return response.value


class _WeatherDurableReplayAuthority:
    def __init__(self) -> None:
        self._candidate: AcceptedAuthorization | None = None

    @staticmethod
    def _readonly_connection() -> sqlite3.Connection:
        if not STATE_DB.is_file():
            _fail("durable replay database is unavailable")
        try:
            conn = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                _fail("durable replay quick_check failed")
            if conn.execute("PRAGMA application_id").fetchone()[0] != STATE_DB_APPLICATION_ID:
                _fail("durable replay application_id drifted")
            if conn.execute("PRAGMA user_version").fetchone()[0] != STATE_DB_SCHEMA_VERSION:
                _fail("durable replay schema version drifted")
            columns = tuple(
                (row["name"], row["type"], row["notnull"], row["pk"])
                for row in conn.execute("PRAGMA table_info(requests)").fetchall()
            )
            if columns != EXPECTED_COLUMNS:
                _fail("durable replay schema drifted")
            return conn
        except WeatherPrivilegedInstallError:
            raise
        except sqlite3.DatabaseError as exc:
            raise WeatherPrivilegedInstallError("durable replay database read failed") from exc

    @classmethod
    def _available(cls, *, issue_id: int, request_id: str) -> bool:
        conn = cls._readonly_connection()
        try:
            rows = conn.execute(
                "SELECT request_id FROM requests WHERE (repository_id = ? AND issue_id = ?) OR request_id = ? LIMIT 2",
                (AUTHORIZATION_REPOSITORY_ID, issue_id, request_id),
            ).fetchall()
            return len(rows) == 0
        finally:
            conn.close()

    def is_available(self, accepted: AcceptedAuthorization) -> bool:
        if type(accepted) is not AcceptedAuthorization:
            _fail("replay authority requires canonical AcceptedAuthorization")
        available = self._available(issue_id=accepted.issue_id, request_id=accepted.request_id)
        if available:
            if self._candidate is not None and self._candidate != accepted:
                _fail("authorization changed between replay checks")
            self._candidate = accepted
        return available

    def assert_unconsumed(self, *, issue_id: int, request_id: str) -> None:
        if not self._available(issue_id=issue_id, request_id=request_id):
            _fail("authorization is already present in durable replay state")

    def consume(self, request_id: str) -> None:
        candidate = self._candidate
        if candidate is None or candidate.request_id != request_id:
            _fail("replay consume has no canonical authorization candidate")
        store = StateStore(STATE_DB)
        try:
            store.discover(
                repository_id=candidate.repository_id,
                issue_id=candidate.issue_id,
                request_id=candidate.request_id,
                canonical_payload_sha256=candidate.canonical_payload_sha256,
                raw_body_sha256=candidate.raw_body_sha256,
            )
            store.transition(request_id, "VALIDATING")
            store.transition(request_id, "ACCEPTED")
            record = store.consume(request_id)
            if record.state != "CONSUMED":
                _fail("authorization did not reach CONSUMED")
        finally:
            store.close()

    @staticmethod
    def mark_succeeded(request_id: str) -> None:
        store = StateStore(STATE_DB)
        try:
            store.transition(request_id, "VERIFYING")
            record = store.transition(request_id, "SUCCEEDED")
            if record.state != "SUCCEEDED":
                _fail("authorization result did not reach SUCCEEDED")
        finally:
            store.close()


class _FirstInstallSanitizedBaselineProvider:
    def resolve(self, *, source_sha: str, target_alias: str) -> Mapping[str, Any]:
        if target_alias != TARGET_ALIAS or type(source_sha) is not str or _SHA40_RE.fullmatch(source_sha) is None:
            _fail("sanitized baseline request identity drifted")
        _path_absent(RELEASE_ROOT / source_sha, "Weather release")
        _path_absent(INSTALL_ROOT, "Weather helper support root")
        _path_absent(HELPER_EXECUTABLE, "Weather helper executable")
        _path_absent(ACTIVATION_FILE, "Weather helper activation")
        volumes = _require_success(
            ("/usr/bin/docker", "volume", "ls", "--filter", f"name=^{HOST_VOLUME}$", "--format", "{{.Name}}"),
            "Weather volume baseline",
        ).strip()
        if volumes:
            _fail("Weather persistent volume is not absent")
        containers = _require_success(
            ("/usr/bin/docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={COMPOSE_PROJECT}", "--format", "{{.ID}}"),
            "Weather container baseline",
        ).strip()
        if containers:
            _fail("Weather Compose project is not absent")
        for unit in (TIMER_NAME, SERVICE_NAME):
            state = _require_success(
                ("/usr/bin/systemctl", "show", unit, "--property=LoadState", "--value"),
                f"{unit} baseline",
            ).strip()
            if state != "not-found":
                _fail(f"{unit} is not absent")
        return {
            "schema": BASELINE_EVIDENCE_SCHEMA,
            "target_alias": TARGET_ALIAS,
            "deployment_state": "not_deployed",
            "current_source_sha": None,
            "persistent_volume_state": "absent",
            "schema_state": "absent",
            "schema_version": None,
            "public_ingest_schedule_state": "absent",
            "bootstrap_stage_state": "not_started",
            "privacy_safe": True,
        }


def _rename_noreplace(source: Path, destination: Path) -> None:
    try:
        source_fd = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        destination_fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise WeatherPrivilegedInstallError("atomic publish parent open failed") from exc
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            _fail("atomic publish requires renameat2")
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        if renameat2(
            source_fd,
            os.fsencode(source.name),
            destination_fd,
            os.fsencode(destination.name),
            RENAME_NOREPLACE,
        ) != 0:
            err = ctypes.get_errno()
            if err == errno.EEXIST:
                _fail("atomic publish destination already exists")
            raise OSError(err, os.strerror(err), str(destination))
        os.fsync(source_fd)
        if destination_fd != source_fd:
            os.fsync(destination_fd)
    finally:
        os.close(source_fd)
        os.close(destination_fd)


def _copy_exact(source: Path, destination: Path, mode: int) -> None:
    source_meta = _require_regular(source)
    if source_meta.st_size > 2 * 1024 * 1024:
        _fail("helper artifact exceeds source size limit")
    data = source.read_bytes()
    after = source.lstat()
    if (
        len(data) != source_meta.st_size
        or (after.st_dev, after.st_ino, after.st_size) != (source_meta.st_dev, source_meta.st_ino, source_meta.st_size)
    ):
        _fail("helper artifact changed while being read")
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(fd, data[offset:])
        os.fchmod(fd, mode)
        os.fchown(fd, ROOT_UID, ROOT_GID)
        os.fsync(fd)
    finally:
        os.close(fd)


def _verify_installed(artifacts: tuple[tuple[str, str, int], ...]) -> None:
    _require_directory(INSTALL_ROOT, uid=ROOT_UID, gid=ROOT_GID, mode=0o755)
    _require_directory(PACKAGE_ROOT, uid=ROOT_UID, gid=ROOT_GID, mode=0o755)
    for source_relative, destination_text, mode in artifacts:
        source = TRUSTED_INSTALL_CHECKOUT / source_relative
        destination = Path(destination_text)
        _require_regular(destination, uid=ROOT_UID, gid=ROOT_GID, mode=mode)
        if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(destination.read_bytes()).digest():
            _fail("installed helper artifact content drifted")
    package_names = {path.name for path in PACKAGE_ROOT.iterdir()}
    expected_package_names = {Path(destination).name for _, destination, _ in artifacts if destination.startswith(str(PACKAGE_ROOT) + "/")}
    if package_names != expected_package_names:
        _fail("installed helper package contains unexpected entries")
    if {path.name for path in INSTALL_ROOT.iterdir()} != {"deploy_executor"}:
        _fail("installed helper support root contains unexpected entries")


def _install_helper_transaction(request_id: str, artifacts: tuple[tuple[str, str, int], ...]) -> int:
    _path_absent(INSTALL_ROOT, "Weather helper support root")
    _path_absent(HELPER_EXECUTABLE, "Weather helper executable")
    parent = INSTALL_ROOT.parent
    _require_directory(parent, uid=ROOT_UID, gid=ROOT_GID)
    stage = parent / f".rozkalns-weather-public-runtime.install-{request_id}"
    _path_absent(stage, "Weather helper install stage")
    os.mkdir(stage, 0o700)
    os.chown(stage, ROOT_UID, ROOT_GID)
    package_stage = stage / "deploy_executor"
    os.mkdir(package_stage, 0o755)
    os.chown(package_stage, ROOT_UID, ROOT_GID)
    entry_stage = stage / ".stage-helper"
    for source_relative, destination_text, mode in artifacts:
        source = TRUSTED_INSTALL_CHECKOUT / source_relative
        destination = entry_stage if destination_text == str(HELPER_EXECUTABLE) else package_stage / Path(destination_text).name
        _copy_exact(source, destination, mode)
    os.chmod(stage, 0o755)
    os.chown(stage, ROOT_UID, ROOT_GID)
    _rename_noreplace(stage, INSTALL_ROOT)
    _rename_noreplace(INSTALL_ROOT / ".stage-helper", HELPER_EXECUTABLE)
    _verify_installed(artifacts)
    return 1


def _activation_payload(plan: WeatherHostWiringPlan) -> dict[str, Any]:
    return {
        "schema": ACTIVATION_SCHEMA,
        "enabled": True,
        "target_alias": TARGET_ALIAS,
        "operation_id": OPERATION_ID,
        "source_sha": plan.source_sha,
        "preactivation_sha256": plan.preactivation_sha256,
        "start_date": plan.start_date,
        "end_date": plan.end_date,
        "recovery_decision": plan.recovery_decision,
        "allowed_helper_ids": [binding.helper_id for binding in expected_helper_bindings()],
    }


def _publish_activation(request_id: str, plan: WeatherHostWiringPlan) -> int:
    _path_absent(ACTIVATION_FILE, "Weather helper activation")
    parent = ACTIVATION_FILE.parent
    if parent.exists():
        _require_directory(parent, uid=ROOT_UID, gid=ROOT_GID, mode=0o755)
    else:
        os.mkdir(parent, 0o755)
        os.chown(parent, ROOT_UID, ROOT_GID)
    payload = _activation_payload(plan)
    parse_activation(payload)
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")
    stage = parent / f".{ACTIVATION_FILE.name}.{request_id}.new"
    _path_absent(stage, "Weather activation stage")
    fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        offset = 0
        while offset < len(raw):
            offset += os.write(fd, raw[offset:])
        os.fchmod(fd, 0o600)
        os.fchown(fd, ROOT_UID, ROOT_GID)
        os.fsync(fd)
    finally:
        os.close(fd)
    _rename_noreplace(stage, ACTIVATION_FILE)
    _require_regular(ACTIVATION_FILE, uid=ROOT_UID, gid=ROOT_GID, mode=0o600)
    if ACTIVATION_FILE.read_bytes() != raw:
        _fail("Weather activation bytes drifted after publish")
    parse_activation(json.loads(raw.decode("utf-8")))
    return 1


def _prepare_envelope(issue_number: int, replay: _WeatherDurableReplayAuthority) -> tuple[WeatherPreactivationEnvelope, Any]:
    auth_surface = load_contract(AUTH_SURFACE)
    require_isolated_auth_surface(auth_surface)
    registry = load_registry(REGISTRY)
    if registry.execution_enabled is not False:
        _fail("registry unexpectedly enables execution")
    clients = build_p9_read_clients(auth_surface=auth_surface, private_key=EXECUTOR_PRIVATE_KEY)
    source_client = FixedPublicGitHubReadClient()
    revalidator = ConcreteCanonicalWeatherCompositeRevalidator(
        authorization_client=clients.authorization,
        queue_client=clients.queue,
        source_client=source_client,
        auth_surface=auth_surface,
        registry=registry,
        replay_availability=replay,
    )
    initial = clients.authorization.get_json(f"/repos/{AUTHORIZATION_REPOSITORY}/issues/{issue_number}")
    if not isinstance(initial.server_time, datetime):
        _fail("GitHub server time is unavailable")
    authority = revalidator.revalidate_composite(issue_number)
    baseline_provider = _FirstInstallSanitizedBaselineProvider()
    baseline_resolver = ConcreteWeatherCompositeBaselineResolver(
        provider=baseline_provider,
        expected_token=authority.expected_bootstrap_baseline_token,
    )
    envelope = prepare_weather_preactivation_envelope(
        issue_number,
        server_time=initial.server_time,
        governance_ok=True,
        authorization_resolver=_AuthorizationResolver(clients.authorization),
        queue_resolver=_QueueResolver(clients.queue),
        replay_guard=replay,
        canonical_revalidator=revalidator,
        baseline_resolver=baseline_resolver,
    )
    final_authority = revalidator.revalidate_composite(issue_number)
    if (
        final_authority.request_id != envelope.request_id
        or final_authority.source_sha != envelope.source_sha
        or final_authority.expected_bootstrap_baseline_token != envelope.bootstrap_baseline_token
        or final_authority.start_date != envelope.start_date
        or final_authority.end_date != envelope.end_date
        or final_authority.recovery_decision != envelope.recovery_decision
    ):
        _fail("canonical Weather authority drifted before privileged install")
    return envelope, final_authority


def run_privileged_install_activation(issue_number: int) -> WeatherPrivilegedInstallReceipt:
    if os.geteuid() != 0:
        _fail("privileged Weather bridge must run as root")
    if type(issue_number) is not int or not 1 <= issue_number <= 2_147_483_647:
        _fail("authorization issue number is invalid")
    replay = _WeatherDurableReplayAuthority()
    envelope, authority = _prepare_envelope(issue_number, replay)
    _validate_trusted_checkout(authority.rpi5_main_sha)
    artifacts = _load_install_manifest()
    plan = build_weather_host_wiring_plan(envelope)
    _path_absent(INSTALL_ROOT, "Weather helper support root")
    _path_absent(HELPER_EXECUTABLE, "Weather helper executable")
    _path_absent(ACTIVATION_FILE, "Weather helper activation")
    replay.assert_unconsumed(issue_id=envelope.authorization_issue_id, request_id=envelope.request_id)

    replay.consume(envelope.request_id)
    install_ops = _install_helper_transaction(envelope.request_id, artifacts)
    activation_ops = _publish_activation(envelope.request_id, plan)
    replay.mark_succeeded(envelope.request_id)
    return WeatherPrivilegedInstallReceipt(
        schema=RECEIPT_SCHEMA,
        authorization_issue_number=issue_number,
        request_id=envelope.request_id,
        source_sha=envelope.source_sha,
        rpi5_main_sha=authority.rpi5_main_sha,
        preactivation_sha256=plan.preactivation_sha256,
        helper_install_operations=install_ops,
        activation_publish_operations=activation_ops,
    )


def public_receipt(receipt: WeatherPrivilegedInstallReceipt) -> Mapping[str, Any]:
    if type(receipt) is not WeatherPrivilegedInstallReceipt:
        _fail("privileged install receipt type is invalid")
    return asdict(receipt)


def source_readiness() -> Mapping[str, Any]:
    return {
        "schema": BRIDGE_SCHEMA,
        "caller_authority": ("authorization_issue_number",),
        "trusted_install_checkout": TRUSTED_INSTALL_CHECKOUT_DERIVATION,
        "helper_install_manifest": str(INSTALL_MANIFEST),
        "helper_install_artifact_count": len(_EXPECTED_ARTIFACTS),
        "activation_file": str(ACTIVATION_FILE),
        "durable_replay_state": str(STATE_DB),
        "capability_specific_root_entrypoint_source_present": True,
        "runtime_live_authority": False,
        "privileged_install_invocation_enabled": False,
        "helper_installation_enabled": False,
        "activation_publication_enabled": False,
        "stage_invocation_enabled": False,
        "production_mutation_enabled": False,
        "production_mutation_started": False,
        "generic_shell_authority": False,
        "caller_supplied_path_allowed": False,
        "caller_supplied_argv_allowed": False,
        "caller_supplied_environment_allowed": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }
