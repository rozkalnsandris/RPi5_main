#!/usr/bin/env python3
"""Fail-closed Weather-only rebind operator: future LIVE authorization required."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import urllib.request

from weather_public_rebind_contract_v1 import contract, source_errors, preflight

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://github.com/rozkalnsandris/RPi5_main.git"
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
CID = re.compile(r"^[a-f0-9]{12,64}$")
IMAGE = "ghcr.io/rozkalnsandris/rozkalns_weather"
CONFIRM = "REBIND-WEATHER-PUBLIC-915"
ENV_PATH = Path("/etc/rozkalns-simple-deployer/private/rozkalns-weather-private-home.env")


class Blocked(Exception):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise Blocked(reason)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixed_file(path: Path, uid: int, mode: int, limit: int = 65536) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        require(stat.S_ISREG(st.st_mode) and st.st_uid == uid
                and (uid != 0 or st.st_gid == 0)
                and stat.S_IMODE(st.st_mode) == mode and st.st_size <= limit,
                "FIXED_FILE_METADATA")
        data = os.read(fd, limit + 1)
        require(len(data) <= limit, "FIXED_FILE_TOO_LARGE")
        return data
    finally:
        os.close(fd)


def root_dir(path: Path) -> None:
    st = path.lstat()
    require(stat.S_ISDIR(st.st_mode) and st.st_uid == 0
            and st.st_gid == 0 and stat.S_IMODE(st.st_mode) == 0o755,
            "ROOT_DIRECTORY_DRIFT")


def command(argv: list[str], timeout: int = 20) -> str:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, check=False,
                                timeout=timeout, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
    except (OSError, subprocess.TimeoutExpired):
        raise Blocked("COMMAND_TRANSPORT")
    require(result.returncode == 0 and len(result.stdout) < 30000, "COMMAND_FAILED")
    return result.stdout.strip()


def git(*argv: str) -> str:
    return command(["/usr/bin/git", "-c", f"safe.directory={ROOT}", "-C",
                    str(ROOT), *argv])


def source_gate(expected: str) -> None:
    require(SHA.fullmatch(expected) is not None, "SOURCE_SHA_INVALID")
    require(os.geteuid() == 0, "ROOT_REQUIRED")
    require(git("rev-parse", "--show-toplevel") == str(ROOT), "CHECKOUT_DRIFT")
    require(git("branch", "--show-current") == "main", "BRANCH_DRIFT")
    require(git("rev-parse", "HEAD") == expected, "HEAD_DRIFT")
    require(git("remote", "get-url", "origin") == ORIGIN, "ORIGIN_DRIFT")
    require(git("status", "--porcelain=v1", "--untracked-files=all") == "", "DIRTY_CHECKOUT")
    require(not source_errors(contract()), "SOURCE_CONTRACT_DRIFT")


@contextmanager
def weather_lock(path: Path):
    # The existing lock must already exist. Never create a file in preflight.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        require(stat.S_ISREG(st.st_mode)
                and st.st_uid == pwd.getpwnam("rozkalns-simple-deployer").pw_uid
                and stat.S_IMODE(st.st_mode) == 0o600, "LOCK_DRIFT")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Blocked("LOCK_BUSY")
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def container_state() -> dict:
    lines = command(["/usr/bin/docker", "ps", "--all",
                     "--filter", "label=com.docker.compose.project=rozkalns-weather-public",
                     "--filter", "label=com.docker.compose.service=weather",
                     "--format", "{{.ID}}"]).splitlines()
    require(len(lines) == 1 and CID.fullmatch(lines[0]) is not None, "CONTAINER_CARDINALITY")
    cid = lines[0]
    def field(selector: str):
        return command(["/usr/bin/docker", "inspect", "--format", selector, cid])
    state = json.loads(field("{{json .State}}"))
    ports = json.loads(field("{{json .NetworkSettings.Ports}}"))
    mounts = json.loads(field("{{json .Mounts}}"))
    image = field("{{.Config.Image}}")
    require(type(state) is dict and type(ports) is dict and type(mounts) is list,
            "DOCKER_SCHEMA")
    ips = [entry.get("HostIp") for binding in ports.values() if binding
           for entry in binding if type(entry) is dict]
    bind = ("wildcard" if ips and any(ip in ("0.0.0.0", "::", "") for ip in ips)
            else "loopback" if ips and all(ip == "127.0.0.1" for ip in ips)
            else "other")
    healthy = state.get("Running") is True and type(state.get("Health")) is dict and state["Health"].get("Status") == "healthy"
    volume = [m for m in mounts if type(m) is dict and m.get("Destination") == "/app/data"]
    correct_volume = (len(volume) == 1 and volume[0].get("Type") == "volume"
                      and volume[0].get("Name") == "rozkalns-weather-public_weather_data")
    return {"image": image, "bind": bind, "healthy": healthy, "volume": correct_volume}


def installed_and_desired(spec: dict, expected: str) -> tuple[dict, dict, dict]:
    paths = {key: Path(spec["installed"][key]) for key in ("compose", "registry", "identity")}
    for path in paths.values():
        root_dir(path.parent)
    old = {key: fixed_file(path, 0, 0o444) for key, path in paths.items()}
    base = spec["baseline"]
    require(sha256(old["compose"]) == base["compose_sha256_from_readonly_host"], "COMPOSE_BASE_DRIFT")
    require(sha256(old["registry"]) == base["registry_sha256_from_historical_source_unverified_on_host"], "REGISTRY_BASE_DRIFT")
    identity = json.loads(old["identity"])
    require(type(identity) is dict and set(identity) == {"schema", "repository", "source_sha"}
            and identity["schema"] == "rozkalns.rpi5-main.simple-deploy.identity.v1"
            and identity["repository"] == "rozkalnsandris/RPi5_main"
            and identity["source_sha"] == base["identity_source_sha"], "IDENTITY_DRIFT")
    new = {
        key: (ROOT / spec["source_files"][key]).read_bytes()
        for key in ("compose", "registry")
    }
    new["identity"] = (json.dumps({
        "repository": "rozkalnsandris/RPi5_main",
        "schema": "rozkalns.rpi5-main.simple-deploy.identity.v1",
        "source_sha": expected,
    }, sort_keys=True, separators=(",", ":")) + "\n").encode()
    require(sha256(new["compose"]) == spec["desired"]["compose_sha256"]
            and sha256(new["registry"]) == spec["desired"]["registry_sha256"], "SOURCE_HASH_DRIFT")
    a = json.loads(old["registry"])["targets"]
    b = json.loads(new["registry"])["targets"]
    require(len(a) == len(b) == 5, "TARGET_COUNT")
    for before, after in zip(a, b):
        require(before["target_alias"] == after["target_alias"], "TARGET_ORDER_DRIFT")
        if after["target_alias"] != spec["target_alias"]:
            require(before == after, "OTHER_TARGET_DRIFT")
        else:
            require({k:v for k,v in before.items() if k not in ("compose","shared_workflow_sha")}
                    == {k:v for k,v in after.items() if k not in ("compose","shared_workflow_sha")}
                    and {k:v for k,v in before["compose"].items() if k != "file_sha256"}
                    == {k:v for k,v in after["compose"].items() if k != "file_sha256"},
                    "WEATHER_TARGET_DRIFT")
    st = ENV_PATH.lstat()
    require(stat.S_ISREG(st.st_mode) and st.st_uid == 0 and st.st_gid == 0
            and stat.S_IMODE(st.st_mode) == 0o600, "PROTECTED_ENV_METADATA")
    return paths, old, new


def immutable_state(spec: dict, bind: str) -> str:
    username = pwd.getpwnam("rozkalns-simple-deployer").pw_uid
    receipt = json.loads(fixed_file(Path(spec["installed"]["receipt"]), username, 0o600))
    override = json.loads(fixed_file(Path(spec["installed"]["override"]), username, 0o600))
    status_file = Path(spec["installed"]["receipt"]).parent.parent / "status/rozkalns-weather-public-rpi5.json"
    status = json.loads(fixed_file(status_file, username, 0o600))
    require(not (status.get("result") == "STOP_ERROR" and status.get("mutation_started") is True),
            "PREVIOUS_STOP_ERROR")
    value = receipt.get("deployed_digest")
    require(receipt.get("schema") == "rozkalns.rpi5-main.simple-deploy.receipt.v1"
            and receipt.get("result") == "SUCCESS"
            and type(value) is str and DIGEST.fullmatch(value) is not None,
            "RECEIPT_DRIFT")
    frozen = IMAGE + "@" + value
    require(override == {"services":{"weather":{"image":frozen}}}, "OVERRIDE_DRIFT")
    state = container_state()
    require(state["image"] == frozen and state["healthy"] and state["volume"]
            and state["bind"] == bind, "CONTAINER_DRIFT")
    labels = json.loads(command(["/usr/bin/docker", "image", "inspect", "--format",
                                 "{{json .Config.Labels}}", frozen]))
    require(type(labels) is dict and
            labels.get("io.rozkalns.simple-deploy.target") == spec["target_alias"]
            and labels.get("io.rozkalns.simple-deploy.shared-revision") == spec["desired"]["shared_workflow_sha"]
            and type(labels.get("org.opencontainers.image.revision")) is str
            and SHA.fullmatch(labels["org.opencontainers.image.revision"]) is not None,
            "IMAGE_LABEL_DRIFT")
    return frozen


def stage(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(os.dup(fd), "wb") as f:
            f.write(data)
            f.flush()
        os.fchown(fd, 0, 0)
        os.fchmod(fd, 0o444)
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def replace_three(paths: dict, old: dict, new: dict, progress) -> None:
    names = ("compose", "registry", "identity")
    stages = {k: paths[k].with_name("." + paths[k].name + ".weather-rebind-915.staged")
              for k in names}
    require(not any(os.path.lexists(p) for p in stages.values()), "STAGE_EXISTS")
    for k in names:
        progress("STAGING", True)
        stage(stages[k], new[k])
    for k in names:
        require(fixed_file(paths[k], 0, 0o444) == old[k], "PRE_REPLACE_DRIFT")
    for k in names:
        progress("REPLACE_" + k.upper(), True)
        require(fixed_file(paths[k], 0, 0o444) == old[k], "PRE_REPLACE_DRIFT")
        os.replace(stages[k], paths[k])
        fsync_dir(paths[k].parent)
        require(fixed_file(paths[k], 0, 0o444) == new[k], "POST_REPLACE_DRIFT")


def listener_loopback() -> bool:
    # Fixed-class, read-only listener observation. Never publish ss output.
    rows = command(["/usr/bin/ss", "-H", "-ltn"], timeout=10).splitlines()
    bound = []
    for row in rows:
        fields = row.split()
        if len(fields) >= 5 and fields[3].endswith(":9180"):
            bound.append(fields[3].rsplit(":", 1)[0])
    return bound == ["127.0.0.1"]


def health(path: str) -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:9180/" + path, timeout=5) as res:
            return res.status == 200
    except (OSError, ValueError):
        return False


def execute(expected: str, apply: bool = False) -> dict:
    phase, mutation = "PREFLIGHT", False
    try:
        source_gate(expected)
        spec = contract()
        with weather_lock(Path(spec["installed"]["lock"])):
            paths, old, new = installed_and_desired(spec, expected)
            frozen = immutable_state(spec, "wildcard")
            evidence = {
                "exact_final_main": expected, "checkout_exact_clean_main_origin": True,
                "installed_identity_sha": spec["baseline"]["identity_source_sha"],
                "installed_registry_sha256": sha256(old["registry"]),
                "installed_compose_sha256": sha256(old["compose"]),
                "root_owned_files_mode_0444": True, "candidate_source_hashes_match": True,
                "non_weather_registry_targets_identical": True, "weather_target_exact": True,
                "target_lock_available": True, "no_blocking_stop_error": True,
                "weather_container_count": 1, "weather_running_healthy": True,
                "weather_publish_class": "wildcard", "weather_volume_preserved": True,
                "receipt_digest": frozen.split("@")[-1], "override_digest": frozen.split("@")[-1],
                "running_image_digest": frozen.split("@")[-1],
                "image_labels_pass": True, "protected_env_metadata_only": True,
            }
            require(preflight(spec, evidence)["result"] == "PASS", "CLASSIFIER_BLOCKED")
            if not apply:
                return {"result": "PASS", "phase": phase, "mutation_performed": False}
            def progress(name, started):
                nonlocal phase, mutation
                phase, mutation = name, started
            replace_three(paths, old, new, progress)
            phase = "FORCE_RECREATE"
            require(immutable_state(spec, "wildcard") == frozen, "PRE_RECREATE_DRIFT")
            argv = spec["phases"][4]["argv"]
            require(argv == FROZEN_ARGV, "RECREATE_ARGV_DRIFT")
            mutation = True
            command(argv, timeout=240)
            phase = "POSTVERIFY_LOCAL"
            result = container_state()
            require(result["image"] == frozen and result["healthy"] and result["volume"]
                    and result["bind"] == "loopback" and listener_loopback(),
                    "POST_CONTAINMENT_DRIFT")
            require(health("health") and health("ready"), "HEALTH_DRIFT")
            return {"result": "LOCAL_PASS_PHASE7_PENDING", "phase": phase,
                    "mutation_performed": True}
    except (Blocked, OSError, ValueError, KeyError, TypeError, KeyboardInterrupt):
        return {"result": "STOP" if mutation else "BLOCKED", "phase": phase,
                "mutation_performed": mutation}


FROZEN_ARGV = [
    "/usr/bin/docker", "compose", "--project-name", "rozkalns-weather-public",
    "--file", "/etc/rozkalns-simple-deployer/compose/rozkalns-weather-public.yml",
    "--file", "/var/lib/rozkalns-simple-deployer/overrides/rozkalns-weather-public-rpi5.yaml",
    "up", "--detach", "--no-deps", "--force-recreate", "--pull", "never",
    "--wait", "--wait-timeout", "180", "weather",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-main", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    args = parser.parse_args()
    if args.apply and args.confirm != "REBIND-WEATHER-PUBLIC-915":
        parser.error("fixed confirmation required")
    if not args.apply and args.confirm is not None:
        parser.error("confirmation valid only with apply")
    outcome = execute(args.expected_main, apply=args.apply)
    print(json.dumps(outcome, sort_keys=True))
    return 0 if outcome["result"] in ("PASS", "LOCAL_PASS_PHASE7_PENDING") else (3 if outcome["result"] == "BLOCKED" else 4)


if __name__ == "__main__":
    sys.exit(main())
