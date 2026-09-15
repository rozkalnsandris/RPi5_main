from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Mapping, Protocol

from .weather_private_bigquery_host_runtime import (
    ACTIVATION_MARKER,
    ACTIVATION_MARKER_MODE,
    HOST_CAPABILITY_ID,
    INSTALL_MUTATION_BUDGET,
    INSTALL_OPERATION_ID,
    INSTALL_ROLLBACK_POLICY,
    INSTALL_TARGET_ALIAS,
    OPERATOR_DESTINATION,
    OPERATOR_MODE,
    OPERATOR_SOURCE,
    ROOT_GID,
    ROOT_UID,
    TRUSTED_CHECKOUT,
    TRUSTED_CHECKOUT_MODE,
    HostInstallObservation,
    build_host_install_plan,
    validate_activation_marker,
)

IMPLEMENTATION_ISSUE = 554
BRIDGE_SCHEMA = "rozkalns-weather.weathernext-private-host-privileged-installer.v1"
RECEIPT_SCHEMA = "rozkalns-weather.weathernext-private-host-install-receipt.v1"
SOURCE_REPOSITORY = "rozkalnsandris/RPi5_main"
SOURCE_REPOSITORY_ID = 1323383044
REVIEWED_ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
MINIMUM_REVIEWED_ANCESTOR = "1fa9ace14aa8b0b7c3c46ac465f1a5093d35d0a7"
BASELINE_RESOLVER_ID = "weathernext.private-host-install-state.v1"
ADAPTER_ID = "weathernext.private-host-installer.v1"
MANAGER_CHECKOUT = TRUSTED_CHECKOUT.parent / "RPi5_main"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")

REQUIRED_EXCLUSIONS = (
    "caller-selected command/path/argv/environment/repository authority",
    "generic root shell or generic sudo authority",
    "package/service/systemd/Docker/network/Cloudflare mutation",
    "credential/ADC/service-account/IAM read or mutation",
    "Google project/API/Analytics Hub/BigQuery action",
    "Weather application staging or private runtime materialization",
    "SQLite/schema/corpus/snapshot mutation",
    "automatic retry/cleanup/rollback/alternate mutation after consume",
)


class WeatherNextPrivateHostInstallerError(RuntimeError):
    pass


@dataclass(frozen=True)
class CanonicalInstallEvidence:
    authorization_issue_number: int
    authorization_issue_id: int
    authorization_created_at: str
    github_server_time: str
    request_id: str
    request_body_sha256: str
    operation_id: str
    target_alias: str
    rpi5_main_sha: str
    queue_issue_number: int
    queue_ready: bool = True
    owner_verified: bool = True
    app_authored: bool = False
    authorization_ttl_valid: bool = True
    authorization_body_unchanged: bool = True
    authorization_replay_available: bool = True
    source_exact_main: bool = True
    source_merged_reachable: bool = True
    source_ci_success: bool = True
    rollback_policy: str = INSTALL_ROLLBACK_POLICY


@dataclass(frozen=True)
class InstallReceipt:
    schema: str
    authorization_issue_number: int
    request_id: str
    rpi5_main_sha: str
    operation_id: str
    target_alias: str
    mutations_executed: tuple[str, ...]
    authorization_consumed: bool
    trusted_checkout_exact: bool
    operator_exact: bool
    activation_marker_exact: bool
    rollback_policy: str = INSTALL_ROLLBACK_POLICY
    automatic_retry: bool = False
    automatic_cleanup: bool = False
    automatic_rollback: bool = False
    production_mutation_started: bool = True


class ReplayAuthority(Protocol):
    def consume(self, request_id: str) -> None: ...
    def mark_succeeded(self, request_id: str) -> None: ...


class FixedInstallBackend(Protocol):
    def observe(self, exact_source_sha: str) -> HostInstallObservation: ...
    def fetch_origin_main(self, exact_source_sha: str) -> None: ...
    def create_trusted_checkout(self, exact_source_sha: str) -> None: ...
    def install_operator(self, exact_source_sha: str) -> None: ...
    def write_activation_marker(self, exact_source_sha: str) -> None: ...
    def verify_exact(self, exact_source_sha: str) -> HostInstallObservation: ...


def _fail(message: str) -> None:
    raise WeatherNextPrivateHostInstallerError(message)


def _run_git(checkout: Path, *args: str, mutation: bool = False) -> subprocess.CompletedProcess[str]:
    read_ops = {"rev-parse", "symbolic-ref", "status", "remote", "merge-base"}
    mutation_ops = {"fetch", "worktree"}
    fixed_checkouts = (MANAGER_CHECKOUT, TRUSTED_CHECKOUT)
    if checkout not in fixed_checkouts:
        _fail("git checkout escaped fixed allowlist")
    if not args:
        _fail("git operation is empty")
    if mutation:
        if args[0] not in mutation_ops:
            _fail("git mutation escaped reviewed allowlist")
    elif args[0] not in read_ops:
        _fail("git read escaped reviewed allowlist")
    argv = (
        "/usr/bin/git",
        "-c",
        f"safe.directory={checkout}",
        "--no-optional-locks",
        "-C",
        str(checkout),
        *args,
    )
    try:
        result = subprocess.run(
            argv,
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
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise WeatherNextPrivateHostInstallerError("fixed git operation failed to run") from exc
    if len(result.stdout.encode("utf-8")) > 65536 or len(result.stderr.encode("utf-8")) > 65536:
        _fail("fixed git operation output exceeded limit")
    return result


def _git_success(checkout: Path, *args: str, mutation: bool = False) -> str:
    result = _run_git(checkout, *args, mutation=mutation)
    if result.returncode != 0:
        _fail("fixed git operation failed closed")
    return result.stdout.strip()


def _meta(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise WeatherNextPrivateHostInstallerError(f"lstat failed: {path}") from exc


def _require_dir(
    path: Path,
    *,
    uid: int | None = None,
    gid: int | None = None,
    mode: int | None = None,
) -> os.stat_result:
    meta = _meta(path)
    if meta is None or not stat.S_ISDIR(meta.st_mode):
        _fail(f"required fixed directory is unavailable: {path}")
    if uid is not None and meta.st_uid != uid:
        _fail(f"required fixed directory owner drifted: {path}")
    if gid is not None and meta.st_gid != gid:
        _fail(f"required fixed directory group drifted: {path}")
    if mode is not None and stat.S_IMODE(meta.st_mode) != mode:
        _fail(f"required fixed directory mode drifted: {path}")
    return meta


def _require_regular(
    path: Path,
    *,
    uid: int | None = None,
    gid: int | None = None,
    mode: int | None = None,
) -> os.stat_result:
    meta = _meta(path)
    if meta is None or not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:
        _fail(f"required fixed file is not a single-link regular file: {path}")
    if uid is not None and meta.st_uid != uid:
        _fail(f"required fixed file owner drifted: {path}")
    if gid is not None and meta.st_gid != gid:
        _fail(f"required fixed file group drifted: {path}")
    if mode is not None and stat.S_IMODE(meta.st_mode) != mode:
        _fail(f"required fixed file mode drifted: {path}")
    return meta


def _read_bounded(path: Path) -> bytes:
    before = _require_regular(path)
    if not 0 <= before.st_size <= MAX_SOURCE_BYTES:
        _fail("reviewed source file exceeds fixed size limit")
    if not hasattr(os, "O_NOFOLLOW"):
        _fail("O_NOFOLLOW is required")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            _fail("reviewed source changed before descriptor validation")
        chunks: list[bytes] = []
        remaining = MAX_SOURCE_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_SOURCE_BYTES or len(raw) != opened.st_size:
            _fail("reviewed source changed during bounded read")
        after = path.lstat()
        if (after.st_dev, after.st_ino, after.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            _fail("reviewed source path changed during bounded read")
        return raw
    finally:
        os.close(fd)


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class PosixFixedInstallBackend:
    """Root-side backend for only the four #552 install mutation categories."""

    def _require_root(self) -> None:
        if os.geteuid() != 0:
            _fail("private host privileged installer requires root identity")

    def _validate_manager(self) -> None:
        _require_dir(MANAGER_CHECKOUT)
        if _git_success(MANAGER_CHECKOUT, "remote", "get-url", "origin") != REVIEWED_ORIGIN:
            _fail("manager checkout origin drifted")

    def _checkout_exact(self, exact_source_sha: str) -> bool:
        try:
            _require_dir(
                TRUSTED_CHECKOUT,
                uid=ROOT_UID,
                gid=ROOT_GID,
                mode=TRUSTED_CHECKOUT_MODE,
            )
            if _git_success(TRUSTED_CHECKOUT, "rev-parse", "HEAD") != exact_source_sha:
                return False
            detached = _run_git(TRUSTED_CHECKOUT, "symbolic-ref", "-q", "HEAD")
            if detached.returncode != 1 or detached.stdout or detached.stderr:
                return False
            if _git_success(
                TRUSTED_CHECKOUT,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ):
                return False
            if _git_success(TRUSTED_CHECKOUT, "remote", "get-url", "origin") != REVIEWED_ORIGIN:
                return False
            for relative in (
                OPERATOR_SOURCE,
                Path("ops/lib/deploy_executor/weather_private_bigquery_host_runtime.py"),
                Path("ops/lib/deploy_executor/weather_private_bigquery_host_bindings.py"),
                Path("ops/deploy/weather-private-bigquery-host-runtime.json"),
            ):
                _require_regular(TRUSTED_CHECKOUT / relative)
            return True
        except WeatherNextPrivateHostInstallerError:
            return False

    def _operator_exact(self, exact_source_sha: str) -> bool:
        try:
            if not self._checkout_exact(exact_source_sha):
                return False
            _require_regular(
                OPERATOR_DESTINATION,
                uid=ROOT_UID,
                gid=ROOT_GID,
                mode=OPERATOR_MODE,
            )
            return _read_bounded(OPERATOR_DESTINATION) == _read_bounded(
                TRUSTED_CHECKOUT / OPERATOR_SOURCE
            )
        except WeatherNextPrivateHostInstallerError:
            return False

    def _marker_exact(self, exact_source_sha: str) -> bool:
        try:
            _require_regular(
                ACTIVATION_MARKER,
                uid=ROOT_UID,
                gid=ROOT_GID,
                mode=ACTIVATION_MARKER_MODE,
            )
            value = json.loads(_read_bounded(ACTIVATION_MARKER).decode("utf-8", "strict"))
            validate_activation_marker(value, exact_rpi5_main_sha=exact_source_sha)
            return True
        except (
            WeatherNextPrivateHostInstallerError,
            UnicodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ):
            return False

    def observe(self, exact_source_sha: str) -> HostInstallObservation:
        if type(exact_source_sha) is not str or _SHA40_RE.fullmatch(exact_source_sha) is None:
            _fail("exact source SHA is invalid")
        checkout = "ABSENT" if _meta(TRUSTED_CHECKOUT) is None else (
            "EXACT" if self._checkout_exact(exact_source_sha) else "CONFLICT"
        )
        operator = "ABSENT" if _meta(OPERATOR_DESTINATION) is None else (
            "EXACT" if self._operator_exact(exact_source_sha) else "CONFLICT"
        )
        marker = "ABSENT" if _meta(ACTIVATION_MARKER) is None else (
            "EXACT" if self._marker_exact(exact_source_sha) else "CONFLICT"
        )
        return HostInstallObservation(
            trusted_checkout_state=checkout,
            operator_state=operator,
            activation_marker_state=marker,
        )

    def fetch_origin_main(self, exact_source_sha: str) -> None:
        self._require_root()
        self._validate_manager()
        if _meta(TRUSTED_CHECKOUT) is not None:
            _fail("trusted checkout must be absent before fetch/worktree bootstrap")
        _git_success(MANAGER_CHECKOUT, "fetch", "origin", "main", mutation=True)
        if _git_success(MANAGER_CHECKOUT, "rev-parse", "refs/remotes/origin/main") != exact_source_sha:
            _fail("fetched origin/main does not equal authorized source SHA")
        ancestor = _run_git(
            MANAGER_CHECKOUT,
            "merge-base",
            "--is-ancestor",
            MINIMUM_REVIEWED_ANCESTOR,
            exact_source_sha,
        )
        if ancestor.returncode != 0:
            _fail("authorized source is outside reviewed installer ancestry")

    def create_trusted_checkout(self, exact_source_sha: str) -> None:
        self._require_root()
        if _meta(TRUSTED_CHECKOUT) is not None:
            _fail("trusted checkout destination is not absent")
        _git_success(
            MANAGER_CHECKOUT,
            "worktree",
            "add",
            "--detach",
            str(TRUSTED_CHECKOUT),
            exact_source_sha,
            mutation=True,
        )
        os.chown(TRUSTED_CHECKOUT, ROOT_UID, ROOT_GID)
        os.chmod(TRUSTED_CHECKOUT, TRUSTED_CHECKOUT_MODE)
        if not self._checkout_exact(exact_source_sha):
            _fail("trusted checkout postcondition failed")

    def install_operator(self, exact_source_sha: str) -> None:
        self._require_root()
        if not self._checkout_exact(exact_source_sha):
            _fail("trusted checkout is not exact before operator install")
        if _meta(OPERATOR_DESTINATION) is not None:
            _fail("operator destination already exists; overwrite is forbidden")
        raw = _read_bounded(TRUSTED_CHECKOUT / OPERATOR_SOURCE)
        _require_dir(OPERATOR_DESTINATION.parent)
        fd = os.open(
            OPERATOR_DESTINATION,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        try:
            offset = 0
            while offset < len(raw):
                written = os.write(fd, raw[offset:])
                if written <= 0:
                    _fail("operator install write failed closed")
                offset += written
            os.fchmod(fd, OPERATOR_MODE)
            os.fchown(fd, ROOT_UID, ROOT_GID)
            os.fsync(fd)
        finally:
            os.close(fd)
        _fsync_directory(OPERATOR_DESTINATION.parent)
        if not self._operator_exact(exact_source_sha):
            _fail("installed operator postcondition failed")

    def write_activation_marker(self, exact_source_sha: str) -> None:
        self._require_root()
        if not self._operator_exact(exact_source_sha):
            _fail("operator is not exact before activation marker publication")
        if _meta(ACTIVATION_MARKER) is not None:
            _fail("activation marker already exists; overwrite is forbidden")
        parent = ACTIVATION_MARKER.parent
        if _meta(parent) is None:
            _require_dir(parent.parent)
            os.mkdir(parent, 0o755)
            os.chown(parent, ROOT_UID, ROOT_GID)
            _fsync_directory(parent.parent)
        else:
            _require_dir(parent, uid=ROOT_UID, gid=ROOT_GID, mode=0o755)
        value = {
            "schema": "rozkalns-weather.weathernext-private-host-capability.v1",
            "host_capability_id": HOST_CAPABILITY_ID,
            "operation_id": INSTALL_OPERATION_ID,
            "target_alias": "rpi5",
            "rpi5_main_source_sha": exact_source_sha,
            "trusted_checkout": str(TRUSTED_CHECKOUT),
            "operator_destination": str(OPERATOR_DESTINATION),
            "execution_enabled": True,
        }
        validate_activation_marker(value, exact_rpi5_main_sha=exact_source_sha)
        raw = (
            json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            + "\n"
        ).encode("utf-8")
        fd = os.open(
            ACTIVATION_MARKER,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        try:
            offset = 0
            while offset < len(raw):
                written = os.write(fd, raw[offset:])
                if written <= 0:
                    _fail("activation marker write failed closed")
                offset += written
            os.fchmod(fd, ACTIVATION_MARKER_MODE)
            os.fchown(fd, ROOT_UID, ROOT_GID)
            os.fsync(fd)
        finally:
            os.close(fd)
        _fsync_directory(parent)
        if not self._marker_exact(exact_source_sha):
            _fail("activation marker postcondition failed")

    def verify_exact(self, exact_source_sha: str) -> HostInstallObservation:
        observation = self.observe(exact_source_sha)
        expected = HostInstallObservation(
            trusted_checkout_state="EXACT",
            operator_state="EXACT",
            activation_marker_state="EXACT",
        )
        if observation != expected:
            _fail("private host install final identity is not exact")
        return observation


def _validate_evidence(evidence: CanonicalInstallEvidence) -> None:
    if type(evidence) is not CanonicalInstallEvidence:
        raise TypeError("private host install requires canonical evidence")
    if evidence.operation_id != INSTALL_OPERATION_ID or evidence.target_alias != INSTALL_TARGET_ALIAS:
        _fail("canonical install operation or target drifted")
    if type(evidence.rpi5_main_sha) is not str or _SHA40_RE.fullmatch(evidence.rpi5_main_sha) is None:
        _fail("canonical RPi5_main SHA is invalid")
    if evidence.rollback_policy != INSTALL_ROLLBACK_POLICY:
        _fail("canonical rollback policy drifted")
    for field in (
        "queue_ready",
        "owner_verified",
        "authorization_ttl_valid",
        "authorization_body_unchanged",
        "authorization_replay_available",
        "source_exact_main",
        "source_merged_reachable",
        "source_ci_success",
    ):
        if getattr(evidence, field) is not True:
            _fail(f"canonical proof failed: {field}")
    if evidence.app_authored is not False:
        _fail("app-authored LIVE-AUTH is forbidden")


def apply_install(
    evidence: CanonicalInstallEvidence,
    *,
    replay: ReplayAuthority,
    backend: FixedInstallBackend,
) -> InstallReceipt:
    """Apply only the mechanically derived #552 plan after canonical revalidation."""

    _validate_evidence(evidence)
    observation = backend.observe(evidence.rpi5_main_sha)
    plan = build_host_install_plan(
        observation,
        exact_rpi5_main_sha=evidence.rpi5_main_sha,
    )
    if plan.operation_id != INSTALL_OPERATION_ID or plan.target_alias != INSTALL_TARGET_ALIAS:
        _fail("derived install plan identity drifted")
    if plan.mutation_budget != INSTALL_MUTATION_BUDGET or plan.rollback_policy != "NONE":
        _fail("derived install plan budget or rollback drifted")

    if plan.decision == "ALREADY_EXACT":
        backend.verify_exact(evidence.rpi5_main_sha)
        return InstallReceipt(
            schema=RECEIPT_SCHEMA,
            authorization_issue_number=evidence.authorization_issue_number,
            request_id=evidence.request_id,
            rpi5_main_sha=evidence.rpi5_main_sha,
            operation_id=INSTALL_OPERATION_ID,
            target_alias=INSTALL_TARGET_ALIAS,
            mutations_executed=(),
            authorization_consumed=False,
            trusted_checkout_exact=True,
            operator_exact=True,
            activation_marker_exact=True,
            production_mutation_started=False,
        )

    replay.consume(evidence.request_id)
    executed: list[str] = []
    for mutation in plan.mutations_required:
        if mutation == "git.weathernext-private-host-checkout-fetch":
            backend.fetch_origin_main(evidence.rpi5_main_sha)
        elif mutation == "git.weathernext-private-host-checkout-worktree-add":
            backend.create_trusted_checkout(evidence.rpi5_main_sha)
        elif mutation == "filesystem.weathernext-private-host-operator-install":
            backend.install_operator(evidence.rpi5_main_sha)
        elif mutation == "filesystem.weathernext-private-host-activation-marker-write":
            backend.write_activation_marker(evidence.rpi5_main_sha)
        else:
            _fail("derived install plan introduced an unknown mutation")
        executed.append(mutation)

    backend.verify_exact(evidence.rpi5_main_sha)
    replay.mark_succeeded(evidence.request_id)
    return InstallReceipt(
        schema=RECEIPT_SCHEMA,
        authorization_issue_number=evidence.authorization_issue_number,
        request_id=evidence.request_id,
        rpi5_main_sha=evidence.rpi5_main_sha,
        operation_id=INSTALL_OPERATION_ID,
        target_alias=INSTALL_TARGET_ALIAS,
        mutations_executed=tuple(executed),
        authorization_consumed=True,
        trusted_checkout_exact=True,
        operator_exact=True,
        activation_marker_exact=True,
    )


def public_receipt(receipt: InstallReceipt) -> Mapping[str, Any]:
    if type(receipt) is not InstallReceipt:
        _fail("private host install receipt type is invalid")
    return asdict(receipt)


def source_readiness() -> Mapping[str, Any]:
    return {
        "schema": BRIDGE_SCHEMA,
        "implementation_issue": IMPLEMENTATION_ISSUE,
        "host_capability_id": HOST_CAPABILITY_ID,
        "install_operation_id": INSTALL_OPERATION_ID,
        "install_target_alias": INSTALL_TARGET_ALIAS,
        "adapter_id": ADAPTER_ID,
        "baseline_resolver_id": BASELINE_RESOLVER_ID,
        "caller_authority": ("authorization_issue_number",),
        "privileged_installer_core_implemented": True,
        "fixed_posix_backend_implemented": True,
        "mutation_budget": INSTALL_MUTATION_BUDGET,
        "rollback_policy": INSTALL_ROLLBACK_POLICY,
        "trusted_checkout": str(TRUSTED_CHECKOUT),
        "operator_destination": str(OPERATOR_DESTINATION),
        "activation_marker": str(ACTIVATION_MARKER),
        "global_executor_execution_enabled": False,
        "runtime_activation_enabled": False,
        "privileged_boundary_installed": False,
        "privileged_dispatch_enabled": False,
        "source_merge_authorizes_live": False,
        "production_mutation_started": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }
