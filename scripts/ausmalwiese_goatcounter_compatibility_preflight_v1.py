#!/usr/bin/env python3
"""Read-only GoatCounter service compatibility preflight for Ausmalwiese.

SOURCE ONLY. Running this operator on rpi5 requires a separate exact owner
authorization. It reads only reviewed source files and narrowly allowlisted host
metadata. It never reads credentials, database contents, private unit contents,
process environments, unrelated sockets or unrelated account databases.
"""
from __future__ import annotations

import ast
import grp
import json
import os
import platform
import pwd
import socket
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


PASS = "PASS_READ_ONLY_COMPATIBILITY_SOURCE_ONLY"

GOATCOUNTER_USER = "ausmalwiese-goatcounter"
GOATCOUNTER_GROUP = "ausmalwiese-goatcounter"
PAGEVIEW_USER = "ausmalwiese-pageview"
PAGEVIEW_GROUP = "ausmalwiese-pageview"

EXEC_ROOT = Path("/usr/local/libexec/ausmalwiese-goatcounter-v1")
DATA_ROOT = Path("/var/lib/ausmalwiese-goatcounter")
CREDENTIAL_ROOT = Path("/etc/ausmalwiese-goatcounter")
CATALOG_PATH = Path("/srv/coloring-pages-content/public/catalog.json")
CATALOG_PARENTS = (
    Path("/srv"),
    Path("/srv/coloring-pages-content"),
    Path("/srv/coloring-pages-content/public"),
)
MAX_CATALOG_BYTES = 8 * 1024 * 1024

GOATCOUNTER_UNIT = "ausmalwiese-goatcounter.service"
PAGEVIEW_UNIT = "ausmalwiese-goatcounter-pageview.service"
GOATCOUNTER_PORT = 9194
PAGEVIEW_PORT = 9193

SYSTEMCTL = "/usr/bin/systemctl"
SS = "/usr/bin/ss"

EXPECTED_CONTRACT = {
    "schema_version": 1,
    "state": "SOURCE_ONLY_NOT_INSTALLED",
    "repository": "rozkalnsandris/RPi5_main",
    "issue": 1224,
    "public": {
        "route": "/api/pageview",
        "hosts": ["ausmalwiese.de", "www.ausmalwiese.de"],
        "max_body_bytes": 128,
        "catalog": str(CATALOG_PATH),
    },
    "adapter": {
        "listen": "127.0.0.1:9193",
        "backend": "http://127.0.0.1:9194/api/v0/count",
        "backend_host": "goatcounter.ausmalwiese.invalid",
        "credential_name": "goatcounter-token",
    },
    "goatcounter": {
        "version": "v2.7.0",
        "source_commit": "7e91d8a9bdbb0dd48496e498c5680f8f3477a1b4",
        "arm64_asset": "goatcounter-v2.7.0-linux-arm64.gz",
        "arm64_bytes": 12770791,
        "arm64_sha256": "ff5b2670b858bbe48802dfdc74130b6dcde2de9f5c1229b838eb9132769307dd",
        "listen": "127.0.0.1:9194",
    },
    "boundaries": {
        "allow_live": False,
        "allow_install": False,
        "allow_ingress_change": False,
        "allow_database_mutation": False,
        "allow_secret_access_from_checkout": False,
        "allow_retry": False,
        "allow_rollback": False,
        "allow_cleanup": False,
        "request_logging": False,
        "forward_client_headers": False,
    },
}

EXPECTED_GOATCOUNTER_UNIT_LINES = (
    "ConditionPathIsExecutable=/usr/local/libexec/ausmalwiese-goatcounter-v1/goatcounter",
    "ConditionPathExists=/var/lib/ausmalwiese-goatcounter/goatcounter.sqlite3",
    "User=ausmalwiese-goatcounter",
    "Group=ausmalwiese-goatcounter",
    "ExecStart=/usr/local/libexec/ausmalwiese-goatcounter-v1/goatcounter serve -db=sqlite+/var/lib/ausmalwiese-goatcounter/goatcounter.sqlite3 -listen=127.0.0.1:9194 -tls=http -store-every=1",
    "ReadWritePaths=/var/lib/ausmalwiese-goatcounter",
    "StandardOutput=null",
    "StandardError=null",
)

EXPECTED_PAGEVIEW_UNIT_LINES = (
    "ConditionPathIsExecutable=/usr/local/libexec/ausmalwiese-goatcounter-v1/pageview-adapter.py",
    "ConditionPathExists=/usr/local/libexec/ausmalwiese-goatcounter-v1/pageview-contract.json",
    "ConditionPathExists=/srv/coloring-pages-content/public/catalog.json",
    "User=ausmalwiese-pageview",
    "Group=ausmalwiese-pageview",
    "LoadCredential=goatcounter-token:/etc/ausmalwiese-goatcounter/pageview-token",
    "ExecStart=/usr/local/libexec/ausmalwiese-goatcounter-v1/pageview-adapter.py --serve --contract=/usr/local/libexec/ausmalwiese-goatcounter-v1/pageview-contract.json",
    "ReadOnlyPaths=/srv/coloring-pages-content/public/catalog.json",
    "StandardOutput=null",
    "StandardError=null",
)

EXPECTED_ADAPTER_CONSTANTS = {
    "ADAPTER_HOST": "127.0.0.1",
    "ADAPTER_PORT": 9193,
    "GOATCOUNTER_URL": "http://127.0.0.1:9194/api/v0/count",
    "CREDENTIAL_NAME": "goatcounter-token",
}

SAFE_STOP_CODES = frozenset({
    "SOURCE_CONTRACT_DRIFT",
    "ROOT_FORBIDDEN",
    "WRONG_HOST",
    "WRONG_OS",
    "WRONG_ARCH",
    "USER_GOATCOUNTER_CONFLICT",
    "USER_PAGEVIEW_CONFLICT",
    "GROUP_GOATCOUNTER_CONFLICT",
    "GROUP_PAGEVIEW_CONFLICT",
    "EXEC_TARGET_CONFLICT",
    "DATA_TARGET_CONFLICT",
    "CREDENTIAL_TARGET_CONFLICT",
    "UNIT_GOATCOUNTER_CONFLICT",
    "UNIT_PAGEVIEW_CONFLICT",
    "UNIT_CHECK_UNAVAILABLE",
    "PORT_9193_CONFLICT",
    "PORT_9194_CONFLICT",
    "PORT_CHECK_UNAVAILABLE",
    "CATALOG_UNAVAILABLE",
    "CATALOG_SYMLINK",
    "CATALOG_TYPE",
    "CATALOG_SIZE",
    "CATALOG_MODE",
    "CATALOG_PARENT_UNAVAILABLE",
    "CATALOG_PARENT_TYPE",
    "CATALOG_PARENT_MODE",
    "METADATA_UNAVAILABLE",
})
FALLBACK_STOP = "PREFLIGHT_INTERNAL"


class PreflightStop(ValueError):
    """Stable non-sensitive compatibility failure code."""


def stop(code: str) -> None:
    raise PreflightStop(code)


def operator_safe_code(exc: PreflightStop) -> str:
    code = str(exc)
    return code if code in SAFE_STOP_CODES else FALLBACK_STOP


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            stop("SOURCE_CONTRACT_DRIFT")
        out[key] = value
    return out


def _read_source(path: Path, *, max_bytes: int = 256 * 1024) -> str:
    try:
        meta = path.lstat()
        if path.is_symlink() or not path.is_file() or not 1 <= meta.st_size <= max_bytes:
            stop("SOURCE_CONTRACT_DRIFT")
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        stop("SOURCE_CONTRACT_DRIFT")
    raise AssertionError("unreachable")


def _validate_unit(text: str, required: tuple[str, ...]) -> None:
    lines = text.splitlines()
    if any(lines.count(line) != 1 for line in required):
        stop("SOURCE_CONTRACT_DRIFT")


def _adapter_assignment(tree: ast.Module, name: str) -> object:
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != name:
            continue
        if isinstance(node.value, ast.Constant):
            return node.value.value
    stop("SOURCE_CONTRACT_DRIFT")
    raise AssertionError("unreachable")


def _adapter_path_assignment(tree: ast.Module, name: str) -> str:
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != name:
            continue
        value = node.value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "Path"
            and len(value.args) == 1
            and isinstance(value.args[0], ast.Constant)
            and isinstance(value.args[0].value, str)
            and not value.keywords
        ):
            return value.args[0].value
    stop("SOURCE_CONTRACT_DRIFT")
    raise AssertionError("unreachable")


def validate_source_contract(repo_root: Path) -> None:
    """Validate reviewed tracked source before touching any host metadata."""
    root = repo_root.resolve()
    contract_text = _read_source(
        root / "ops/contracts/ausmalwiese-goatcounter-pageview-v1.json",
        max_bytes=64 * 1024,
    )
    try:
        contract = json.loads(contract_text, object_pairs_hook=_strict_object)
    except (json.JSONDecodeError, TypeError, ValueError):
        stop("SOURCE_CONTRACT_DRIFT")
    if contract != EXPECTED_CONTRACT:
        stop("SOURCE_CONTRACT_DRIFT")

    goat_unit = _read_source(root / "ops/systemd/ausmalwiese-goatcounter.service")
    pageview_unit = _read_source(
        root / "ops/systemd/ausmalwiese-goatcounter-pageview.service"
    )
    _validate_unit(goat_unit, EXPECTED_GOATCOUNTER_UNIT_LINES)
    _validate_unit(pageview_unit, EXPECTED_PAGEVIEW_UNIT_LINES)

    adapter_source = _read_source(
        root / "scripts/ausmalwiese_goatcounter_pageview_adapter_v1.py"
    )
    try:
        tree = ast.parse(adapter_source)
    except SyntaxError:
        stop("SOURCE_CONTRACT_DRIFT")
    for name, expected in EXPECTED_ADAPTER_CONSTANTS.items():
        if _adapter_assignment(tree, name) != expected:
            stop("SOURCE_CONTRACT_DRIFT")
    if _adapter_path_assignment(tree, "CATALOG_PATH") != str(CATALOG_PATH):
        stop("SOURCE_CONTRACT_DRIFT")


@dataclass(frozen=True)
class PathMeta:
    exists: bool
    symlink: bool = False
    regular: bool = False
    directory: bool = False
    mode: int = 0
    size: int = 0


class HostMetadata(Protocol):
    def identity(self) -> tuple[str, str, str, int]: ...
    def user_exists(self, name: str) -> bool: ...
    def group_exists(self, name: str) -> bool: ...
    def path_meta(self, path: Path) -> PathMeta: ...
    def resolved_dir_meta(self, path: Path) -> PathMeta: ...
    def unit_load_state(self, unit: str) -> str: ...
    def port_occupied(self, port: int) -> bool: ...


class RealHostMetadata:
    """Narrow, read-only host metadata adapter."""

    def identity(self) -> tuple[str, str, str, int]:
        return (
            socket.gethostname().split(".", 1)[0],
            platform.system(),
            platform.machine(),
            os.geteuid(),
        )

    def user_exists(self, name: str) -> bool:
        try:
            pwd.getpwnam(name)
            return True
        except KeyError:
            return False
        except OSError:
            stop("METADATA_UNAVAILABLE")
        raise AssertionError("unreachable")

    def group_exists(self, name: str) -> bool:
        try:
            grp.getgrnam(name)
            return True
        except KeyError:
            return False
        except OSError:
            stop("METADATA_UNAVAILABLE")
        raise AssertionError("unreachable")

    def path_meta(self, path: Path) -> PathMeta:
        try:
            m = path.lstat()
        except FileNotFoundError:
            return PathMeta(False)
        except OSError:
            stop("METADATA_UNAVAILABLE")
        return PathMeta(
            True,
            symlink=stat.S_ISLNK(m.st_mode),
            regular=stat.S_ISREG(m.st_mode),
            directory=stat.S_ISDIR(m.st_mode),
            mode=stat.S_IMODE(m.st_mode),
            size=m.st_size,
        )

    def resolved_dir_meta(self, path: Path) -> PathMeta:
        try:
            m = path.stat()
        except FileNotFoundError:
            return PathMeta(False)
        except OSError:
            stop("METADATA_UNAVAILABLE")
        return PathMeta(
            True,
            regular=stat.S_ISREG(m.st_mode),
            directory=stat.S_ISDIR(m.st_mode),
            mode=stat.S_IMODE(m.st_mode),
            size=m.st_size,
        )

    def unit_load_state(self, unit: str) -> str:
        try:
            cp = subprocess.run(
                [SYSTEMCTL, "show", "--property=LoadState", "--value", unit],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=3,
                check=False,
                env={
                    "PATH": "/usr/bin:/bin",
                    "LC_ALL": "C",
                    "SYSTEMD_COLORS": "0",
                    "SYSTEMD_PAGER": "",
                },
            )
        except (OSError, subprocess.TimeoutExpired):
            stop("UNIT_CHECK_UNAVAILABLE")
        if cp.returncode != 0:
            stop("UNIT_CHECK_UNAVAILABLE")
        value = cp.stdout.strip()
        if not value:
            stop("UNIT_CHECK_UNAVAILABLE")
        return value

    def port_occupied(self, port: int) -> bool:
        if port not in (PAGEVIEW_PORT, GOATCOUNTER_PORT):
            stop("PORT_CHECK_UNAVAILABLE")
        try:
            cp = subprocess.run(
                [SS, "-H", "-ltn", f"sport = :{port}"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=3,
                check=False,
                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
            )
        except (OSError, subprocess.TimeoutExpired):
            stop("PORT_CHECK_UNAVAILABLE")
        if cp.returncode != 0:
            stop("PORT_CHECK_UNAVAILABLE")
        return bool(cp.stdout.strip())


def _require_absent_target(host: HostMetadata, path: Path, code: str) -> None:
    if host.path_meta(path).exists:
        stop(code)


def _validate_catalog(host: HostMetadata) -> None:
    for parent in CATALOG_PARENTS:
        meta = host.resolved_dir_meta(parent)
        if not meta.exists:
            stop("CATALOG_PARENT_UNAVAILABLE")
        if not meta.directory:
            stop("CATALOG_PARENT_TYPE")
        if not (meta.mode & stat.S_IXOTH):
            stop("CATALOG_PARENT_MODE")

    meta = host.path_meta(CATALOG_PATH)
    if not meta.exists:
        stop("CATALOG_UNAVAILABLE")
    if meta.symlink:
        stop("CATALOG_SYMLINK")
    if not meta.regular:
        stop("CATALOG_TYPE")
    if not 1 <= meta.size <= MAX_CATALOG_BYTES:
        stop("CATALOG_SIZE")
    if not (meta.mode & stat.S_IROTH) or (meta.mode & stat.S_IWOTH):
        stop("CATALOG_MODE")


def run_preflight(
    *,
    repo_root: Path | None = None,
    host: HostMetadata | None = None,
) -> str:
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[1]

    # Source validation must complete before any host metadata call.
    validate_source_contract(repo_root)

    if host is None:
        host = RealHostMetadata()

    hostname, os_name, arch, euid = host.identity()
    if euid == 0:
        stop("ROOT_FORBIDDEN")
    if hostname != "rpi5":
        stop("WRONG_HOST")
    if os_name != "Linux":
        stop("WRONG_OS")
    if arch != "aarch64":
        stop("WRONG_ARCH")

    if host.user_exists(GOATCOUNTER_USER):
        stop("USER_GOATCOUNTER_CONFLICT")
    if host.user_exists(PAGEVIEW_USER):
        stop("USER_PAGEVIEW_CONFLICT")
    if host.group_exists(GOATCOUNTER_GROUP):
        stop("GROUP_GOATCOUNTER_CONFLICT")
    if host.group_exists(PAGEVIEW_GROUP):
        stop("GROUP_PAGEVIEW_CONFLICT")

    # A pre-existing target root is a conflict. We deliberately do not inspect
    # its contents; absence of the root also proves the reviewed child targets
    # (binary/adapter, DB, credential) cannot already exist below it.
    _require_absent_target(host, EXEC_ROOT, "EXEC_TARGET_CONFLICT")
    _require_absent_target(host, DATA_ROOT, "DATA_TARGET_CONFLICT")
    _require_absent_target(host, CREDENTIAL_ROOT, "CREDENTIAL_TARGET_CONFLICT")

    if host.unit_load_state(GOATCOUNTER_UNIT) != "not-found":
        stop("UNIT_GOATCOUNTER_CONFLICT")
    if host.unit_load_state(PAGEVIEW_UNIT) != "not-found":
        stop("UNIT_PAGEVIEW_CONFLICT")

    if host.port_occupied(PAGEVIEW_PORT):
        stop("PORT_9193_CONFLICT")
    if host.port_occupied(GOATCOUNTER_PORT):
        stop("PORT_9194_CONFLICT")

    _validate_catalog(host)
    return PASS


def main() -> int:
    try:
        result = run_preflight()
    except PreflightStop as exc:
        print("GOATCOUNTER_COMPATIBILITY=STOP CODE=" + operator_safe_code(exc))
        return 2
    except Exception:
        # Never emit arbitrary host/tool exception details.
        print("GOATCOUNTER_COMPATIBILITY=STOP CODE=" + FALLBACK_STOP)
        return 2

    print(
        "GOATCOUNTER_COMPATIBILITY=" + result
        + " USERS=ABSENT GROUPS=ABSENT"
        + " TARGETS=ABSENT UNITS=ABSENT PORTS=FREE"
        + " CATALOG=COMPATIBLE"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
