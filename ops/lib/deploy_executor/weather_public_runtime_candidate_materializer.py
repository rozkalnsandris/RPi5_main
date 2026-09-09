from __future__ import annotations

import ctypes
from dataclasses import dataclass
import errno
import grp
import os
from pathlib import Path
import pwd
import re
import stat
from typing import Callable, Protocol, Sequence

from .weather_public_runtime_adapter import SOURCE_REPOSITORY
from .weather_public_runtime_execution import RELEASE_ROOT

PUBLIC_REPOSITORY_URL = "https://github.com/rozkalnsandris/rozkalns_weather.git"
FETCH_IDENTITY = "rozkalns-deploy-executor"
FETCH_GROUP = "rozkalns-deploy-executor"
PARTIAL_SUFFIX = ".release-materializer-partial"
ROOT_UID = 0
ROOT_GID = 0
ROOT_DIRECTORY_MODE = 0o755
BUILD_DIRECTORY_MODE = 0o700
FINAL_DIRECTORY_MODE = 0o555
FINAL_FILE_MODE = 0o444
FINAL_EXECUTABLE_MODE = 0o555
RENAME_NOREPLACE = 1
MAX_COMMAND_OUTPUT_BYTES = 65536
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")


class WeatherCandidateMaterializerError(RuntimeError):
    pass


class CommandResultLike(Protocol):
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[Sequence[str]], CommandResultLike]


@dataclass(frozen=True)
class CandidateMaterializationPlan:
    source_repository: str
    source_sha: str
    public_repository_url: str
    fetch_identity: str
    release_root: str
    partial_root: str
    clone_argv: tuple[str, ...]
    ancestry_argv: tuple[str, ...]
    checkout_argv: tuple[str, ...]


def _fail(message: str) -> None:
    raise WeatherCandidateMaterializerError(message)


def _fixed_git_prefix() -> tuple[str, ...]:
    return (
        "/usr/sbin/runuser",
        "-u",
        FETCH_IDENTITY,
        "--",
        "/usr/bin/env",
        "-i",
        "PATH=/usr/bin:/bin",
        "LANG=C.UTF-8",
        "LC_ALL=C.UTF-8",
        "HOME=/nonexistent",
        "GIT_TERMINAL_PROMPT=0",
        "GIT_CONFIG_NOSYSTEM=1",
        "/usr/bin/git",
    )


def build_candidate_materialization_plan(source_sha: str) -> CandidateMaterializationPlan:
    if type(source_sha) is not str or _SHA40_RE.fullmatch(source_sha) is None:
        _fail("Weather release source SHA is invalid")
    base = Path(RELEASE_ROOT)
    release = base / source_sha
    partial = base / f".{source_sha}{PARTIAL_SUFFIX}"
    prefix = _fixed_git_prefix()
    clone = prefix + (
        "clone",
        "--no-tags",
        "--no-checkout",
        PUBLIC_REPOSITORY_URL,
        str(partial),
    )
    ancestry = prefix + (
        "-C",
        str(partial),
        "merge-base",
        "--is-ancestor",
        source_sha,
        "refs/remotes/origin/main",
    )
    checkout = prefix + (
        "-C",
        str(partial),
        "checkout",
        "--detach",
        source_sha,
    )
    return CandidateMaterializationPlan(
        source_repository=SOURCE_REPOSITORY,
        source_sha=source_sha,
        public_repository_url=PUBLIC_REPOSITORY_URL,
        fetch_identity=FETCH_IDENTITY,
        release_root=str(release),
        partial_root=str(partial),
        clone_argv=clone,
        ancestry_argv=ancestry,
        checkout_argv=checkout,
    )


def _require_success(runner: CommandRunner, argv: Sequence[str], where: str) -> str:
    result = runner(tuple(argv))
    if not hasattr(result, "returncode") or result.returncode != 0:
        _fail(f"Weather release {where} failed closed")
    stdout = getattr(result, "stdout", None)
    stderr = getattr(result, "stderr", None)
    if type(stdout) is not str or type(stderr) is not str:
        _fail(f"Weather release {where} returned unsupported output")
    if len(stdout.encode("utf-8")) > MAX_COMMAND_OUTPUT_BYTES or len(stderr.encode("utf-8")) > MAX_COMMAND_OUTPUT_BYTES:
        _fail(f"Weather release {where} output exceeded source limit")
    return stdout


def _mode(st: os.stat_result) -> int:
    return stat.S_IMODE(st.st_mode)


def _assert_root_dir(path: Path, label: str) -> None:
    try:
        st = path.lstat()
    except OSError as exc:
        raise WeatherCandidateMaterializerError(f"{label} lstat failed") from exc
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != ROOT_UID or st.st_gid != ROOT_GID or _mode(st) != ROOT_DIRECTORY_MODE:
        _fail(f"{label} metadata drifted")


def _ensure_root_dir(path: Path, label: str) -> None:
    try:
        path.lstat()
    except FileNotFoundError:
        try:
            path.mkdir(mode=ROOT_DIRECTORY_MODE)
            os.chown(path, ROOT_UID, ROOT_GID)
            os.chmod(path, ROOT_DIRECTORY_MODE)
        except OSError as exc:
            raise WeatherCandidateMaterializerError(f"{label} creation failed") from exc
    except OSError as exc:
        raise WeatherCandidateMaterializerError(f"{label} lstat failed") from exc
    _assert_root_dir(path, label)


def _path_absent(path: Path, label: str) -> None:
    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise WeatherCandidateMaterializerError(f"{label} lstat failed") from exc
    _fail(f"{label} already exists; implicit reuse or retry is forbidden")


def _identity_ids() -> tuple[int, int]:
    try:
        uid = pwd.getpwnam(FETCH_IDENTITY).pw_uid
        gid = grp.getgrnam(FETCH_GROUP).gr_gid
    except KeyError as exc:
        raise WeatherCandidateMaterializerError("fixed deploy-executor identity is unavailable") from exc
    return uid, gid


def _lock_tree(root: Path) -> None:
    try:
        st = root.lstat()
    except OSError as exc:
        raise WeatherCandidateMaterializerError("Weather release partial lstat failed") from exc
    if not stat.S_ISDIR(st.st_mode):
        _fail("Weather release partial is not a directory")
    try:
        os.chown(root, ROOT_UID, ROOT_GID)
        os.chmod(root, BUILD_DIRECTORY_MODE)
    except OSError as exc:
        raise WeatherCandidateMaterializerError("Weather release partial root lock failed") from exc

    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in dirnames:
            child = current_path / name
            st = child.lstat()
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
                _fail("Weather release contains a symlink or non-directory tree entry")
            os.chown(child, ROOT_UID, ROOT_GID)
            os.chmod(child, BUILD_DIRECTORY_MODE)
        for name in filenames:
            child = current_path / name
            st = child.lstat()
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
                _fail("Weather release contains a symlink or special file")
            executable = bool(_mode(st) & 0o111)
            os.chown(child, ROOT_UID, ROOT_GID)
            os.chmod(child, FINAL_EXECUTABLE_MODE if executable else FINAL_FILE_MODE)

    for current, _dirnames, _filenames in os.walk(root, topdown=False, followlinks=False):
        os.chmod(current, FINAL_DIRECTORY_MODE)
        os.chown(current, ROOT_UID, ROOT_GID)


def _validate_locked_release(release: Path, source_sha: str, runner: CommandRunner) -> None:
    head = _require_success(
        runner,
        ("/usr/bin/git", "--no-optional-locks", "-C", str(release), "rev-parse", "HEAD"),
        "locked HEAD validation",
    ).strip()
    if head != source_sha:
        _fail("Weather release locked HEAD drifted")

    _require_success(
        runner,
        (
            "/usr/bin/git",
            "--no-optional-locks",
            "-C",
            str(release),
            "merge-base",
            "--is-ancestor",
            source_sha,
            "refs/remotes/origin/main",
        ),
        "locked main ancestry validation",
    )

    status_out = _require_success(
        runner,
        (
            "/usr/bin/git",
            "--no-optional-locks",
            "-C",
            str(release),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ),
        "locked cleanliness validation",
    )
    if status_out:
        _fail("Weather release locked tree is not clean")

    stage_out = _require_success(
        runner,
        ("/usr/bin/git", "--no-optional-locks", "-C", str(release), "ls-files", "--stage"),
        "locked tracked-mode validation",
    )
    tracked = 0
    for raw_line in stage_out.splitlines():
        if not raw_line:
            continue
        mode = raw_line.split(" ", 1)[0]
        if mode not in {"100644", "100755"}:
            _fail("Weather release symlink, gitlink, or unsupported tracked mode is forbidden")
        tracked += 1
    if tracked == 0:
        _fail("Weather release contains no tracked files")


def _rename_noreplace(base: Path, source_name: str, destination_name: str) -> None:
    try:
        base_fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise WeatherCandidateMaterializerError("Weather release base open failed") from exc
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            _fail("Weather release atomic publish requires renameat2")
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        result = renameat2(
            base_fd,
            os.fsencode(source_name),
            base_fd,
            os.fsencode(destination_name),
            RENAME_NOREPLACE,
        )
        if result != 0:
            err = ctypes.get_errno()
            if err == errno.EEXIST:
                _fail("Weather release target appeared before atomic publish")
            raise OSError(err, os.strerror(err), destination_name)
        os.fsync(base_fd)
    finally:
        os.close(base_fd)


def materialize_candidate(source_sha: str, runner: CommandRunner) -> Path:
    """Materialize exactly one immutable release checkout; the historical name is kept for API compatibility."""

    plan = build_candidate_materialization_plan(source_sha)
    base = Path(RELEASE_ROOT)
    parent = base.parent
    release = Path(plan.release_root)
    partial = Path(plan.partial_root)

    _ensure_root_dir(parent, "Weather release namespace")
    _ensure_root_dir(base, "Weather release root")
    _path_absent(release, "Weather release target")
    _path_absent(partial, "Weather release partial")

    fetch_uid, fetch_gid = _identity_ids()
    try:
        partial.mkdir(mode=BUILD_DIRECTORY_MODE)
        os.chown(partial, fetch_uid, fetch_gid)
        os.chmod(partial, BUILD_DIRECTORY_MODE)
    except OSError as exc:
        raise WeatherCandidateMaterializerError("Weather release partial creation failed") from exc

    _require_success(runner, plan.clone_argv, "public repository clone")
    _require_success(runner, plan.ancestry_argv, "source ancestry")
    _require_success(runner, plan.checkout_argv, "exact source checkout")

    _lock_tree(partial)
    _validate_locked_release(partial, source_sha, runner)
    _rename_noreplace(base, partial.name, release.name)
    _validate_locked_release(release, source_sha, runner)
    return release


def source_readiness() -> dict[str, object]:
    return {
        "source_repository": SOURCE_REPOSITORY,
        "public_repository_url": PUBLIC_REPOSITORY_URL,
        "fetch_identity": FETCH_IDENTITY,
        "release_root": RELEASE_ROOT,
        "release_path_source_derived_only": True,
        "network_fetch_runs_as_root": False,
        "credentialed_fetch_required": False,
        "source_sha_main_ancestry_required": True,
        "symlinks_allowed": False,
        "gitlinks_allowed": False,
        "atomic_publish": "renameat2-RENAME_NOREPLACE",
        "filesystem_release_materializations": 1,
        "preexisting_release_reuse": False,
        "automatic_retry": False,
        "automatic_cleanup": False,
        "automatic_rollback": False,
        "caller_supplied_repository_url": False,
        "caller_supplied_path": False,
        "caller_supplied_argv": False,
        "caller_supplied_environment": False,
    }
