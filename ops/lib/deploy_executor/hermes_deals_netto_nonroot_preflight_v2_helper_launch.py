from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import stat
import subprocess
from types import MappingProxyType
from typing import Mapping

from .hermes_deals_netto_nonroot_preflight_v2_adapter import SOURCE_SHA

LAUNCH_IMPLEMENTED = True
LAUNCH_ENABLED = False
HOST_WIRING_ENABLED = False
CANARY_AUTHORIZED = False
PRODUCTION_MUTATION_STARTED = False

INTERPRETER = "/usr/bin/python3"
INSTALLED_HELPER_PATH = (
    "/usr/local/libexec/hermes-deals-audits/"
    "netto-missing-normal-price-nonroot-preflight-v2/"
    "netto_missing_normal_price_nonroot_preflight_v2.py"
)
HELPER_SHA256 = "275b1e3296f8f9c7312447dec1b1acb3ffd5d09beaab62ac5ca216275d98360c"
FIXED_CWD = "/home/andris"
RUN_UID = 1000
RUN_GID = 1000
EXTRA_GROUPS: tuple[int, ...] = ()
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
MAX_STDOUT_BYTES = 16384
MAX_STDERR_BYTES = 4096


class HermesDealsNettoNonrootPreflightV2LaunchError(RuntimeError):
    pass


@dataclass(frozen=True)
class InstalledHelperSnapshot:
    regular: bool
    symlink: bool
    link_count: int
    uid: int
    gid: int
    mode: int
    sha256: str
    descriptor_matches_path: bool


@dataclass(frozen=True)
class FixedNettoLaunchSpec:
    argv: tuple[str, str, str]
    cwd: str
    environment: tuple[tuple[str, str], ...]
    user: int
    group: int
    extra_groups: tuple[int, ...]
    shell: bool


def _read_fixed_helper_snapshot() -> InstalledHelperSnapshot:
    try:
        path_stat = os.lstat(INSTALLED_HELPER_PATH)
    except OSError as exc:
        raise HermesDealsNettoNonrootPreflightV2LaunchError(
            "installed Netto helper metadata unavailable"
        ) from exc

    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(INSTALLED_HELPER_PATH, flags)
    except OSError as exc:
        raise HermesDealsNettoNonrootPreflightV2LaunchError(
            "installed Netto helper could not be opened safely"
        ) from exc

    digest = hashlib.sha256()
    try:
        descriptor_stat = os.fstat(fd)
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            digest.update(chunk)
    except OSError as exc:
        raise HermesDealsNettoNonrootPreflightV2LaunchError(
            "installed Netto helper verification failed"
        ) from exc
    finally:
        os.close(fd)

    return InstalledHelperSnapshot(
        regular=stat.S_ISREG(path_stat.st_mode),
        symlink=stat.S_ISLNK(path_stat.st_mode),
        link_count=path_stat.st_nlink,
        uid=path_stat.st_uid,
        gid=path_stat.st_gid,
        mode=stat.S_IMODE(path_stat.st_mode),
        sha256=digest.hexdigest(),
        descriptor_matches_path=(
            path_stat.st_dev == descriptor_stat.st_dev
            and path_stat.st_ino == descriptor_stat.st_ino
        ),
    )


def _validate_helper_snapshot(snapshot: InstalledHelperSnapshot) -> None:
    if type(snapshot) is not InstalledHelperSnapshot:
        raise HermesDealsNettoNonrootPreflightV2LaunchError(
            "installed Netto helper snapshot type drift"
        )
    if not snapshot.regular or snapshot.symlink:
        raise HermesDealsNettoNonrootPreflightV2LaunchError(
            "installed Netto helper must be a regular non-symlink file"
        )
    if snapshot.link_count != 1:
        raise HermesDealsNettoNonrootPreflightV2LaunchError(
            "installed Netto helper link-count drift"
        )
    if snapshot.uid != 0 or snapshot.gid != 0 or snapshot.mode != 0o555:
        raise HermesDealsNettoNonrootPreflightV2LaunchError(
            "installed Netto helper ownership or mode drift"
        )
    if not snapshot.descriptor_matches_path:
        raise HermesDealsNettoNonrootPreflightV2LaunchError(
            "installed Netto helper descriptor identity drift"
        )
    if snapshot.sha256 != HELPER_SHA256:
        raise HermesDealsNettoNonrootPreflightV2LaunchError(
            "installed Netto helper SHA-256 drift"
        )


def validate_installed_helper() -> None:
    _validate_helper_snapshot(_read_fixed_helper_snapshot())


def fixed_launch_spec() -> FixedNettoLaunchSpec:
    return FixedNettoLaunchSpec(
        argv=FIXED_ARGV,
        cwd=FIXED_CWD,
        environment=tuple(sorted(FIXED_ENV.items())),
        user=RUN_UID,
        group=RUN_GID,
        extra_groups=EXTRA_GROUPS,
        shell=False,
    )


def launch_fixed_helper() -> subprocess.CompletedProcess[bytes]:
    """Future root-parent launcher. Source remains intentionally disabled and unwired."""

    if not LAUNCH_ENABLED or not HOST_WIRING_ENABLED or not CANARY_AUTHORIZED:
        raise HermesDealsNettoNonrootPreflightV2LaunchError(
            "Netto v2 fixed helper launch is source-disabled"
        )
    if os.geteuid() != 0:
        raise HermesDealsNettoNonrootPreflightV2LaunchError(
            "Netto v2 identity drop requires a root parent"
        )

    validate_installed_helper()
    spec = fixed_launch_spec()
    try:
        completed = subprocess.run(
            spec.argv,
            cwd=spec.cwd,
            env=dict(spec.environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=HELPER_TIMEOUT_SECONDS,
            shell=False,
            close_fds=True,
            user=RUN_UID,
            group=RUN_GID,
            extra_groups=EXTRA_GROUPS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HermesDealsNettoNonrootPreflightV2LaunchError(
            "Netto v2 fixed helper process failed"
        ) from exc

    if len(completed.stdout) > MAX_STDOUT_BYTES or len(completed.stderr) > MAX_STDERR_BYTES:
        raise HermesDealsNettoNonrootPreflightV2LaunchError(
            "Netto v2 fixed helper output exceeded source limits"
        )
    return completed


def source_readiness() -> Mapping[str, object]:
    spec = fixed_launch_spec()
    return {
        "launch_implemented": LAUNCH_IMPLEMENTED,
        "launch_enabled": LAUNCH_ENABLED,
        "host_wiring_enabled": HOST_WIRING_ENABLED,
        "canary_authorized": CANARY_AUTHORIZED,
        "production_mutation_started": PRODUCTION_MUTATION_STARTED,
        "interpreter": INTERPRETER,
        "helper_path": INSTALLED_HELPER_PATH,
        "registered_source_sha": SOURCE_SHA,
        "helper_sha256": HELPER_SHA256,
        "argv": spec.argv,
        "cwd": spec.cwd,
        "environment": dict(spec.environment),
        "uid": spec.user,
        "gid": spec.group,
        "extra_groups": spec.extra_groups,
        "shell": spec.shell,
        "helper_provenance_validation_required": True,
        "parent_root_required_for_identity_drop": True,
        "caller_process_authority": False,
    }
