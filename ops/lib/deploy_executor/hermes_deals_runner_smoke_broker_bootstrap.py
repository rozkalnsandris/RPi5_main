from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Mapping, Sequence

IMPLEMENTATION_ISSUE = 570
CHECKOUT_ISOLATION_ISSUE = 576
TRUSTED_CHECKOUT_NAME = "RPi5_main-runner-smoke-broker-bootstrap-trusted"
REVIEWED_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
EXPECTED_HEAD_MODE = "detached"
SOURCE_DELIVERY_CONTRACT = Path(
    "ops/deploy/rpi5-main-runner-smoke-broker-bootstrap-source-trusted-checkout-bootstrap.json"
)
RELEASE_ROOT = Path("/usr/local/libexec/rozkalns-runner-smoke-install")
RELEASES_ROOT = RELEASE_ROOT / "releases"
CURRENT_LINK = RELEASE_ROOT / "current"
SOCKET_SOURCE = Path("ops/systemd/rozkalns-hermes-deals-runner-smoke-install.socket")
SERVICE_SOURCE = Path("ops/systemd/rozkalns-hermes-deals-runner-smoke-install@.service")
SOCKET_DESTINATION = Path("/etc/systemd/system/rozkalns-hermes-deals-runner-smoke-install.socket")
SERVICE_DESTINATION = Path("/etc/systemd/system/rozkalns-hermes-deals-runner-smoke-install@.service")
SOCKET_UNIT = "rozkalns-hermes-deals-runner-smoke-install.socket"
BROKER_ENTRYPOINT = Path("ops/bin/rpi5-hermes-deals-runner-smoke-install-broker")
PACKAGE_ROOT = Path("ops/lib/deploy_executor")
ROOT_UID = 0
ROOT_GID = 0
DIRECTORY_MODE = 0o755
EXECUTABLE_MODE = 0o755
MODULE_MODE = 0o644
UNIT_MODE = 0o644
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
MAX_GIT_OUTPUT = 65536
MAX_SYSTEMCTL_OUTPUT = 4096
RECEIPT_SCHEMA = "rozkalns.hermes-deals.runner-smoke-broker-bootstrap-receipt.v1"
PLAN_SCHEMA = "rozkalns.hermes-deals.runner-smoke-broker-bootstrap-plan.v1"
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_FIXED_ENV = {
    "PATH": "/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "HOME": "/nonexistent",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_CONFIG_NOSYSTEM": "1",
}

# Fixed runtime closure for the broker. This is intentionally explicit: no dynamic
# import discovery and no whole-repository copy are permitted by the live installer.
PACKAGE_MODULES = (
    "__init__.py",
    "adapters.py",
    "github_app_auth.py",
    "hermes_deals_origin_adapter.py",
    "hermes_deals_origin_dispatch_request.py",
    "hermes_deals_origin_host_evidence.py",
    "hermes_deals_origin_privileged_broker.py",
    "hermes_deals_origin_privileged_consumer.py",
    "hermes_deals_origin_privileged_dispatcher.py",
    "hermes_deals_origin_runtime_adapters.py",
    "hermes_deals_origin_source_auth.py",
    "hermes_deals_runner_smoke_install.py",
    "hermes_deals_runner_smoke_install_broker.py",
    "hermes_deals_runner_smoke_install_consumer.py",
    "hermes_deals_runner_smoke_install_execution_bridge.py",
    "hermes_deals_runner_smoke_install_runtime.py",
    "p9_canary.py",
    "p9_isolated_auth_surface.py",
    "p9_runtime.py",
    "p9_source_auth.py",
    "protocol.py",
    "queue_normalizer.py",
    "registry.py",
    "source_evidence.py",
    "state.py",
    "transport.py",
)

MUTATION_SEQUENCE = (
    "publish-root-owned-sha-release",
    "publish-current-symlink",
    "publish-fixed-systemd-units",
    "systemctl-daemon-reload",
    "enable-start-fixed-socket",
)


class RunnerSmokeBrokerBootstrapError(RuntimeError):
    pass


class RunnerSmokeBrokerBootstrapApplyError(RunnerSmokeBrokerBootstrapError):
    def __init__(self, message: str, *, mutation_started: bool) -> None:
        super().__init__(message)
        self.mutation_started = mutation_started


@dataclass(frozen=True)
class BootstrapObservation:
    source_sha: str
    filesystem_state: str
    socket_enabled_state: str
    socket_active_state: str


@dataclass(frozen=True)
class BootstrapPlan:
    schema: str
    decision: str
    source_sha: str
    mutations_required: tuple[str, ...]
    caller_arguments: tuple[str, ...] = ()
    generic_sudo_allowed: bool = False
    automatic_retry: bool = False
    automatic_cleanup: bool = False
    automatic_rollback: bool = False


def source_readiness() -> Mapping[str, Any]:
    return {
        "schema": PLAN_SCHEMA,
        "implementation_issue": IMPLEMENTATION_ISSUE,
        "checkout_isolation_issue": CHECKOUT_ISOLATION_ISSUE,
        "trusted_checkout_name": TRUSTED_CHECKOUT_NAME,
        "reviewed_origin": REVIEWED_ORIGIN,
        "expected_head_mode": EXPECTED_HEAD_MODE,
        "source_delivery_contract": str(SOURCE_DELIVERY_CONTRACT),
        "trusted_checkout_must_equal_origin_main": True,
        "prior_source_delivery_exact_main_required": True,
        "source_delivery_live_authorized": False,
        "release_root": str(RELEASE_ROOT),
        "current_link": str(CURRENT_LINK),
        "socket_destination": str(SOCKET_DESTINATION),
        "service_destination": str(SERVICE_DESTINATION),
        "socket_unit": SOCKET_UNIT,
        "runtime_artifact_count": 1 + len(PACKAGE_MODULES),
        "package_modules": PACKAGE_MODULES,
        "caller_authority": (),
        "generic_sudo_allowed": False,
        "caller_command_allowed": False,
        "caller_path_allowed": False,
        "caller_argv_allowed": False,
        "caller_environment_allowed": False,
        "caller_unit_allowed": False,
        "dynamic_module_discovery_allowed": False,
        "whole_repository_copy_allowed": False,
        "rdc_no_new_privileges_must_remain": True,
        "bootstrap_apply_implemented": True,
        "runtime_activation_enabled": False,
        "systemd_socket_installed": False,
        "source_merge_authorizes_live": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
        "production_mutation_started": False,
    }


def runtime_artifacts() -> tuple[tuple[Path, Path, int], ...]:
    artifacts: list[tuple[Path, Path, int]] = [
        (BROKER_ENTRYPOINT, BROKER_ENTRYPOINT, EXECUTABLE_MODE),
    ]
    artifacts.extend(
        (PACKAGE_ROOT / name, PACKAGE_ROOT / name, MODULE_MODE)
        for name in PACKAGE_MODULES
    )
    return tuple(artifacts)


def _fail(message: str) -> None:
    raise RunnerSmokeBrokerBootstrapError(message)


def _git(checkout: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            [
                "/usr/bin/git",
                "--no-optional-locks",
                "-c",
                f"safe.directory={checkout}",
                "-C",
                str(checkout),
                *args,
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            shell=False,
            close_fds=True,
            env=_FIXED_ENV,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise RunnerSmokeBrokerBootstrapError("trusted checkout Git read failed to run") from exc
    if result.returncode != 0:
        _fail(f"trusted checkout Git read failed rc={result.returncode}")
    if len(result.stdout.encode("utf-8")) > MAX_GIT_OUTPUT or len(result.stderr.encode("utf-8")) > MAX_GIT_OUTPUT:
        _fail("trusted checkout Git read output exceeded limit")
    return result.stdout


def validate_trusted_checkout(checkout: Path) -> str:
    checkout = checkout.resolve()
    if checkout.name != TRUSTED_CHECKOUT_NAME or not checkout.is_dir():
        _fail("unexpected trusted checkout identity")
    top = Path(_git(checkout, "rev-parse", "--show-toplevel").strip()).resolve()
    if top != checkout:
        _fail("trusted checkout top-level drifted")
    if _git(checkout, "config", "--get", "remote.origin.url").strip() != REVIEWED_ORIGIN:
        _fail("trusted checkout origin drifted")
    if _git(checkout, "rev-parse", "--abbrev-ref", "HEAD").strip() != "HEAD":
        _fail("trusted checkout must be detached")
    if _git(checkout, "status", "--porcelain=v1", "--untracked-files=all"):
        _fail("trusted checkout is not clean")
    head = _git(checkout, "rev-parse", "HEAD").strip()
    origin_main = _git(checkout, "rev-parse", "refs/remotes/origin/main").strip()
    if _SHA40_RE.fullmatch(head) is None or _SHA40_RE.fullmatch(origin_main) is None:
        _fail("trusted checkout SHA is malformed")
    if head != origin_main:
        _fail("trusted checkout HEAD does not equal origin/main")
    return head


def _read_source(checkout: Path, relative: Path) -> bytes:
    path = checkout / relative
    try:
        meta = path.lstat()
    except OSError as exc:
        raise RunnerSmokeBrokerBootstrapError(f"source artifact missing: {relative}") from exc
    if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1 or meta.st_size > MAX_ARTIFACT_BYTES:
        _fail(f"source artifact shape drifted: {relative}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise RunnerSmokeBrokerBootstrapError(f"source artifact unreadable: {relative}") from exc
    if len(data) != meta.st_size:
        _fail(f"source artifact changed during read: {relative}")
    return data


def desired_artifact_bytes(checkout: Path) -> tuple[tuple[Path, bytes, int], ...]:
    return tuple(
        (destination, _read_source(checkout, source), mode)
        for source, destination, mode in runtime_artifacts()
    )


def _host_path(host_root: Path, absolute: Path) -> Path:
    if not absolute.is_absolute():
        _fail("host destination must be absolute")
    if host_root == Path("/"):
        return absolute
    return host_root / absolute.relative_to("/")


def _regular_exact(path: Path, expected: bytes, mode: int, *, uid: int, gid: int) -> bool:
    try:
        meta = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise RunnerSmokeBrokerBootstrapError(f"host artifact stat failed: {path}") from exc
    if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:
        return False
    if stat.S_IMODE(meta.st_mode) != mode or meta.st_uid != uid or meta.st_gid != gid:
        return False
    try:
        return path.read_bytes() == expected
    except OSError as exc:
        raise RunnerSmokeBrokerBootstrapError(f"host artifact read failed: {path}") from exc


def _directory_exact(path: Path, mode: int, *, uid: int, gid: int) -> bool:
    try:
        meta = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise RunnerSmokeBrokerBootstrapError(f"host directory stat failed: {path}") from exc
    return (
        stat.S_ISDIR(meta.st_mode)
        and not stat.S_ISLNK(meta.st_mode)
        and stat.S_IMODE(meta.st_mode) == mode
        and meta.st_uid == uid
        and meta.st_gid == gid
    )


def _current_link_exact(path: Path, source_sha: str, *, uid: int, gid: int) -> bool:
    try:
        meta = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise RunnerSmokeBrokerBootstrapError("current symlink stat failed") from exc
    if not stat.S_ISLNK(meta.st_mode) or meta.st_uid != uid or meta.st_gid != gid:
        return False
    try:
        return os.readlink(path) == f"releases/{source_sha}"
    except OSError as exc:
        raise RunnerSmokeBrokerBootstrapError("current symlink read failed") from exc


def _release_tree_has_only_expected(release: Path, destinations: Sequence[Path]) -> bool:
    expected_files = {str(path) for path in destinations}
    expected_dirs = {"ops", "ops/bin", "ops/lib", "ops/lib/deploy_executor"}
    try:
        observed_files: set[str] = set()
        observed_dirs: set[str] = set()
        for root, dirs, files in os.walk(release, topdown=True, followlinks=False):
            base = Path(root)
            for name in dirs:
                rel = str((base / name).relative_to(release))
                observed_dirs.add(rel)
            for name in files:
                rel = str((base / name).relative_to(release))
                observed_files.add(rel)
        return observed_files == expected_files and observed_dirs == expected_dirs
    except OSError as exc:
        raise RunnerSmokeBrokerBootstrapError("release tree inspection failed") from exc


def _filesystem_state(
    checkout: Path,
    source_sha: str,
    *,
    host_root: Path,
    uid: int,
    gid: int,
) -> str:
    release_root = _host_path(host_root, RELEASE_ROOT)
    socket_destination = _host_path(host_root, SOCKET_DESTINATION)
    service_destination = _host_path(host_root, SERVICE_DESTINATION)
    owned_paths = (release_root, socket_destination, service_destination)
    if all(not path.exists() and not path.is_symlink() for path in owned_paths):
        return "ABSENT"

    releases_root = _host_path(host_root, RELEASES_ROOT)
    current_link = _host_path(host_root, CURRENT_LINK)
    release = releases_root / source_sha
    required_dirs = (
        release_root,
        releases_root,
        release,
        release / "ops",
        release / "ops/bin",
        release / "ops/lib",
        release / "ops/lib/deploy_executor",
    )
    if not all(_directory_exact(path, DIRECTORY_MODE, uid=uid, gid=gid) for path in required_dirs):
        return "DRIFT"
    try:
        releases = {entry.name for entry in releases_root.iterdir()}
        roots = {entry.name for entry in release_root.iterdir()}
    except OSError as exc:
        raise RunnerSmokeBrokerBootstrapError("release root inspection failed") from exc
    if releases != {source_sha} or roots != {"releases", "current"}:
        return "DRIFT"
    if not _current_link_exact(current_link, source_sha, uid=uid, gid=gid):
        return "DRIFT"

    desired = desired_artifact_bytes(checkout)
    for relative, data, mode in desired:
        if not _regular_exact(release / relative, data, mode, uid=uid, gid=gid):
            return "DRIFT"
    if not _release_tree_has_only_expected(release, [relative for relative, _, _ in desired]):
        return "DRIFT"
    if not _regular_exact(socket_destination, _read_source(checkout, SOCKET_SOURCE), UNIT_MODE, uid=uid, gid=gid):
        return "DRIFT"
    if not _regular_exact(service_destination, _read_source(checkout, SERVICE_SOURCE), UNIT_MODE, uid=uid, gid=gid):
        return "DRIFT"
    return "EXACT"


def _systemctl_state(action: str, unit: str) -> str:
    if action not in {"is-enabled", "is-active"} or unit != SOCKET_UNIT:
        _fail("unsupported systemctl observation")
    try:
        result = subprocess.run(
            ["/usr/bin/systemctl", action, unit],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            shell=False,
            close_fds=True,
            env=_FIXED_ENV,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise RunnerSmokeBrokerBootstrapError("systemctl observation failed to run") from exc
    if len(result.stdout.encode("utf-8")) > MAX_SYSTEMCTL_OUTPUT or len(result.stderr.encode("utf-8")) > MAX_SYSTEMCTL_OUTPUT:
        _fail("systemctl observation output exceeded limit")
    value = result.stdout.strip()
    allowed = {
        "is-enabled": {"enabled", "disabled", "not-found", "static", "indirect", "masked", "generated"},
        "is-active": {"active", "inactive", "failed", "unknown", "activating", "deactivating"},
    }[action]
    if value not in allowed:
        _fail(f"unexpected systemctl {action} state")
    return value


def observe_bootstrap(
    checkout: Path,
    *,
    host_root: Path = Path("/"),
    uid: int = ROOT_UID,
    gid: int = ROOT_GID,
) -> BootstrapObservation:
    source_sha = validate_trusted_checkout(checkout)
    filesystem_state = _filesystem_state(
        checkout,
        source_sha,
        host_root=host_root,
        uid=uid,
        gid=gid,
    )
    return BootstrapObservation(
        source_sha=source_sha,
        filesystem_state=filesystem_state,
        socket_enabled_state=_systemctl_state("is-enabled", SOCKET_UNIT),
        socket_active_state=_systemctl_state("is-active", SOCKET_UNIT),
    )


def plan_bootstrap(observation: BootstrapObservation) -> BootstrapPlan:
    if not isinstance(observation, BootstrapObservation) or _SHA40_RE.fullmatch(observation.source_sha) is None:
        _fail("bootstrap observation is invalid")
    if (
        observation.filesystem_state == "EXACT"
        and observation.socket_enabled_state == "enabled"
        and observation.socket_active_state == "active"
    ):
        return BootstrapPlan(
            schema=PLAN_SCHEMA,
            decision="ALREADY_EXACT_NO_MUTATION",
            source_sha=observation.source_sha,
            mutations_required=(),
        )
    if (
        observation.filesystem_state == "ABSENT"
        and observation.socket_enabled_state in {"disabled", "not-found"}
        and observation.socket_active_state in {"inactive", "unknown"}
    ):
        return BootstrapPlan(
            schema=PLAN_SCHEMA,
            decision="INSTALL_REQUIRED_EXPLICIT_LIVE",
            source_sha=observation.source_sha,
            mutations_required=MUTATION_SEQUENCE,
        )
    _fail("runner-smoke broker host state is partial, conflicting, or drifted")


def _mkdir_root_owned(path: Path) -> None:
    path.mkdir(mode=DIRECTORY_MODE)
    os.chown(path, ROOT_UID, ROOT_GID)
    os.chmod(path, DIRECTORY_MODE)


def _write_root_owned(path: Path, data: bytes, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, mode)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fchmod(fd, mode)
        os.fchown(fd, ROOT_UID, ROOT_GID)
        os.fsync(fd)
    finally:
        os.close(fd)


def _run_fixed_systemctl(*args: str) -> None:
    allowed = {
        ("daemon-reload",),
        ("enable", "--now", SOCKET_UNIT),
    }
    if tuple(args) not in allowed:
        _fail("unsupported systemctl mutation")
    try:
        result = subprocess.run(
            ["/usr/bin/systemctl", *args],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            shell=False,
            close_fds=True,
            env=_FIXED_ENV,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise RunnerSmokeBrokerBootstrapError("fixed systemctl mutation failed to run") from exc
    if result.returncode != 0:
        _fail(f"fixed systemctl mutation failed rc={result.returncode}")
    if len(result.stdout.encode("utf-8")) > MAX_SYSTEMCTL_OUTPUT or len(result.stderr.encode("utf-8")) > MAX_SYSTEMCTL_OUTPUT:
        _fail("fixed systemctl mutation output exceeded limit")


def _publish_absent_state(checkout: Path, source_sha: str) -> None:
    release_root = RELEASE_ROOT
    releases_root = RELEASES_ROOT
    release = releases_root / source_sha
    _mkdir_root_owned(release_root)
    _mkdir_root_owned(releases_root)
    _mkdir_root_owned(release)
    for relative in (Path("ops"), Path("ops/bin"), Path("ops/lib"), Path("ops/lib/deploy_executor")):
        _mkdir_root_owned(release / relative)
    for relative, data, mode in desired_artifact_bytes(checkout):
        _write_root_owned(release / relative, data, mode)
    os.symlink(f"releases/{source_sha}", CURRENT_LINK)
    os.lchown(CURRENT_LINK, ROOT_UID, ROOT_GID)
    _write_root_owned(SOCKET_DESTINATION, _read_source(checkout, SOCKET_SOURCE), UNIT_MODE)
    _write_root_owned(SERVICE_DESTINATION, _read_source(checkout, SERVICE_SOURCE), UNIT_MODE)
    _run_fixed_systemctl("daemon-reload")
    _run_fixed_systemctl("enable", "--now", SOCKET_UNIT)


def apply_bootstrap(checkout: Path) -> Mapping[str, Any]:
    if os.geteuid() != 0:
        _fail("runner-smoke broker bootstrap requires euid 0")
    observation = observe_bootstrap(checkout)
    plan = plan_bootstrap(observation)
    if plan.decision == "ALREADY_EXACT_NO_MUTATION":
        return {
            "schema": RECEIPT_SCHEMA,
            "result": "ALREADY_EXACT_NO_MUTATION",
            "implementation_issue": IMPLEMENTATION_ISSUE,
            "source_sha": plan.source_sha,
            "mutations_started": False,
            "automatic_retry": False,
            "automatic_cleanup": False,
            "automatic_rollback": False,
        }

    mutation_started = False
    try:
        mutation_started = True
        _publish_absent_state(checkout, plan.source_sha)
        final = observe_bootstrap(checkout)
        if plan_bootstrap(final).decision != "ALREADY_EXACT_NO_MUTATION":
            _fail("post-install broker bootstrap verification did not converge to exact state")
    except Exception as exc:
        if isinstance(exc, RunnerSmokeBrokerBootstrapApplyError):
            raise
        raise RunnerSmokeBrokerBootstrapApplyError(
            "runner-smoke broker bootstrap failed closed",
            mutation_started=mutation_started,
        ) from exc
    return {
        "schema": RECEIPT_SCHEMA,
        "result": "INSTALLED_EXACT",
        "implementation_issue": IMPLEMENTATION_ISSUE,
        "source_sha": plan.source_sha,
        "mutations_started": True,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def failure_receipt(*, mutation_started: bool) -> Mapping[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "result": "FAIL_CLOSED",
        "implementation_issue": IMPLEMENTATION_ISSUE,
        "mutation_state": "UNKNOWN_FAIL_CLOSED" if mutation_started else "NOT_STARTED",
        "mutations_started": mutation_started,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def plan_dict(plan: BootstrapPlan) -> Mapping[str, Any]:
    return asdict(plan)


def receipt_json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"))
