from __future__ import annotations

from dataclasses import dataclass
import grp
import hashlib
import json
import os
import pwd
import stat
import subprocess
from types import MappingProxyType
from typing import Any, Mapping

from .hermes_deals_netto_nonroot_preflight_v2_adapter import SOURCE_SHA

CONTRACT_ID = "hermes-deals.netto-v2-dedicated-execution-identity.v1"
ACCESS_CONTRACT_ID = "hermes-deals.netto-v2-minimum-fixed-input-access.v1"
BROKER_COMPOSITION_PATTERN = "deploy_executor.hermes_deals_origin_broker_composition"

IDENTITY_CONTRACT_IMPLEMENTED = True
PRIVILEGE_DROP_SEAM_IMPLEMENTED = True
EXECUTION_ENABLED = False
HOST_WIRING_ENABLED = False
ACCESS_EVIDENCE_RESOLVER_WIRED = False
CANARY_AUTHORIZED = False
PRODUCTION_MUTATION_STARTED = False
PARALLEL_PRIVILEGED_BROKER_ALLOWED = False

EXECUTION_USER = "hermes-netto-audit"
EXECUTION_GROUP = "hermes-netto-audit"
EXECUTION_HOME = "/nonexistent"
EXECUTION_SHELL = "/usr/sbin/nologin"
FORBIDDEN_EXECUTION_USERS = frozenset({"root", "andris", "github-runner"})
FORBIDDEN_GROUPS = frozenset({"docker"})

INTERPRETER = "/usr/bin/python3"
INSTALLED_HELPER_PATH = (
    "/usr/local/libexec/hermes-deals-audits/"
    "netto-missing-normal-price-nonroot-preflight-v2/"
    "netto_missing_normal_price_nonroot_preflight_v2.py"
)
REGISTRATION_PATH = (
    "/etc/hermes-deals-audits.d/netto-missing-normal-price-nonroot-preflight-v2.json"
)
HELPER_SHA256 = "275b1e3296f8f9c7312447dec1b1acb3ffd5d09beaab62ac5ca216275d98360c"
REGISTRATION_SHA256 = (
    "887ad4e9295864307a24df6773e98f75056961aebeedd57b95641ba3e7386a1f"
)
REGISTRATION_BYTES = (
    b'{"capability":"netto-missing-normal-price-nonroot-preflight-v2",'
    b'"helper_sha256":"275b1e3296f8f9c7312447dec1b1acb3ffd5d09beaab62ac5ca216275d98360c",'
    b'"registered_source_sha":"067db7bd4b8057bc16a9bf0ef9ed8487127a0a05",'
    b'"schema":"rozkalns.hermes-deals.netto-nonroot-preflight-v2-registration.v1"}\n'
)
FIXED_CWD = "/"
FIXED_ENV: Mapping[str, str] = MappingProxyType(
    {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONUNBUFFERED": "1",
    }
)
FIXED_ARGV = (INTERPRETER, INSTALLED_HELPER_PATH, SOURCE_SHA)
HELPER_TIMEOUT_SECONDS = 50
MAX_STDOUT_BYTES = 32 * 1024
MAX_STDERR_BYTES = 4096
MAX_HELPER_BYTES = 128 * 1024
MAX_REGISTRATION_BYTES = 16 * 1024

RESULT_SCHEMA = "rozkalns.hermes-deals.netto-nonroot-preflight-v2-evidence.v1"
RESULT_STRATEGY = "netto_missing_normal_price_nonroot_access_preflight_v2"
RESULT_FIELDS = frozenset(
    {
        "schema", "schema_version", "strategy", "capability",
        "registered_source_sha", "runner_user", "runner_uid",
        "n9_manifest_readable", "n9_manifest_sha256_match",
        "corpus_root_readable", "corpus_root_executable",
        "blocked_at", "non_root_ready", "safe_permission_metadata",
        "sudo_used", "file_contents_exported", "parser_executed",
        "database_write_performed", "review_write_performed",
        "deployment_performed",
    }
)
PERMISSION_FIELDS = frozenset(
    {
        "home_andris_mode", "home_andris_uid", "home_andris_gid",
        "n9_parent_mode", "corpus_root_mode",
    }
)
FALSE_POSTCONDITIONS = (
    "sudo_used",
    "file_contents_exported",
    "parser_executed",
    "database_write_performed",
    "review_write_performed",
    "deployment_performed",
)

INPUT_HOME_ROOT = "/home"
INPUT_OWNER_ACCOUNT = "andris"
INPUT_OWNER_HOME = f"{INPUT_HOME_ROOT}/{INPUT_OWNER_ACCOUNT}"
N9_RELATIVE_ROOT = (
    "hermes-deals-audits/"
    "netto-n9-visual-cell-validation-pack-v1-20260802T202304Z"
)
N9_RELATIVE_GENERATED = f"{N9_RELATIVE_ROOT}/generated"
N9_RELATIVE_MANIFEST = f"{N9_RELATIVE_GENERATED}/fixture-manifest.json"
CORPUS_RELATIVE_PARENT = "hermes-deals-netto-corpus"
CORPUS_RELATIVE_ROOT = f"{CORPUS_RELATIVE_PARENT}/flyers"
FIXED_INPUT_RELATIVE_PATHS = (
    "",
    "hermes-deals-audits",
    N9_RELATIVE_ROOT,
    N9_RELATIVE_GENERATED,
    N9_RELATIVE_MANIFEST,
    CORPUS_RELATIVE_PARENT,
    CORPUS_RELATIVE_ROOT,
)
N9_ROOT = f"{INPUT_OWNER_HOME}/{N9_RELATIVE_ROOT}"
N9_GENERATED = f"{INPUT_OWNER_HOME}/{N9_RELATIVE_GENERATED}"
N9_MANIFEST = f"{INPUT_OWNER_HOME}/{N9_RELATIVE_MANIFEST}"
CORPUS_PARENT = f"{INPUT_OWNER_HOME}/{CORPUS_RELATIVE_PARENT}"
CORPUS_ROOT = f"{INPUT_OWNER_HOME}/{CORPUS_RELATIVE_ROOT}"


class HermesDealsNettoExecutionIdentityError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExecutionIdentitySnapshot:
    username: str
    uid: int
    primary_group: str
    gid: int
    home: str
    shell: str
    supplementary_groups: tuple[str, ...]


@dataclass(frozen=True)
class FixedAccessRequirement:
    path: str
    kind: str
    readable: bool
    executable: bool
    writable: bool


@dataclass(frozen=True)
class FixedAccessSnapshot:
    path: str
    kind: str
    readable: bool
    executable: bool
    writable: bool


FIXED_INPUT_ACCESS = (
    FixedAccessRequirement(INPUT_OWNER_HOME, "directory", False, True, False),
    FixedAccessRequirement(
        f"{INPUT_OWNER_HOME}/hermes-deals-audits", "directory", False, True, False
    ),
    FixedAccessRequirement(N9_ROOT, "directory", False, True, False),
    FixedAccessRequirement(N9_GENERATED, "directory", False, True, False),
    FixedAccessRequirement(N9_MANIFEST, "file", True, False, False),
    FixedAccessRequirement(CORPUS_PARENT, "directory", False, True, False),
    FixedAccessRequirement(CORPUS_ROOT, "directory", True, True, False),
)


@dataclass(frozen=True)
class SecureFileSnapshot:
    path: str
    regular: bool
    symlink: bool
    link_count: int
    uid: int
    gid: int
    mode: int
    size: int
    sha256: str
    descriptor_matches_path: bool
    content: bytes | None = None


@dataclass(frozen=True)
class NettoLaunchPlan:
    argv: tuple[str, str, str]
    cwd: str
    environment: tuple[tuple[str, str], ...]
    uid: int
    gid: int
    extra_groups: tuple[int, ...]
    shell: bool
    close_fds: bool
    timeout_seconds: int
    stdout_limit_bytes: int
    stderr_limit_bytes: int


@dataclass(frozen=True)
class FixedProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True)
class NettoLaunchReceipt:
    contract_id: str
    access_contract_id: str
    source_sha: str
    execution_user: str
    execution_uid: int
    helper_sha256: str
    registration_sha256: str
    blocked_at: str
    output_validated: bool
    production_mutation_started: bool = False


def resolve_execution_identity() -> ExecutionIdentitySnapshot:
    try:
        account = pwd.getpwnam(EXECUTION_USER)
        primary_group = grp.getgrgid(account.pw_gid)
    except KeyError as exc:
        raise HermesDealsNettoExecutionIdentityError(
            "dedicated Netto execution identity is absent"
        ) from exc
    supplementary = tuple(
        sorted(
            group.gr_name
            for group in grp.getgrall()
            if group.gr_gid != account.pw_gid and EXECUTION_USER in group.gr_mem
        )
    )
    snapshot = ExecutionIdentitySnapshot(
        username=account.pw_name,
        uid=account.pw_uid,
        primary_group=primary_group.gr_name,
        gid=account.pw_gid,
        home=account.pw_dir,
        shell=account.pw_shell,
        supplementary_groups=supplementary,
    )
    validate_execution_identity(snapshot)
    return snapshot


def validate_execution_identity(snapshot: ExecutionIdentitySnapshot) -> None:
    if type(snapshot) is not ExecutionIdentitySnapshot:
        raise HermesDealsNettoExecutionIdentityError("execution identity type drift")
    if snapshot.username != EXECUTION_USER or snapshot.username in FORBIDDEN_EXECUTION_USERS:
        raise HermesDealsNettoExecutionIdentityError("execution account identity drift")
    if type(snapshot.uid) is not int or snapshot.uid <= 0:
        raise HermesDealsNettoExecutionIdentityError("execution account must be non-root")
    if snapshot.primary_group != EXECUTION_GROUP or snapshot.primary_group in FORBIDDEN_GROUPS:
        raise HermesDealsNettoExecutionIdentityError("execution primary group drift")
    if type(snapshot.gid) is not int or snapshot.gid <= 0:
        raise HermesDealsNettoExecutionIdentityError("execution group must be non-root")
    if snapshot.home != EXECUTION_HOME or snapshot.shell != EXECUTION_SHELL:
        raise HermesDealsNettoExecutionIdentityError("execution account login metadata drift")
    if tuple(snapshot.supplementary_groups) != ():
        raise HermesDealsNettoExecutionIdentityError(
            "execution account must have no supplementary groups"
        )


def validate_fixed_input_access(snapshots: tuple[FixedAccessSnapshot, ...]) -> None:
    if type(snapshots) is not tuple or len(snapshots) != len(FIXED_INPUT_ACCESS):
        raise HermesDealsNettoExecutionIdentityError("fixed input-access evidence incomplete")
    for expected, observed in zip(FIXED_INPUT_ACCESS, snapshots, strict=True):
        if type(observed) is not FixedAccessSnapshot or observed != FixedAccessSnapshot(
            expected.path,
            expected.kind,
            expected.readable,
            expected.executable,
            expected.writable,
        ):
            raise HermesDealsNettoExecutionIdentityError(
                f"fixed input-access contract drift: {expected.path}"
            )


def _snapshot_fixed_file(
    path: str, *, max_bytes: int, retain_content: bool
) -> SecureFileSnapshot:
    try:
        path_stat = os.lstat(path)
    except OSError as exc:
        raise HermesDealsNettoExecutionIdentityError(
            f"fixed provenance path unavailable: {path}"
        ) from exc
    if not hasattr(os, "O_NOFOLLOW"):
        raise HermesDealsNettoExecutionIdentityError("O_NOFOLLOW is required")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError as exc:
        raise HermesDealsNettoExecutionIdentityError(
            f"fixed provenance path could not be opened safely: {path}"
        ) from exc
    digest = hashlib.sha256()
    captured = bytearray()
    size = 0
    try:
        descriptor_stat = os.fstat(fd)
        while True:
            chunk = os.read(fd, min(65536, max_bytes + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise HermesDealsNettoExecutionIdentityError(
                    f"fixed provenance path exceeds source size bound: {path}"
                )
            digest.update(chunk)
            if retain_content:
                captured.extend(chunk)
    except OSError as exc:
        raise HermesDealsNettoExecutionIdentityError(
            f"fixed provenance path read failed: {path}"
        ) from exc
    finally:
        os.close(fd)
    return SecureFileSnapshot(
        path=path,
        regular=stat.S_ISREG(path_stat.st_mode),
        symlink=stat.S_ISLNK(path_stat.st_mode),
        link_count=path_stat.st_nlink,
        uid=path_stat.st_uid,
        gid=path_stat.st_gid,
        mode=stat.S_IMODE(path_stat.st_mode),
        size=size,
        sha256=digest.hexdigest(),
        descriptor_matches_path=(
            path_stat.st_dev == descriptor_stat.st_dev
            and path_stat.st_ino == descriptor_stat.st_ino
        ),
        content=bytes(captured) if retain_content else None,
    )


def read_installed_provenance() -> tuple[SecureFileSnapshot, SecureFileSnapshot]:
    helper = _snapshot_fixed_file(
        INSTALLED_HELPER_PATH, max_bytes=MAX_HELPER_BYTES, retain_content=False
    )
    registration = _snapshot_fixed_file(
        REGISTRATION_PATH, max_bytes=MAX_REGISTRATION_BYTES, retain_content=True
    )
    validate_installed_provenance(helper, registration)
    return helper, registration


def _validate_secure_snapshot(
    snapshot: SecureFileSnapshot,
    *,
    expected_path: str,
    expected_mode: int,
    expected_sha256: str,
) -> None:
    if type(snapshot) is not SecureFileSnapshot or snapshot.path != expected_path:
        raise HermesDealsNettoExecutionIdentityError("fixed provenance identity drift")
    if not snapshot.regular or snapshot.symlink or snapshot.link_count != 1:
        raise HermesDealsNettoExecutionIdentityError("fixed provenance type/link drift")
    if snapshot.uid != 0 or snapshot.gid != 0 or snapshot.mode != expected_mode:
        raise HermesDealsNettoExecutionIdentityError("fixed provenance metadata drift")
    if not snapshot.descriptor_matches_path or snapshot.sha256 != expected_sha256:
        raise HermesDealsNettoExecutionIdentityError("fixed provenance content drift")


def validate_installed_provenance(
    helper: SecureFileSnapshot, registration: SecureFileSnapshot
) -> None:
    _validate_secure_snapshot(
        helper,
        expected_path=INSTALLED_HELPER_PATH,
        expected_mode=0o555,
        expected_sha256=HELPER_SHA256,
    )
    _validate_secure_snapshot(
        registration,
        expected_path=REGISTRATION_PATH,
        expected_mode=0o444,
        expected_sha256=REGISTRATION_SHA256,
    )
    if registration.content != REGISTRATION_BYTES:
        raise HermesDealsNettoExecutionIdentityError("registration canonical content drift")


def fixed_launch_plan(identity: ExecutionIdentitySnapshot) -> NettoLaunchPlan:
    validate_execution_identity(identity)
    return NettoLaunchPlan(
        argv=FIXED_ARGV,
        cwd=FIXED_CWD,
        environment=tuple(sorted(FIXED_ENV.items())),
        uid=identity.uid,
        gid=identity.gid,
        extra_groups=(),
        shell=False,
        close_fds=True,
        timeout_seconds=HELPER_TIMEOUT_SECONDS,
        stdout_limit_bytes=MAX_STDOUT_BYTES,
        stderr_limit_bytes=MAX_STDERR_BYTES,
    )


def _validate_launch_plan(plan: NettoLaunchPlan) -> None:
    if type(plan) is not NettoLaunchPlan:
        raise HermesDealsNettoExecutionIdentityError("launch plan type drift")
    if (
        plan.argv != FIXED_ARGV
        or plan.cwd != FIXED_CWD
        or plan.environment != tuple(sorted(FIXED_ENV.items()))
        or type(plan.uid) is not int
        or plan.uid <= 0
        or type(plan.gid) is not int
        or plan.gid <= 0
        or plan.extra_groups != ()
        or plan.shell is not False
        or plan.close_fds is not True
        or plan.timeout_seconds != HELPER_TIMEOUT_SECONDS
        or plan.stdout_limit_bytes != MAX_STDOUT_BYTES
        or plan.stderr_limit_bytes != MAX_STDERR_BYTES
    ):
        raise HermesDealsNettoExecutionIdentityError("fixed launch plan drift")


def _run_fixed_process(plan: NettoLaunchPlan) -> FixedProcessResult:
    """Future fixed privilege-drop seam; the runner re-resolves the fixed account."""
    _validate_launch_plan(plan)
    resolved_identity = resolve_execution_identity()
    if plan != fixed_launch_plan(resolved_identity):
        raise HermesDealsNettoExecutionIdentityError(
            "fixed Netto runner identity does not match the dedicated account"
        )
    try:
        completed = subprocess.run(
            plan.argv,
            cwd=plan.cwd,
            env=dict(plan.environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=plan.timeout_seconds,
            shell=False,
            close_fds=True,
            user=plan.uid,
            group=plan.gid,
            extra_groups=(),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HermesDealsNettoExecutionIdentityError(
            "fixed Netto helper process failed"
        ) from exc
    if (
        len(completed.stdout) > plan.stdout_limit_bytes
        or len(completed.stderr) > plan.stderr_limit_bytes
    ):
        raise HermesDealsNettoExecutionIdentityError(
            "fixed Netto helper output exceeded source limits"
        )
    return FixedProcessResult(completed.returncode, completed.stdout, completed.stderr)


def _reject_json_constant(value: str) -> None:
    raise HermesDealsNettoExecutionIdentityError(
        f"non-finite helper JSON value is forbidden: {value}"
    )


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise HermesDealsNettoExecutionIdentityError(
                f"duplicate helper JSON key is forbidden: {key}"
            )
        value[key] = item
    return value


def validate_helper_result(
    plan: NettoLaunchPlan, result: FixedProcessResult
) -> Mapping[str, Any]:
    _validate_launch_plan(plan)
    if type(result) is not FixedProcessResult or result.returncode != 0 or result.stderr:
        raise HermesDealsNettoExecutionIdentityError("fixed helper result failed closed")
    if len(result.stdout) > MAX_STDOUT_BYTES:
        raise HermesDealsNettoExecutionIdentityError("fixed helper stdout exceeded limit")
    try:
        payload = json.loads(
            result.stdout.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HermesDealsNettoExecutionIdentityError("fixed helper JSON invalid") from exc
    if type(payload) is not dict or set(payload) != RESULT_FIELDS:
        raise HermesDealsNettoExecutionIdentityError("fixed helper evidence fields drift")
    if (
        payload["schema"] != RESULT_SCHEMA
        or payload["schema_version"] != 2
        or payload["strategy"] != RESULT_STRATEGY
        or payload["capability"] != "netto-missing-normal-price-nonroot-preflight-v2"
        or payload["registered_source_sha"] != SOURCE_SHA
        or payload["runner_user"] != EXECUTION_USER
        or payload["runner_uid"] != plan.uid
    ):
        raise HermesDealsNettoExecutionIdentityError("fixed helper evidence identity drift")
    for field in (
        "n9_manifest_readable",
        "n9_manifest_sha256_match",
        "corpus_root_readable",
        "corpus_root_executable",
        "non_root_ready",
    ):
        if type(payload[field]) is not bool:
            raise HermesDealsNettoExecutionIdentityError(
                f"fixed helper evidence boolean drift: {field}"
            )
    if (
        payload["n9_manifest_readable"] is not True
        or payload["n9_manifest_sha256_match"] is not True
        or payload["corpus_root_readable"] is not True
        or payload["corpus_root_executable"] is not True
        or payload["blocked_at"] != "campaign_identity_probe_required"
        or payload["non_root_ready"] is not False
    ):
        raise HermesDealsNettoExecutionIdentityError("fixed helper readiness drift")
    metadata = payload["safe_permission_metadata"]
    if type(metadata) is not dict or set(metadata) != PERMISSION_FIELDS:
        raise HermesDealsNettoExecutionIdentityError("permission metadata drift")
    for field in FALSE_POSTCONDITIONS:
        if payload[field] is not False:
            raise HermesDealsNettoExecutionIdentityError(
                f"mutation postcondition drift: {field}"
            )
    return payload


class HermesDealsNettoV2OneShotLauncher:
    """Capability-specific future launcher; source remains disabled and unwired."""

    def __init__(self):
        self._invoked = False

    def launch_prevalidated(
        self,
        *,
        identity: ExecutionIdentitySnapshot,
        helper: SecureFileSnapshot,
        registration: SecureFileSnapshot,
        access: tuple[FixedAccessSnapshot, ...],
    ) -> NettoLaunchReceipt:
        if not (
            EXECUTION_ENABLED
            and HOST_WIRING_ENABLED
            and ACCESS_EVIDENCE_RESOLVER_WIRED
            and CANARY_AUTHORIZED
        ):
            raise HermesDealsNettoExecutionIdentityError(
                "Netto v2 execution remains source-disabled and unwired"
            )
        if os.geteuid() != 0:
            raise HermesDealsNettoExecutionIdentityError(
                "privilege drop requires the existing privileged broker parent"
            )
        if self._invoked:
            raise HermesDealsNettoExecutionIdentityError(
                "Netto v2 invocation budget already consumed"
            )
        validate_execution_identity(identity)
        validate_installed_provenance(helper, registration)
        validate_fixed_input_access(access)
        plan = fixed_launch_plan(identity)

        self._invoked = True
        try:
            result = _run_fixed_process(plan)
        except HermesDealsNettoExecutionIdentityError:
            raise
        except Exception:
            raise HermesDealsNettoExecutionIdentityError(
                "fixed Netto helper runner failed"
            ) from None
        payload = validate_helper_result(plan, result)
        return NettoLaunchReceipt(
            contract_id=CONTRACT_ID,
            access_contract_id=ACCESS_CONTRACT_ID,
            source_sha=SOURCE_SHA,
            execution_user=EXECUTION_USER,
            execution_uid=identity.uid,
            helper_sha256=HELPER_SHA256,
            registration_sha256=REGISTRATION_SHA256,
            blocked_at=payload["blocked_at"],
            output_validated=True,
        )


def source_readiness() -> Mapping[str, object]:
    return {
        "contract_id": CONTRACT_ID,
        "access_contract_id": ACCESS_CONTRACT_ID,
        "identity_contract_implemented": IDENTITY_CONTRACT_IMPLEMENTED,
        "privilege_drop_seam_implemented": PRIVILEGE_DROP_SEAM_IMPLEMENTED,
        "execution_enabled": EXECUTION_ENABLED,
        "host_wiring_enabled": HOST_WIRING_ENABLED,
        "access_evidence_resolver_wired": ACCESS_EVIDENCE_RESOLVER_WIRED,
        "canary_authorized": CANARY_AUTHORIZED,
        "production_mutation_started": PRODUCTION_MUTATION_STARTED,
        "execution_user": EXECUTION_USER,
        "execution_group": EXECUTION_GROUP,
        "execution_home": EXECUTION_HOME,
        "execution_shell": EXECUTION_SHELL,
        "supplementary_groups": (),
        "forbidden_execution_users": tuple(sorted(FORBIDDEN_EXECUTION_USERS)),
        "forbidden_groups": tuple(sorted(FORBIDDEN_GROUPS)),
        "broker_composition_pattern": BROKER_COMPOSITION_PATTERN,
        "parallel_privileged_broker_allowed": PARALLEL_PRIVILEGED_BROKER_ALLOWED,
        "interpreter": INTERPRETER,
        "helper_path": INSTALLED_HELPER_PATH,
        "registration_path": REGISTRATION_PATH,
        "registered_source_sha": SOURCE_SHA,
        "helper_sha256": HELPER_SHA256,
        "registration_sha256": REGISTRATION_SHA256,
        "argv": FIXED_ARGV,
        "cwd": FIXED_CWD,
        "environment": dict(FIXED_ENV),
        "timeout_seconds": HELPER_TIMEOUT_SECONDS,
        "stdout_limit_bytes": MAX_STDOUT_BYTES,
        "stderr_limit_bytes": MAX_STDERR_BYTES,
        "shell": False,
        "extra_groups": (),
        "invocation_budget": 1,
        "input_home_root": INPUT_HOME_ROOT,
        "input_owner_account": INPUT_OWNER_ACCOUNT,
        "fixed_input_relative_paths": FIXED_INPUT_RELATIVE_PATHS,
        "fixed_input_access": tuple(
            (item.path, item.kind, item.readable, item.executable, item.writable)
            for item in FIXED_INPUT_ACCESS
        ),
        "generic_home_read_allowed": False,
        "caller_command_path_argv_env_identity_authority": False,
        "requires_separate_live_authorization": True,
    }
