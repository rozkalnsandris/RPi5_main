#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = ROOT / "scripts/install-weather-operator-v7-host-capability.py"
CONTRACT = ROOT / "ops/deploy/weather-public-runtime-operator-upgrade-v7-host-capability-repair.json"
TRUSTED_SOURCE_CHECKOUT_NAME = "RPi5_main-weather-v7-host-capability-repair-source-trusted"
PREDECESSOR_SOURCE_SHA = "76496822e73e8ce628915978a1fea7970a2230ea"
PREDECESSOR_BROKER_SHA256 = "69d203453f4769e694f93a7840b3f81881d1cb49ea105322d3ad508a5b55925f"
PREDECESSOR_OPERATOR_SHA256 = "4058f89227b38dc62788b20fc82041113a9363a90b7fb9fd78743dd4fe41d27f"
BROKEN_MANAGER_CHECKOUT_NAME = "RPi5_main-weather-v7-host-capability-installer-source-v2-trusted"
V7_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-operator-upgrade-v7-trusted"
V6_CHECKOUT_NAME = "RPi5_main-weather-public-runtime-operator-upgrade-v6-trusted"
OPERATOR_TARGET = Path("/usr/local/sbin/rozkalns-weather-public-runtime-operator")


class RepairError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise RepairError(message)


def load_installer():
    spec = importlib.util.spec_from_file_location("weather_v7_host_capability_installer", INSTALLER_PATH)
    if spec is None or spec.loader is None:
        fail("host-capability installer module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = load_installer()


def sha256(data: bytes) -> str:
    return installer.sha256(data)


def source_bytes(path: str) -> bytes:
    return installer.source_bytes(path)


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


def load_registration() -> dict[str, object]:
    raw = safe_file(installer.REGISTRATION, mode=0o600, max_bytes=8192)
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RepairError("installed registration is malformed") from exc
    required = {
        "schema", "capability_source_sha", "manager_checkout", "artifact_count",
        "module_sha256", "broker_sha256", "socket_sha256", "service_sha256",
    }
    if type(value) is not dict or set(value) != required:
        fail("installed registration fields drifted")
    return value


def repair_source_identity() -> tuple[str, Path]:
    if ROOT.name != TRUSTED_SOURCE_CHECKOUT_NAME:
        fail("repair installer must run from the dedicated trusted source checkout")
    sha = installer.source_sha()
    symbolic = installer.run_git("symbolic-ref", "-q", "HEAD", check=False)
    if symbolic.returncode == 0:
        fail("repair source checkout must be detached")
    return sha, installer.canonical_manager_checkout()


def require_contract() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract.get("schema") != "rozkalns.rpi5-main.weather-operator-upgrade-v7-host-capability-repair.v1":
        fail("repair contract schema drifted")
    if contract.get("issue") != 593:
        fail("repair contract issue binding drifted")
    repair = contract.get("repair")
    if type(repair) is not dict:
        fail("repair contract repair section drifted")
    if repair.get("fixed_targets") != {
        str(installer.BROKER_TARGET): "0755",
        str(installer.REGISTRATION): "0600",
    }:
        fail("repair contract fixed targets drifted")
    if repair.get("mutation_budget") != [
        {"category": "filesystem.weather-v7-capability-broker-atomic-replace", "max_operations": 1},
        {"category": "filesystem.weather-v7-capability-registration-atomic-replace", "max_operations": 1},
    ]:
        fail("repair mutation budget drifted")


def preflight() -> dict[str, object]:
    sha, manager = repair_source_identity()
    require_contract()

    hashes: dict[str, str] = {}
    for source, target, mode in installer.ARTIFACTS:
        expected = source_bytes(source)
        installed = safe_file(target, mode=mode)
        installed_hash = sha256(installed)
        hashes[str(target)] = installed_hash
        if target == installer.BROKER_TARGET:
            if installed_hash != PREDECESSOR_BROKER_SHA256:
                fail("installed predecessor broker identity drifted")
        elif installed != expected:
            fail(f"unchanged host-capability artifact drifted: {target.name}")

    registration = load_registration()
    expected_broken_manager = manager.parent / BROKEN_MANAGER_CHECKOUT_NAME
    if registration.get("schema") != "rozkalns.rpi5-main.weather-operator-upgrade-v7-host-capability-registration.v1":
        fail("installed registration schema drifted")
    if registration.get("capability_source_sha") != PREDECESSOR_SOURCE_SHA:
        fail("installed registration predecessor source drifted")
    if registration.get("manager_checkout") != str(expected_broken_manager):
        fail("installed registration no longer matches the known broken manager binding")
    if registration.get("artifact_count") != len(installer.ARTIFACTS):
        fail("installed registration artifact count drifted")
    if registration.get("broker_sha256") != PREDECESSOR_BROKER_SHA256:
        fail("installed registration predecessor broker hash drifted")
    if registration.get("module_sha256") != hashes[str(installer.PACKAGE_ROOT / "weather_operator_upgrade_v7_host_capability.py")]:
        fail("installed registration module hash drifted")
    if registration.get("socket_sha256") != hashes[str(installer.SYSTEMD_ROOT / installer.SOCKET_NAME)]:
        fail("installed registration socket hash drifted")
    if registration.get("service_sha256") != hashes[str(installer.SYSTEMD_ROOT / installer.SERVICE_NAME)]:
        fail("installed registration service hash drifted")

    if sha256(safe_file(OPERATOR_TARGET, mode=0o755)) != PREDECESSOR_OPERATOR_SHA256:
        fail("Weather operator predecessor identity drifted")
    if (manager.parent / V7_CHECKOUT_NAME).exists():
        fail("v7 operator checkout already exists")
    if not (manager.parent / V6_CHECKOUT_NAME).is_dir():
        fail("preserved v6 checkout is absent")

    new_broker = source_bytes("ops/bin/rozkalns-weather-operator-v7-privileged-broker")
    new_broker_hash = sha256(new_broker)
    if new_broker_hash == PREDECESSOR_BROKER_SHA256:
        fail("repair broker source did not change")
    for target in (installer.BROKER_TARGET, installer.REGISTRATION):
        if (target.parent / f".{target.name}.repair-593.tmp").exists():
            fail(f"repair temp path already exists: {target.name}")

    return {
        "schema": "rozkalns.rpi5-main.weather-operator-upgrade-v7-host-capability-repair-preflight.v1",
        "result": "PASS",
        "source_sha": sha,
        "manager_checkout": str(manager),
        "artifact_count": len(installer.ARTIFACTS),
        "verified_unchanged_artifact_count": len(installer.ARTIFACTS) - 1,
        "predecessor_broker_sha256": PREDECESSOR_BROKER_SHA256,
        "target_broker_sha256": new_broker_hash,
        "host_mutation_started": False,
        "operator_replaced": False,
        "v7_checkout_created": False,
        "systemd_mutated": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def atomic_replace(path: Path, data: bytes, mode: int) -> None:
    temp = path.parent / f".{path.name}.repair-593.tmp"
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
    dir_fd = os.open(path.parent, os.O_RDONLY | os.O_CLOEXEC)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def apply() -> dict[str, object]:
    if os.geteuid() != 0:
        fail("--apply requires an owner-authorized root process")
    evidence = preflight()
    sha = str(evidence["source_sha"])
    manager = str(evidence["manager_checkout"])
    broker_data = source_bytes("ops/bin/rozkalns-weather-operator-v7-privileged-broker")
    broker_hash = sha256(broker_data)

    mutation_started = True
    try:
        atomic_replace(installer.BROKER_TARGET, broker_data, 0o755)
        registration = load_registration()
        registration["capability_source_sha"] = sha
        registration["manager_checkout"] = manager
        registration["broker_sha256"] = broker_hash
        registration_data = (
            json.dumps(registration, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        )
        atomic_replace(installer.REGISTRATION, registration_data, 0o600)

        if sha256(safe_file(installer.BROKER_TARGET, mode=0o755)) != broker_hash:
            fail("repaired broker postcondition failed")
        final_registration = load_registration()
        if final_registration.get("capability_source_sha") != sha:
            fail("repaired registration source postcondition failed")
        if final_registration.get("manager_checkout") != manager:
            fail("repaired registration manager postcondition failed")
        if final_registration.get("broker_sha256") != broker_hash:
            fail("repaired registration broker postcondition failed")
    except Exception as exc:
        raise RepairError(
            "host-capability repair failed closed after mutation; no retry/cleanup/rollback is authorized"
        ) from exc

    return {
        "schema": "rozkalns.rpi5-main.weather-operator-upgrade-v7-host-capability-repair-receipt.v1",
        "result": "PASS",
        "source_sha": sha,
        "manager_checkout": manager,
        "host_mutation_started": mutation_started,
        "broker_repaired": True,
        "registration_repaired": True,
        "broker_sha256": broker_hash,
        "operator_replaced": False,
        "v7_checkout_created": False,
        "systemd_mutated": False,
        "weather_runtime_mutated": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Repair the installed Weather v7 broker manager-registration boundary"
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
