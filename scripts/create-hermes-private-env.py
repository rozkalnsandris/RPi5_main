#!/usr/bin/env python3
"""Fixed Hermes env-child preparation; apply requires separate exact LIVE authority."""
from __future__ import annotations

import argparse
import ctypes
import fcntl
import grp
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import resource
import stat
import subprocess
import sys
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/create-hermes-private-env.py"
CONTRACT = "ops/contracts/hermes-private-env-child-v1.json"
PARENT = Path("/etc/rozkalns-simple-deployer/private")
CHILD = "hermes-deals-api.env"
STAGE = ".hermes-deals-api.env.child-v1.staged"
LEGACY_STAGE = ".hermes-deals-api.env.prerequisites-v1.staged"
PRINCIPAL = "rozkalns-simple-deployer"
MAX_BYTES = 65536
PROPERTIES = ("LoadState", "User", "Group", "SupplementaryGroups", "DynamicUser")

spec = importlib.util.spec_from_file_location(
    "hermes_env_v4", ROOT / "scripts/materialize-simple-deploy-hermes-prerequisites-v4.py"
)
assert spec and spec.loader
v4 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v4
spec.loader.exec_module(v4)
v3 = v4.v3


class Stop(Exception):
    """Never expose underlying exception messages or protected values."""


def require(condition):
    if not condition:
        raise Stop()


def source_check(sha):
    v4._require_frozen_source(sha)
    for relative in (SCRIPT, CONTRACT, v4.legacy.SCRIPT_RELATIVE,
                     v4.legacy.CONTRACT_RELATIVE):
        require(v3._git_stdout_readonly("show", f"{sha}:{relative}") ==
                (ROOT / relative).read_bytes())
    require(json.loads((ROOT / CONTRACT).read_text()) == contract())


def contract():
    return {
        "schema": "hermes.private-env-child.v1", "issue": 984,
        "entrypoint": SCRIPT, "parent": str(PARENT), "child": CHILD,
        "stage": STAGE, "legacy_stage_must_be_absent": LEGACY_STAGE,
        "source": "passwd(andris).home/hermes-deals/.env",
        "source_max_bytes": MAX_BYTES,
        "source_keys": list(v3.SOURCE_ENV_KEYS),
        "destination_keys": list(v3.DESTINATION_ENV_KEYS),
        "parent_mode": "0750", "child_mode": "0640",
        "parent_owner": "root", "child_owner": "root", "group": PRINCIPAL,
        "parent_mutation_allowed": False, "overwrite_allowed": False,
        "default_protected_read": False, "default_mutation": False,
        "apply_requires_separate_live_authorization": True,
        "activation_eligible": False, "compose_runtime_access": "NOT_PROVEN",
        "retry": False, "rollback": False, "error_cleanup": False,
    }


def no_acl(fd):
    require(not {"system.posix_acl_access", "system.posix_acl_default"}
            .intersection(os.listxattr(fd)))


@contextmanager
def directory(path, owners):
    """Walk from / using pinned descriptors; reject every symlink/writable ancestor."""
    require(path.is_absolute() and ".." not in path.parts)
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:]:
            st = os.fstat(fd)
            require(st.st_uid in owners and not stat.S_IMODE(st.st_mode) & 0o022)
            no_acl(fd)
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW |
                            os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = child
        st = os.fstat(fd)
        require(st.st_uid in owners and not stat.S_IMODE(st.st_mode) & 0o022)
        no_acl(fd)
        yield fd
    finally:
        os.close(fd)


def identity(st):
    return st.st_dev, st.st_ino, st.st_uid, st.st_gid, st.st_mode


def fingerprint(st):
    return (*identity(st), st.st_size, st.st_nlink, st.st_mtime_ns, st.st_ctime_ns)


def absent(fd, name):
    try:
        os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return True
    return False


def parent_check(fd, gid, *, root_uid=0):
    st = os.fstat(fd)
    require(stat.S_ISDIR(st.st_mode) and st.st_uid == root_uid and st.st_gid == gid
            and stat.S_IMODE(st.st_mode) == 0o750)
    no_acl(fd)
    return identity(st)


def file_check(st, uid, gid, mode):
    require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == uid
            and st.st_gid == gid and stat.S_IMODE(st.st_mode) == mode)


def runtime_identity():
    account = pwd.getpwnam(PRINCIPAL)
    group = grp.getgrnam(PRINCIPAL)
    docker = grp.getgrnam("docker")
    require(account.pw_uid != 0 and group.gr_gid != 0 and docker.gr_gid != 0
            and docker.gr_gid != group.gr_gid and account.pw_gid == group.gr_gid
            and v4._exclusive_runtime_group(PRINCIPAL, group.gr_gid))
    response = subprocess.run(
        ["/usr/bin/systemctl", "show", PRINCIPAL + ".service", "--no-pager",
         *["--property=" + p for p in PROPERTIES]],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False, timeout=10,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
    )
    require(response.returncode == 0)
    values = dict(line.split("=", 1) for line in response.stdout.decode().splitlines()
                  if "=" in line)
    require(values == {"LoadState": "loaded", "User": PRINCIPAL, "Group": PRINCIPAL,
                       "SupplementaryGroups": "docker", "DynamicUser": "no"})
    return account.pw_uid, group.gr_gid, docker.gr_gid


def project(raw):
    values = v3._extract_source_env(raw)
    # Preserve the reviewed v3 URL template; never silently reinterpret URI delimiters.
    for key in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        require(re.fullmatch(r"[A-Za-z0-9._~-]+", values[key]) is not None)
    return v3._derive_destination_env(values)


def read_source(fd, uid, gid, receipt):
    before = os.stat(".env", dir_fd=fd, follow_symlinks=False)
    file_check(before, uid, gid, 0o600)
    require(0 < before.st_size <= MAX_BYTES)
    child = os.open(".env", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                    os.O_CLOEXEC, dir_fd=fd)
    try:
        require(fingerprint(os.fstat(child)) == fingerprint(before))
        no_acl(child)
        receipt["protected_read_started"] = True
        chunks, size = [], 0
        while True:
            chunk = os.read(child, min(4096, MAX_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            require(size <= MAX_BYTES)
        require(fingerprint(os.fstat(child)) == fingerprint(before))
        require(fingerprint(os.stat(".env", dir_fd=fd, follow_symlinks=False)) ==
                fingerprint(before))
        return project(b"".join(chunks)), fingerprint(before)
    finally:
        os.close(child)


def rename_no_replace(fd):
    rename = ctypes.CDLL(None, use_errno=True).renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                       ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    require(rename(fd, STAGE.encode(), fd, CHILD.encode(), 1) == 0)


def publish(fd, data, gid, revalidate, receipt, *, root_uid=0):
    require(absent(fd, CHILD) and absent(fd, STAGE) and absent(fd, LEGACY_STAGE))
    # Mark the attempt conservatively before O_EXCL: an interrupted syscall is ambiguous.
    receipt["mutation_attempted"] = True
    stage = os.open(STAGE, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW |
                    os.O_CLOEXEC, 0o600, dir_fd=fd)
    try:
        os.fchown(stage, root_uid, gid)
        os.fchmod(stage, 0o600)
        no_acl(stage)
        remaining = memoryview(data)
        while remaining:
            written = os.write(stage, remaining)
            require(written > 0)
            remaining = remaining[written:]
        os.fsync(stage)
        revalidate()
        require(fingerprint(os.stat(STAGE, dir_fd=fd, follow_symlinks=False)) ==
                fingerprint(os.fstat(stage)))
        file_check(os.fstat(stage), root_uid, gid, 0o600)
        os.fchmod(stage, 0o640)
        os.fsync(stage)
        rename_no_replace(fd)
        receipt["published"] = True
        os.fsync(fd)
        final = os.stat(CHILD, dir_fd=fd, follow_symlinks=False)
        file_check(final, root_uid, gid, 0o640)
        require(fingerprint(final) == fingerprint(os.fstat(stage)))
        require(absent(fd, STAGE))
    finally:
        # Deliberately no unlink/rollback. Partial stage or published child is evidence.
        os.close(stage)


def dac_readable(uid, gid, docker_gid):
    child = os.fork()
    if child == 0:
        try:
            os.setgroups([docker_gid])
            os.setgid(gid)
            os.setuid(uid)
            os._exit(0 if os.access(PARENT / CHILD, os.R_OK, effective_ids=True) else 1)
        except BaseException:
            os._exit(2)
    _, result = os.waitpid(child, 0)
    require(result == 0)


def execute(sha, apply, receipt):
    require(os.geteuid() == 0)
    source_check(sha)
    runtime = runtime_identity()
    source = pwd.getpwnam("andris")
    require(source.pw_uid != 0)
    source_dir = Path(source.pw_dir) / "hermes-deals"
    with directory(PARENT, {0}) as parent:
        fcntl.flock(parent, fcntl.LOCK_EX | fcntl.LOCK_NB)
        original_parent = parent_check(parent, runtime[1])
        require(absent(parent, CHILD) and absent(parent, STAGE) and absent(parent, LEGACY_STAGE))
        with directory(source_dir, {0, source.pw_uid}) as src:
            original_source = identity(os.fstat(src))
            st = os.stat(".env", dir_fd=src, follow_symlinks=False)
            file_check(st, source.pw_uid, source.pw_gid, 0o600)
            require(0 < st.st_size <= MAX_BYTES)
            if not apply:
                receipt["status"] = "ABSENT_METADATA_ONLY"
                return
            # No protected content read before all metadata/identity/source checks above.
            data, source_fp = read_source(src, source.pw_uid, source.pw_gid, receipt)

            def revalidate():
                source_check(sha)
                require(runtime_identity() == runtime)
                with directory(PARENT, {0}) as fresh_parent:
                    require(parent_check(fresh_parent, runtime[1]) == original_parent)
                with directory(source_dir, {0, source.pw_uid}) as fresh_source:
                    require(identity(os.fstat(fresh_source)) == original_source)
                    require(fingerprint(os.stat(".env", dir_fd=fresh_source,
                                                follow_symlinks=False)) == source_fp)
                require(absent(parent, CHILD) and absent(parent, LEGACY_STAGE))

            revalidate()
            publish(parent, data, runtime[1], revalidate, receipt)
        require(runtime_identity() == runtime)
        with directory(PARENT, {0}) as fresh:
            require(parent_check(fresh, runtime[1]) == original_parent)
        final = os.stat(CHILD, dir_fd=parent, follow_symlinks=False)
        dac_readable(*runtime)
        require(fingerprint(os.stat(CHILD, dir_fd=parent, follow_symlinks=False)) ==
                fingerprint(final))
        require(runtime_identity() == runtime)
        with directory(PARENT, {0}) as fresh:
            require(parent_check(fresh, runtime[1]) == original_parent)
        receipt["consumer_dac"] = "DAC_READABLE"
        receipt["status"] = "CHILD_CREATED"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--apply", action="store_true",
                        help="Requires separate exact owner protected-read/creation authority")
    args = parser.parse_args(argv)
    receipt = {"schema": "hermes.private-env-child.result.v1", "status": "ERROR_STOP",
               "protected_read_started": False, "protected_values_emitted": False,
               "mutation_attempted": False, "published": False,
               "consumer_dac": "NOT_RUN", "compose_runtime_access": "NOT_PROVEN",
               "activation_eligible": False}
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        execute(args.expected_source_sha, args.apply, receipt)
    except (Exception, KeyboardInterrupt):
        # Includes parser/projection, OS, Git, NSS, subprocess and interrupted failures.
        # No exception text, source bytes, hashes of secrets or raw property output.
        print(json.dumps(receipt, sort_keys=True))
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
