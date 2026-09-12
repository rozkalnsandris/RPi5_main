from __future__ import annotations

from dataclasses import asdict, dataclass
import grp
import hashlib
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
from typing import Any, Mapping, Protocol

OPERATION_ID = "hermes-deals.runner-smoke-audit.v1"
LIVE_GATE_ID = "hermes-deals.runner-smoke-audit.install.v1"
INSTALL_TARGET_ALIAS = "hermes-deals-runner-smoke-audit-install"
CANARY_TARGET_ALIAS = "hermes-deals-runner-smoke-audit"
SOURCE_REPOSITORY = "rozkalnsandris/hermes-deals"
SOURCE_REPOSITORY_ID = 1317143994
SOURCE_SHA = "0e3b834f155cef7f9e964ddf02228c6a7ad1950c"
OWNER_NUMERIC_ID = 277435981
EXECUTION_ACCOUNT = "hermes-deals-audit-canary"
EXECUTION_GROUP = "hermes-deals-audit-canary"
EXECUTION_HOME = "/nonexistent"
EXECUTION_SHELL = "/usr/sbin/nologin"
HELPER_SOURCE_RELATIVE = Path("ops/bin/hermes-deals-runner-smoke-audit")
REGISTRATION_SOURCE_RELATIVE = Path("ops/deploy/hermes-deals-runner-smoke-audit-registration.json")
HELPER_DESTINATION = Path("/usr/local/libexec/rozkalns-deploy/hermes-deals-runner-smoke-audit")
REGISTRATION_DESTINATION = Path("/etc/rozkalns-deploy/hermes-deals-runner-smoke-audit.json")
HELPER_SHA256 = "fc8ccc8a2179c23670d28bbe166e45f85769b8bd13c319e423f56c4f65b17bd4"
REGISTRATION_SHA256 = "3bc7771d8480ac3a5a5de6ab7f0eb6710cf3aaa458c8a60eaffb5c8d8aaf5c10"
HELPER_MODE = 0o755
REGISTRATION_MODE = 0o644
ROOT_UID = 0
ROOT_GID = 0
LIVE_ENVELOPE_SCHEMA = "rozkalns.hermes-deals.runner-smoke-install-live-envelope.v1"
PLAN_SCHEMA = "rozkalns.hermes-deals.runner-smoke-install-plan.v2"
APPLY_RECEIPT_SCHEMA = "rozkalns.hermes-deals.runner-smoke-install-apply-receipt.v1"
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RunnerSmokeInstallError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise RunnerSmokeInstallError(message)


@dataclass(frozen=True)
class InstallObservation:
    execution_identity_state: str
    helper_destination_state: str
    registration_destination_state: str


@dataclass(frozen=True)
class InstallPlan:
    schema: str
    decision: str
    operation_id: str
    live_gate_id: str
    target_alias: str
    source_repository: str
    source_sha: str
    execution_identity_state: str
    helper_destination_state: str
    registration_destination_state: str
    mutations_required: tuple[str, ...]
    helper_execution_allowed: bool = False
    host_write_allowed: bool = False
    live_authority_consumed: bool = False


@dataclass(frozen=True)
class ApplyReceipt:
    schema: str
    result: str
    authorization_issue_number: int
    operation_id: str
    live_gate_id: str
    target_alias: str
    source_repository: str
    source_sha: str
    rpi5_main_sha: str
    mutations_started: bool
    authorization_consumed: bool
    helper_invoked: bool = False
    rollback_policy: str = "NONE"
    automatic_retry: bool = False
    automatic_cleanup: bool = False
    automatic_rollback: bool = False


class AuthorizationConsumer(Protocol):
    def consume(self, *, authorization_issue_number: int, body_sha256: str) -> None: ...


class FixedInstallBackend(Protocol):
    def observe(self) -> InstallObservation: ...
    def ensure_identity(self) -> None: ...
    def install_helper(self) -> None: ...
    def install_registration(self) -> None: ...
    def verify_exact_state(self) -> InstallObservation: ...


def source_readiness() -> Mapping[str, Any]:
    return {
        "schema": PLAN_SCHEMA,
        "implementation_issue": 476,
        "operation_id": OPERATION_ID,
        "live_gate_id": LIVE_GATE_ID,
        "install_target_alias": INSTALL_TARGET_ALIAS,
        "source_repository": SOURCE_REPOSITORY,
        "source_sha": SOURCE_SHA,
        "execution_identity": EXECUTION_ACCOUNT,
        "apply_implemented": True,
        "external_apply_entrypoint_enabled": False,
        "global_executor_execution_enabled": False,
        "runtime_live_authority": False,
        "caller_authority": ("authorization_issue_number",),
        "caller_command_allowed": False,
        "caller_path_allowed": False,
        "caller_argv_allowed": False,
        "caller_environment_allowed": False,
        "generic_shell_allowed": False,
        "generic_sudo_allowed": False,
        "helper_invocation_allowed": False,
        "rollback_policy": "NONE",
        "automatic_retry_after_mutation_start": False,
        "automatic_cleanup_after_mutation_start": False,
        "automatic_rollback_after_mutation_start": False,
        "alternate_mutation_path_after_mutation_start": False,
    }


def _state(value: Any, field: str) -> str:
    if value not in {"ABSENT", "EXACT"}:
        _fail(f"{field} is conflicting or unknown")
    return str(value)


def build_plan(evidence: Mapping[str, Any]) -> InstallPlan:
    required = {
        "rpi5_main_sha",
        "rpi5_main_merged_reachable",
        "rpi5_main_ci_success",
        "hermes_source_sha",
        "hermes_source_merged_reachable",
        "hermes_source_ci_success",
        "execution_identity_state",
        "helper_destination_state",
        "registration_destination_state",
    }
    if set(evidence) != required:
        _fail("install PLAN evidence field drift")
    rpi_sha = evidence["rpi5_main_sha"]
    if type(rpi_sha) is not str or _SHA40_RE.fullmatch(rpi_sha) is None:
        _fail("RPi5_main SHA is invalid")
    if evidence["hermes_source_sha"] != SOURCE_SHA:
        _fail("Hermes source SHA does not match reviewed runner-smoke source")
    for field in (
        "rpi5_main_merged_reachable",
        "rpi5_main_ci_success",
        "hermes_source_merged_reachable",
        "hermes_source_ci_success",
    ):
        if evidence[field] is not True:
            _fail(f"required source/CI evidence failed: {field}")
    identity_state = _state(evidence["execution_identity_state"], "execution identity state")
    helper_state = _state(evidence["helper_destination_state"], "helper destination state")
    registration_state = _state(evidence["registration_destination_state"], "registration destination state")
    mutations = []
    if identity_state == "ABSENT":
        mutations.extend(("create_exact_system_group", "create_exact_system_user"))
    if helper_state == "ABSENT":
        mutations.append("install_exact_helper")
    if registration_state == "ABSENT":
        mutations.append("install_exact_registration")
    return InstallPlan(
        schema=PLAN_SCHEMA,
        decision="SOURCE_PLAN_READY",
        operation_id=OPERATION_ID,
        live_gate_id=LIVE_GATE_ID,
        target_alias=INSTALL_TARGET_ALIAS,
        source_repository=SOURCE_REPOSITORY,
        source_sha=SOURCE_SHA,
        execution_identity_state=identity_state,
        helper_destination_state=helper_state,
        registration_destination_state=registration_state,
        mutations_required=tuple(mutations),
    )


def validate_live_envelope(envelope: Mapping[str, Any]) -> None:
    required = {
        "schema",
        "authorization_issue_number",
        "owner_numeric_id",
        "operation_id",
        "live_gate_id",
        "target_alias",
        "source_repository",
        "source_repository_id",
        "source_sha",
        "rpi5_main_sha",
        "rpi5_main_merged_reachable",
        "rpi5_main_ci_success",
        "hermes_source_merged_reachable",
        "hermes_source_ci_success",
        "helper_sha256",
        "registration_sha256",
        "request_body_sha256",
        "identical_body_refetch",
        "ttl_valid",
        "replay_available",
        "live_authorized",
        "rollback_policy",
    }
    if set(envelope) != required:
        _fail("LIVE envelope field drift")
    if envelope["schema"] != LIVE_ENVELOPE_SCHEMA:
        _fail("LIVE envelope schema drift")
    if type(envelope["authorization_issue_number"]) is not int or envelope["authorization_issue_number"] <= 0:
        _fail("authorization issue number invalid")
    exact = {
        "owner_numeric_id": OWNER_NUMERIC_ID,
        "operation_id": OPERATION_ID,
        "live_gate_id": LIVE_GATE_ID,
        "target_alias": INSTALL_TARGET_ALIAS,
        "source_repository": SOURCE_REPOSITORY,
        "source_repository_id": SOURCE_REPOSITORY_ID,
        "source_sha": SOURCE_SHA,
        "helper_sha256": HELPER_SHA256,
        "registration_sha256": REGISTRATION_SHA256,
        "rollback_policy": "NONE",
    }
    for field, expected in exact.items():
        if envelope[field] != expected:
            _fail(f"LIVE envelope identity drift: {field}")
    if type(envelope["rpi5_main_sha"]) is not str or _SHA40_RE.fullmatch(envelope["rpi5_main_sha"]) is None:
        _fail("LIVE envelope RPi5_main SHA invalid")
    if type(envelope["request_body_sha256"]) is not str or _SHA256_RE.fullmatch(envelope["request_body_sha256"]) is None:
        _fail("LIVE envelope body hash invalid")
    for field in (
        "rpi5_main_merged_reachable",
        "rpi5_main_ci_success",
        "hermes_source_merged_reachable",
        "hermes_source_ci_success",
        "identical_body_refetch",
        "ttl_valid",
        "replay_available",
        "live_authorized",
    ):
        if envelope[field] is not True:
            _fail(f"LIVE envelope required proof failed: {field}")


def _plan_evidence(envelope: Mapping[str, Any], observation: InstallObservation) -> Mapping[str, Any]:
    return {
        "rpi5_main_sha": envelope["rpi5_main_sha"],
        "rpi5_main_merged_reachable": envelope["rpi5_main_merged_reachable"],
        "rpi5_main_ci_success": envelope["rpi5_main_ci_success"],
        "hermes_source_sha": envelope["source_sha"],
        "hermes_source_merged_reachable": envelope["hermes_source_merged_reachable"],
        "hermes_source_ci_success": envelope["hermes_source_ci_success"],
        "execution_identity_state": observation.execution_identity_state,
        "helper_destination_state": observation.helper_destination_state,
        "registration_destination_state": observation.registration_destination_state,
    }


def apply_install(
    envelope: Mapping[str, Any],
    *,
    authorization_consumer: AuthorizationConsumer,
    backend: FixedInstallBackend,
) -> ApplyReceipt:
    validate_live_envelope(envelope)
    observation = backend.observe()
    plan = build_plan(_plan_evidence(envelope, observation))
    if not plan.mutations_required:
        verified = backend.verify_exact_state()
        if verified != InstallObservation("EXACT", "EXACT", "EXACT"):
            _fail("idempotent exact-state verification failed")
        return ApplyReceipt(
            schema=APPLY_RECEIPT_SCHEMA,
            result="ALREADY_EXACT_NO_MUTATION",
            authorization_issue_number=envelope["authorization_issue_number"],
            operation_id=OPERATION_ID,
            live_gate_id=LIVE_GATE_ID,
            target_alias=INSTALL_TARGET_ALIAS,
            source_repository=SOURCE_REPOSITORY,
            source_sha=SOURCE_SHA,
            rpi5_main_sha=envelope["rpi5_main_sha"],
            mutations_started=False,
            authorization_consumed=False,
        )

    authorization_consumer.consume(
        authorization_issue_number=envelope["authorization_issue_number"],
        body_sha256=envelope["request_body_sha256"],
    )
    # No retry, cleanup, rollback or alternate mutation path exists below this point.
    if plan.execution_identity_state == "ABSENT":
        backend.ensure_identity()
    if plan.helper_destination_state == "ABSENT":
        backend.install_helper()
    if plan.registration_destination_state == "ABSENT":
        backend.install_registration()
    verified = backend.verify_exact_state()
    if verified != InstallObservation("EXACT", "EXACT", "EXACT"):
        _fail("post-install exact-state verification failed")
    return ApplyReceipt(
        schema=APPLY_RECEIPT_SCHEMA,
        result="INSTALLED_EXACT",
        authorization_issue_number=envelope["authorization_issue_number"],
        operation_id=OPERATION_ID,
        live_gate_id=LIVE_GATE_ID,
        target_alias=INSTALL_TARGET_ALIAS,
        source_repository=SOURCE_REPOSITORY,
        source_sha=SOURCE_SHA,
        rpi5_main_sha=envelope["rpi5_main_sha"],
        mutations_started=True,
        authorization_consumed=True,
    )


class PosixFixedInstallBackend:
    """Concrete fixed-path backend for a later separately authorized LIVE wrapper.

    The backend has no caller-selected command/path/argv/environment surface. It is
    intentionally not connected to a CLI or the globally disabled executor in #476.
    """

    def __init__(self) -> None:
        self._source_root = Path(__file__).resolve().parents[3]

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _artifact_state(path: Path, *, mode: int, sha256: str) -> str:
        try:
            meta = path.lstat()
        except FileNotFoundError:
            return "ABSENT"
        except OSError:
            return "CONFLICT"
        if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:
            return "CONFLICT"
        if meta.st_uid != ROOT_UID or meta.st_gid != ROOT_GID or stat.S_IMODE(meta.st_mode) != mode:
            return "CONFLICT"
        try:
            return "EXACT" if PosixFixedInstallBackend._sha256(path) == sha256 else "CONFLICT"
        except OSError:
            return "CONFLICT"

    @staticmethod
    def _identity_state() -> str:
        try:
            account = pwd.getpwnam(EXECUTION_ACCOUNT)
        except KeyError:
            account = None
        try:
            group = grp.getgrnam(EXECUTION_GROUP)
        except KeyError:
            group = None
        if account is None and group is None:
            return "ABSENT"
        if account is None or group is None:
            return "CONFLICT"
        if account.pw_uid == 0 or account.pw_gid == ROOT_GID or group.gr_gid == ROOT_GID:
            return "CONFLICT"
        if account.pw_gid != group.gr_gid:
            return "CONFLICT"
        if account.pw_dir != EXECUTION_HOME or account.pw_shell != EXECUTION_SHELL:
            return "CONFLICT"
        try:
            docker_group = grp.getgrnam("docker")
        except KeyError:
            docker_group = None
        if docker_group is not None and account.pw_gid == docker_group.gr_gid:
            return "CONFLICT"
        for item in grp.getgrall():
            if EXECUTION_ACCOUNT in item.gr_mem:
                return "CONFLICT"
        return "EXACT"

    def observe(self) -> InstallObservation:
        return InstallObservation(
            execution_identity_state=self._identity_state(),
            helper_destination_state=self._artifact_state(
                HELPER_DESTINATION, mode=HELPER_MODE, sha256=HELPER_SHA256
            ),
            registration_destination_state=self._artifact_state(
                REGISTRATION_DESTINATION, mode=REGISTRATION_MODE, sha256=REGISTRATION_SHA256
            ),
        )

    @staticmethod
    def _run_account_tool(argv: tuple[str, ...]) -> None:
        allowed = {
            (
                "/usr/sbin/groupadd", "--system", EXECUTION_GROUP
            ),
            (
                "/usr/sbin/useradd", "--system", "--gid", EXECUTION_GROUP,
                "--home-dir", EXECUTION_HOME, "--no-create-home",
                "--shell", EXECUTION_SHELL, EXECUTION_ACCOUNT
            ),
        }
        if argv not in allowed:
            _fail("account mutation escaped the fixed runner-smoke envelope")
        try:
            result = subprocess.run(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="strict",
                env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
                shell=False,
                close_fds=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
            raise RunnerSmokeInstallError("fixed account mutation failed to run") from exc
        if result.returncode != 0:
            _fail("fixed account mutation failed closed")

    def ensure_identity(self) -> None:
        if self._identity_state() != "ABSENT":
            _fail("identity create requires exact ABSENT baseline")
        self._run_account_tool(("/usr/sbin/groupadd", "--system", EXECUTION_GROUP))
        self._run_account_tool((
            "/usr/sbin/useradd", "--system", "--gid", EXECUTION_GROUP,
            "--home-dir", EXECUTION_HOME, "--no-create-home",
            "--shell", EXECUTION_SHELL, EXECUTION_ACCOUNT
        ))
        if self._identity_state() != "EXACT":
            _fail("dedicated execution identity postcondition failed")

    def _source_artifact(self, relative: Path, expected_sha256: str) -> bytes:
        source = self._source_root / relative
        meta = source.lstat()
        if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1 or meta.st_size > 2 * 1024 * 1024:
            _fail("reviewed source artifact shape drifted")
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            _fail("reviewed source artifact identity drifted")
        return raw

    @staticmethod
    def _ensure_fixed_parent(parent: Path) -> None:
        if parent == HELPER_DESTINATION.parent:
            grandparent = parent.parent
            if not grandparent.exists():
                _fail("fixed helper grandparent is unavailable")
        elif parent == REGISTRATION_DESTINATION.parent:
            grandparent = parent.parent
            if not grandparent.exists():
                _fail("fixed registration grandparent is unavailable")
        else:
            _fail("parent path escaped the fixed install surface")
        try:
            meta = parent.lstat()
        except FileNotFoundError:
            os.mkdir(parent, 0o755)
            os.chown(parent, ROOT_UID, ROOT_GID)
            meta = parent.lstat()
        if not stat.S_ISDIR(meta.st_mode) or meta.st_uid != ROOT_UID or meta.st_gid != ROOT_GID:
            _fail("fixed install parent ownership/type drifted")
        if stat.S_IMODE(meta.st_mode) != 0o755:
            _fail("fixed install parent mode drifted")

    @staticmethod
    def _install_bytes(destination: Path, raw: bytes, *, mode: int) -> None:
        PosixFixedInstallBackend._ensure_fixed_parent(destination.parent)
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            offset = 0
            while offset < len(raw):
                offset += os.write(fd, raw[offset:])
            os.fchown(fd, ROOT_UID, ROOT_GID)
            os.fchmod(fd, mode)
            os.fsync(fd)
        finally:
            os.close(fd)

    def install_helper(self) -> None:
        if self._artifact_state(HELPER_DESTINATION, mode=HELPER_MODE, sha256=HELPER_SHA256) != "ABSENT":
            _fail("helper install requires exact ABSENT baseline")
        raw = self._source_artifact(HELPER_SOURCE_RELATIVE, HELPER_SHA256)
        self._install_bytes(HELPER_DESTINATION, raw, mode=HELPER_MODE)

    def install_registration(self) -> None:
        if self._artifact_state(
            REGISTRATION_DESTINATION, mode=REGISTRATION_MODE, sha256=REGISTRATION_SHA256
        ) != "ABSENT":
            _fail("registration install requires exact ABSENT baseline")
        raw = self._source_artifact(REGISTRATION_SOURCE_RELATIVE, REGISTRATION_SHA256)
        self._install_bytes(REGISTRATION_DESTINATION, raw, mode=REGISTRATION_MODE)

    def verify_exact_state(self) -> InstallObservation:
        observed = self.observe()
        if observed != InstallObservation("EXACT", "EXACT", "EXACT"):
            _fail("installed runner-smoke state is not exact")
        return observed


def receipt_dict(receipt: ApplyReceipt) -> Mapping[str, Any]:
    return asdict(receipt)
