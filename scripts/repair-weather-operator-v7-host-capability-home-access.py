#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = ROOT / "scripts/install-weather-operator-v7-host-capability.py"
CONTRACT = ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v7-host-capability-repair-v2.json"
TRUSTED_SOURCE_CHECKOUT_NAME = "RPi5_main-weather-v7-host-capability-repair-v2-source-trusted"
PREDECESSOR_SOURCE_SHA = "99c5568e4a6f0433546c728642b5375abd9a1189"
PREDECESSOR_BROKER_SHA256 = "d84004ec46ce802c264a29ea70e0ab8dda6f99785257649ebc9a655611d599be"
PREDECESSOR_REGISTRATION_SCHEMA = "rozkalns.rpi5-main.weather-operator-upgrade-v7-host-capability-registration.v1"
TARGET_REGISTRATION_SCHEMA = "rozkalns.rpi5-main.weather-operator-upgrade-v7-host-capability-registration.v2"
PREDECESSOR_OPERATOR_SHA256 = "4058f89227b38dc62788b20fc82041113a9363a90b7fb9fd78743dd4fe41d27f"
V7_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-operator-upgrade-v7-trusted"
V6_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-operator-upgrade-v6-trusted"
V6_SHA = "9136c37156e84da3918e58d5d467c8b1e5cc403a"
OPERATOR_TARGET = Path("/usr/local/sbin/rozkalns-weather-public-runtime-operator")
UPDATED_SOURCES = {
    "ops/lib/deploy_executor/weather_operator_upgrade_v7_host_capability.py",
    "ops/bin/rozkalns-weather-operator-v7-privileged-broker",
    "ops/systemd/rozkalns-weather-operator-v7-privileged-broker@.service",
}


class RepairError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise RepairError(message)


def load_installer():
    spec = importlib.util.spec_from_file_location("weather_v7_host_capability_installer_595", INSTALLER_PATH)
    if spec is None or spec.loader is None:
        fail("host-capability installer module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = load_installer()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_bytes(path: str) -> bytes:
    return installer.source_bytes(path)


def predecessor_source_bytes(path: str) -> bytes:
    try:
        result = subprocess.run(
            ["/usr/bin/git", "-C", str(ROOT), "show", f"{PREDECESSOR_SOURCE_SHA}:{path}"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=installer.git_environment(),
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RepairError(f"predecessor source artifact is unavailable: {path}") from exc
    data = bytes(result.stdout)
    if not data:
        fail(f"predecessor source artifact is empty: {path}")
    return data


def safe_file(path: Path, *, mode: int, max_bytes: int = 2 * 1024 * 1024) -> bytes:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        fail(f"repair target is not a single-link regular file: {path.name}")
    if before.st_uid != 0 or before.st_gid != 0 or stat.S_IMODE(before.st_mode) != mode:
        fail(f"repair target metadata drifted: {path.name}")
    if not 0 < before.st_size <= max_bytes:
        fail(f"repair target size is invalid: {path.name}")
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            fail(f"repair target changed before open: {path.name}")
        data = os.read(fd, max_bytes + 1)
        if len(data) != opened.st_size or len(data) > max_bytes:
            fail(f"repair target changed while read: {path.name}")
        return data
    finally:
        os.close(fd)


def load_predecessor_registration() -> dict[str, object]:
    raw = safe_file(installer.REGISTRATION, mode=0o600, max_bytes=8192)
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RepairError("installed registration is malformed") from exc
    required = {
        "schema",
        "capability_source_sha",
        "manager_checkout",
        "artifact_count",
        "module_sha256",
        "broker_sha256",
        "socket_sha256",
        "service_sha256",
    }
    if type(value) is not dict or set(value) != required:
        fail("installed predecessor registration fields drifted")
    if value.get("schema") != PREDECESSOR_REGISTRATION_SCHEMA:
        fail("installed predecessor registration schema drifted")
    return value


def repair_source_identity() -> tuple[str, Path, int, int]:
    if ROOT.name != TRUSTED_SOURCE_CHECKOUT_NAME:
        fail("repair installer must run from the dedicated trusted source checkout")
    sha = installer.source_sha()
    symbolic = installer.run_git("symbolic-ref", "-q", "HEAD", check=False)
    if symbolic.returncode == 0:
        fail("repair source checkout must be detached")
    manager = installer.canonical_manager_checkout()
    manager_uid, manager_gid = installer.manager_identity(manager)
    return sha, manager, manager_uid, manager_gid


def require_contract() -> dict[str, object]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract.get("schema") != "rozkalns.rpi5-main.weather-operator-upgrade-v7-host-capability-repair.v2":
        fail("repair contract schema drifted")
    if contract.get("issue") != 595:
        fail("repair contract issue binding drifted")
    repair = contract.get("repair")
    if type(repair) is not dict:
        fail("repair contract repair section drifted")
    expected_targets = {
        str(installer.PACKAGE_ROOT / "weather_operator_upgrade_v7_host_capability.py"): "0644",
        str(installer.BROKER_TARGET): "0755",
        str(installer.SYSTEMD_ROOT / installer.SERVICE_NAME): "0644",
        str(installer.REGISTRATION): "0600",
    }
    if repair.get("fixed_targets") != expected_targets:
        fail("repair contract fixed targets drifted")
    if repair.get("mutation_budget") != [
        {"category": "filesystem.weather-v7-capability-module-atomic-replace", "max_operations": 1},
        {"category": "filesystem.weather-v7-capability-broker-atomic-replace", "max_operations": 1},
        {"category": "filesystem.weather-v7-capability-service-template-atomic-replace", "max_operations": 1},
        {"category": "filesystem.weather-v7-capability-registration-v2-atomic-replace", "max_operations": 1},
        {"category": "systemd.weather-v7-capability-daemon-reload", "max_operations": 1},
    ]:
        fail("repair mutation budget drifted")
    sandbox = contract.get("service_sandbox")
    if type(sandbox) is not dict or sandbox.get("capability_bounding_set") != ["CAP_SETUID", "CAP_SETGID"]:
        fail("repair service capability contract drifted")
    if sandbox.get("cap_dac_override_allowed") is not False:
        fail("repair must not allow CAP_DAC_OVERRIDE")
    if sandbox.get("cap_dac_read_search_allowed") is not False:
        fail("repair must not allow CAP_DAC_READ_SEARCH")
    return contract


def require_v6(manager: Path) -> None:
    result = installer.run_git_at(manager, "worktree", "list", "--porcelain")
    expected_path = str(manager.parent / V6_CHECKOUT_NAME)
    blocks = result.stdout.strip().split("\n\n") if result.stdout.strip() else []
    matching = [block for block in blocks if f"worktree {expected_path}" in block.splitlines()]
    if len(matching) != 1 or f"HEAD {V6_SHA}" not in matching[0].splitlines() or "detached" not in matching[0].splitlines():
        fail("preserved v6 checkout registration drifted")
    v6 = manager.parent / V6_CHECKOUT_NAME
    if installer.run_git_at(v6, "status", "--porcelain", "--untracked-files=all").stdout != "":
        fail("preserved v6 checkout is dirty")


def preflight() -> dict[str, object]:
    sha, manager, manager_uid, manager_gid = repair_source_identity()
    require_contract()
    registration = load_predecessor_registration()
    if registration.get("capability_source_sha") != PREDECESSOR_SOURCE_SHA:
        fail("installed predecessor registration source drifted")
    if registration.get("manager_checkout") != str(manager):
        fail("installed predecessor manager binding drifted")
    if registration.get("artifact_count") != len(installer.ARTIFACTS):
        fail("installed predecessor artifact count drifted")

    installed_hashes: dict[str, str] = {}
    for source, target, mode in installer.ARTIFACTS:
        installed = safe_file(target, mode=mode)
        expected = predecessor_source_bytes(source)
        if installed != expected:
            fail(f"installed predecessor artifact drifted: {target.name}")
        installed_hashes[str(target)] = sha256(installed)

    if installed_hashes[str(installer.BROKER_TARGET)] != PREDECESSOR_BROKER_SHA256:
        fail("installed predecessor broker identity drifted")
    if registration.get("broker_sha256") != PREDECESSOR_BROKER_SHA256:
        fail("installed predecessor registration broker hash drifted")
    if registration.get("module_sha256") != installed_hashes[str(installer.PACKAGE_ROOT / "weather_operator_upgrade_v7_host_capability.py")]:
        fail("installed predecessor registration module hash drifted")
    if registration.get("socket_sha256") != installed_hashes[str(installer.SYSTEMD_ROOT / installer.SOCKET_NAME)]:
        fail("installed predecessor registration socket hash drifted")
    if registration.get("service_sha256") != installed_hashes[str(installer.SYSTEMD_ROOT / installer.SERVICE_NAME)]:
        fail("installed predecessor registration service hash drifted")

    if sha256(safe_file(OPERATOR_TARGET, mode=0o755)) != PREDECESSOR_OPERATOR_SHA256:
        fail("Weather operator predecessor identity drifted")
    if (manager.parent / V7_CHECKOUT_NAME).exists():
        fail("v7 operator checkout already exists")
    require_v6(manager)

    targets = (
        installer.PACKAGE_ROOT / "weather_operator_upgrade_v7_host_capability.py",
        installer.BROKER_TARGET,
        installer.SYSTEMD_ROOT / installer.SERVICE_NAME,
        installer.REGISTRATION,
    )
    for target in targets:
        if (target.parent / f".{target.name}.repair-595.tmp").exists():
            fail(f"repair temp path already exists: {target.name}")

    target_hashes = {
        "module_sha256": sha256(source_bytes("ops/lib/deploy_executor/weather_operator_upgrade_v7_host_capability.py")),
        "broker_sha256": sha256(source_bytes("ops/bin/rozkalns-weather-operator-v7-privileged-broker")),
        "socket_sha256": installed_hashes[str(installer.SYSTEMD_ROOT / installer.SOCKET_NAME)],
        "service_sha256": sha256(source_bytes("ops/systemd/rozkalns-weather-operator-v7-privileged-broker@.service")),
    }
    return {
        "schema": "rozkalns.rpi5-main.weather-operator-upgrade-v7-host-capability-repair-preflight.v2",
        "result": "PASS",
        "source_sha": sha,
        "manager_checkout": str(manager),
        "manager_uid": manager_uid,
        "manager_gid": manager_gid,
        "artifact_count": len(installer.ARTIFACTS),
        "predecessor_broker_sha256": PREDECESSOR_BROKER_SHA256,
        "target_broker_sha256": target_hashes["broker_sha256"],
        "target_hashes": target_hashes,
        "host_mutation_started": False,
        "operator_replaced": False,
        "v7_checkout_created": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def atomic_replace(path: Path, data: bytes, mode: int) -> None:
    temp = path.parent / f".{path.name}.repair-595.tmp"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, mode)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                fail("repair write made no progress")
            view = view[written:]
        os.fsync(fd)
        os.fchmod(fd, mode)
        os.fchown(fd, 0, 0)
    finally:
        os.close(fd)
    os.replace(temp, path)
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_CLOEXEC)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def systemctl_daemon_reload() -> None:
    subprocess.run(
        ["/usr/bin/systemctl", "daemon-reload"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        check=True,
    )


def apply() -> dict[str, object]:
    if os.geteuid() != 0:
        fail("--apply requires an owner-authorized root process")
    evidence = preflight()
    sha = str(evidence["source_sha"])
    manager = str(evidence["manager_checkout"])
    manager_uid = int(evidence["manager_uid"])
    manager_gid = int(evidence["manager_gid"])
    target_hashes = dict(evidence["target_hashes"])

    module_target = installer.PACKAGE_ROOT / "weather_operator_upgrade_v7_host_capability.py"
    service_target = installer.SYSTEMD_ROOT / installer.SERVICE_NAME
    module_data = source_bytes("ops/lib/deploy_executor/weather_operator_upgrade_v7_host_capability.py")
    broker_data = source_bytes("ops/bin/rozkalns-weather-operator-v7-privileged-broker")
    service_data = source_bytes("ops/systemd/rozkalns-weather-operator-v7-privileged-broker@.service")
    registration = {
        "schema": TARGET_REGISTRATION_SCHEMA,
        "capability_source_sha": sha,
        "manager_checkout": manager,
        "manager_uid": manager_uid,
        "manager_gid": manager_gid,
        "artifact_count": len(installer.ARTIFACTS),
        "module_sha256": target_hashes["module_sha256"],
        "broker_sha256": target_hashes["broker_sha256"],
        "socket_sha256": target_hashes["socket_sha256"],
        "service_sha256": target_hashes["service_sha256"],
    }
    registration_data = json.dumps(
        registration,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"

    mutation_started = True
    try:
        atomic_replace(module_target, module_data, 0o644)
        atomic_replace(installer.BROKER_TARGET, broker_data, 0o755)
        atomic_replace(service_target, service_data, 0o644)
        atomic_replace(installer.REGISTRATION, registration_data, 0o600)
        systemctl_daemon_reload()

        if safe_file(module_target, mode=0o644) != module_data:
            fail("repaired module postcondition failed")
        if safe_file(installer.BROKER_TARGET, mode=0o755) != broker_data:
            fail("repaired broker postcondition failed")
        if safe_file(service_target, mode=0o644) != service_data:
            fail("repaired service template postcondition failed")
        if safe_file(installer.REGISTRATION, mode=0o600, max_bytes=8192) != registration_data:
            fail("repaired registration postcondition failed")
        if sha256(safe_file(OPERATOR_TARGET, mode=0o755)) != PREDECESSOR_OPERATOR_SHA256:
            fail("Weather operator changed during capability repair")
    except Exception as exc:
        raise RepairError(
            "host-capability repair v2 failed closed after mutation; no retry/cleanup/rollback is authorized"
        ) from exc

    return {
        "schema": "rozkalns.rpi5-main.weather-operator-upgrade-v7-host-capability-repair-receipt.v2",
        "result": "PASS",
        "source_sha": sha,
        "manager_checkout": manager,
        "manager_uid": manager_uid,
        "manager_gid": manager_gid,
        "host_mutation_started": mutation_started,
        "module_repaired": True,
        "broker_repaired": True,
        "service_template_repaired": True,
        "registration_v2_written": True,
        "daemon_reloaded": True,
        "socket_restarted": False,
        "caller_timer_restarted": False,
        "operator_replaced": False,
        "v7_checkout_created": False,
        "weather_runtime_mutated": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Repair Weather v7 broker home access and LIVE-AUTH provenance boundary"
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = apply() if args.apply else preflight()
    except RepairError as exc:
        print(json.dumps({"result": "FAIL_CLOSED", "reason": str(exc)}, sort_keys=True, separators=(",", ":")))
        return 78
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
