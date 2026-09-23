from __future__ import annotations

import ctypes
from dataclasses import dataclass
import errno
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Callable, Literal, Mapping, Protocol, Sequence

SOURCE_REPOSITORY = "rozkalnsandris/rozkalns_weather"
REVIEWED_ORIGIN = "https://github.com/rozkalnsandris/rozkalns_weather.git"
OPERATION_ID = "rpi5.weathernext-private-application-stage.v1"
TARGET_ALIAS = "rpi5-weathernext-private-application-stage"
STAGE_ID = "rozkalns-weather.weathernext-private-application-stage.v1"
STAGE_ROOT = Path("/var/lib/rpi5-deploy/weather-private-application")
MARKER = STAGE_ROOT / "source-stage.json"
ROLLBACK_POLICY = "NONE"
ROOT_UID = 0
ROOT_GID = 0
STAGE_ROOT_MODE = 0o755
MARKER_MODE = 0o644
MAX_COMMAND_OUTPUT_BYTES = 64 * 1024
_RENAME_NOREPLACE = 1
_SHA40 = re.compile(r"^[0-9a-f]{40}$")

MUTATION_BUDGET = (
    ("git.weathernext-private-application-stage-clone-checkout", 1),
    ("filesystem.weathernext-private-application-stage-marker-write", 1),
    ("filesystem.weathernext-private-application-stage-publish", 1),
)

REQUIRED_EXCLUSIONS = (
    "no private runtime materialization",
    "no Google auth or project binding",
    "no Analytics Hub link mutation",
    "no BigQuery access",
    "no SQLite or corpus write",
    "no Docker or systemd mutation",
    "no package manager or network-control mutation",
    "no generic shell path argv or environment authority",
    "no automatic retry cleanup or rollback",
)

StageState = Literal["ABSENT", "EXACT", "CONFLICT"]


class WeatherNextPrivateApplicationStageError(RuntimeError):
    pass


class CommandResultLike(Protocol):
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[Sequence[str]], CommandResultLike]


@dataclass(frozen=True)
class ApplicationStageEvidence:
    exact_weather_source_sha: str
    current_weather_main_sha: str
    exact_main_ci_success: bool
    stage_present: bool
    partial_present: bool
    stage_uid: int | None = None
    stage_gid: int | None = None
    stage_mode: int | None = None
    marker_exact: bool = False
    git_origin: str | None = None
    git_head_sha: str | None = None
    git_detached: bool = False
    tracked_clean: bool = False


@dataclass(frozen=True)
class StageStep:
    category: str
    maximum: int
    target: str
    invariant: str


@dataclass(frozen=True)
class ApplicationStagePlan:
    operation_id: str
    target_alias: str
    source_repository: str
    source_sha: str
    reviewed_origin: str
    stage_root: str
    marker: str
    prior_state: StageState
    steps: tuple[StageStep, ...]
    rollback_policy: str = ROLLBACK_POLICY
    authorization_consumed_before_first_mutation: bool = True
    automatic_retry: bool = False
    automatic_cleanup: bool = False
    automatic_rollback: bool = False
    runtime_materialization_allowed: bool = False
    google_action_allowed: bool = False
    bigquery_action_allowed: bool = False
    sqlite_write_allowed: bool = False


def _fail(message: str) -> None:
    raise WeatherNextPrivateApplicationStageError(message)


def _valid_sha(value: str | None) -> bool:
    return isinstance(value, str) and _SHA40.fullmatch(value) is not None


def marker_value(source_sha: str) -> dict[str, object]:
    if not _valid_sha(source_sha):
        _fail("Weather application stage source SHA is invalid")
    return {
        "schema": STAGE_ID,
        "source_repository": SOURCE_REPOSITORY,
        "source_sha": source_sha,
        "staged": True,
    }


def classify_application_stage(evidence: ApplicationStageEvidence) -> StageState:
    if not _valid_sha(evidence.exact_weather_source_sha):
        _fail("exact Weather source SHA is invalid")
    if evidence.current_weather_main_sha != evidence.exact_weather_source_sha:
        _fail("Weather source/head drifted from exact current main")
    if not evidence.exact_main_ci_success:
        _fail("Weather exact-main required CI is not successful")
    if evidence.partial_present:
        return "CONFLICT"
    if not evidence.stage_present:
        return "ABSENT"
    exact = (
        evidence.stage_uid == ROOT_UID
        and evidence.stage_gid == ROOT_GID
        and evidence.stage_mode == STAGE_ROOT_MODE
        and evidence.marker_exact
        and evidence.git_origin == REVIEWED_ORIGIN
        and evidence.git_head_sha == evidence.exact_weather_source_sha
        and evidence.git_detached
        and evidence.tracked_clean
    )
    return "EXACT" if exact else "CONFLICT"


def build_stage_plan(evidence: ApplicationStageEvidence) -> ApplicationStagePlan:
    state = classify_application_stage(evidence)
    if state == "CONFLICT":
        _fail("Weather private application stage conflicts with reviewed fixed state")
    if state == "EXACT":
        return ApplicationStagePlan(
            operation_id=OPERATION_ID,
            target_alias=TARGET_ALIAS,
            source_repository=SOURCE_REPOSITORY,
            source_sha=evidence.exact_weather_source_sha,
            reviewed_origin=REVIEWED_ORIGIN,
            stage_root=str(STAGE_ROOT),
            marker=str(MARKER),
            prior_state=state,
            steps=(),
        )
    partial = STAGE_ROOT.parent / f".{STAGE_ROOT.name}.{evidence.exact_weather_source_sha}.partial"
    steps = (
        StageStep(
            category=MUTATION_BUDGET[0][0],
            maximum=1,
            target=str(partial),
            invariant="clone only reviewed Weather origin/main and detach exact authorized current-main SHA",
        ),
        StageStep(
            category=MUTATION_BUDGET[1][0],
            maximum=1,
            target=str(partial / MARKER.name),
            invariant="write only the fixed public-safe source-stage marker root:root 0644",
        ),
        StageStep(
            category=MUTATION_BUDGET[2][0],
            maximum=1,
            target=str(STAGE_ROOT),
            invariant="publish only by no-replace rename when the fixed final stage root is absent",
        ),
    )
    return ApplicationStagePlan(
        operation_id=OPERATION_ID,
        target_alias=TARGET_ALIAS,
        source_repository=SOURCE_REPOSITORY,
        source_sha=evidence.exact_weather_source_sha,
        reviewed_origin=REVIEWED_ORIGIN,
        stage_root=str(STAGE_ROOT),
        marker=str(MARKER),
        prior_state=state,
        steps=steps,
    )


def public_plan(plan: ApplicationStagePlan) -> dict[str, object]:
    return {
        "operation_id": plan.operation_id,
        "target_alias": plan.target_alias,
        "source_repository": plan.source_repository,
        "source_sha": plan.source_sha,
        "reviewed_origin": plan.reviewed_origin,
        "stage_root": plan.stage_root,
        "marker": plan.marker,
        "prior_state": plan.prior_state,
        "mutation_budget": [
            {"category": step.category, "max_operations": step.maximum}
            for step in plan.steps
        ],
        "rollback_policy": plan.rollback_policy,
        "authorization_consumed_before_first_mutation": plan.authorization_consumed_before_first_mutation,
        "automatic_retry": plan.automatic_retry,
        "automatic_cleanup": plan.automatic_cleanup,
        "automatic_rollback": plan.automatic_rollback,
        "runtime_materialization_allowed": plan.runtime_materialization_allowed,
        "google_action_allowed": plan.google_action_allowed,
        "bigquery_action_allowed": plan.bigquery_action_allowed,
        "sqlite_write_allowed": plan.sqlite_write_allowed,
    }


def _fixed_git_prefix() -> tuple[str, ...]:
    return (
        "/usr/bin/env",
        "-i",
        "PATH=/usr/bin:/bin",
        "LANG=C.UTF-8",
        "LC_ALL=C.UTF-8",
        "HOME=/nonexistent",
        "GIT_TERMINAL_PROMPT=0",
        "GIT_CONFIG_NOSYSTEM=1",
        "/usr/bin/git",
        "--no-optional-locks",
    )


def _default_runner(argv: Sequence[str]) -> CommandResultLike:
    return subprocess.run(
        tuple(argv),
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def _run(runner: CommandRunner, argv: Sequence[str], where: str, *, accepted_codes: tuple[int, ...] = (0,)) -> str:
    result = runner(tuple(argv))
    if not hasattr(result, "returncode") or result.returncode not in accepted_codes:
        _fail(f"Weather application stage {where} failed closed")
    stdout = getattr(result, "stdout", None)
    stderr = getattr(result, "stderr", None)
    if type(stdout) is not str or type(stderr) is not str:
        _fail(f"Weather application stage {where} returned unsupported output")
    if len(stdout.encode()) > MAX_COMMAND_OUTPUT_BYTES or len(stderr.encode()) > MAX_COMMAND_OUTPUT_BYTES:
        _fail(f"Weather application stage {where} output exceeded source limit")
    return stdout


def _marker_exact(path: Path, source_sha: str) -> bool:
    try:
        st = path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        _fail("Weather application stage marker metadata failed")
    if (
        not stat.S_ISREG(st.st_mode)
        or st.st_nlink != 1
        or st.st_uid != ROOT_UID
        or st.st_gid != ROOT_GID
        or stat.S_IMODE(st.st_mode) != MARKER_MODE
        or not 0 < st.st_size <= 4096
    ):
        return False
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        try:
            raw = os.read(fd, 4097)
        finally:
            os.close(fd)
        value = json.loads(raw.decode("utf-8", "strict"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return value == marker_value(source_sha)


def _rename_noreplace(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        _fail("renameat2 is required for no-replace stage publication")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    rc = renameat2(
        -100,
        os.fsencode(source),
        -100,
        os.fsencode(destination),
        _RENAME_NOREPLACE,
    )
    if rc != 0:
        err = ctypes.get_errno()
        if err in {errno.EEXIST, errno.ENOTEMPTY}:
            _fail("fixed Weather application stage destination already exists")
        raise WeatherNextPrivateApplicationStageError("Weather application stage publication failed") from OSError(err, os.strerror(err))


class PosixApplicationStageBackend:
    def __init__(self, *, runner: CommandRunner = _default_runner):
        self._runner = runner

    def observe(self, source_sha: str, *, current_main_sha: str, exact_main_ci_success: bool) -> ApplicationStageEvidence:
        if not _valid_sha(source_sha):
            _fail("Weather application stage source SHA is invalid")
        partial = STAGE_ROOT.parent / f".{STAGE_ROOT.name}.{source_sha}.partial"
        partial_present = partial.exists() or partial.is_symlink()
        try:
            st = STAGE_ROOT.lstat()
        except FileNotFoundError:
            return ApplicationStageEvidence(
                exact_weather_source_sha=source_sha,
                current_weather_main_sha=current_main_sha,
                exact_main_ci_success=exact_main_ci_success,
                stage_present=False,
                partial_present=partial_present,
            )
        except OSError:
            _fail("Weather application stage root metadata failed")
        if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
            return ApplicationStageEvidence(
                source_sha, current_main_sha, exact_main_ci_success, True, partial_present,
                st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode), False,
            )
        prefix = _fixed_git_prefix()
        origin = _run(
            self._runner,
            prefix + ("-C", str(STAGE_ROOT), "config", "--get", "remote.origin.url"),
            "origin observation",
        ).strip()
        head = _run(
            self._runner,
            prefix + ("-C", str(STAGE_ROOT), "rev-parse", "HEAD"),
            "HEAD observation",
        ).strip()
        branch = _run(
            self._runner,
            prefix + ("-C", str(STAGE_ROOT), "rev-parse", "--abbrev-ref", "HEAD"),
            "detached observation",
        ).strip()
        tracked = _run(
            self._runner,
            prefix + ("-C", str(STAGE_ROOT), "status", "--porcelain", "--untracked-files=no"),
            "tracked-clean observation",
        )
        return ApplicationStageEvidence(
            exact_weather_source_sha=source_sha,
            current_weather_main_sha=current_main_sha,
            exact_main_ci_success=exact_main_ci_success,
            stage_present=True,
            partial_present=partial_present,
            stage_uid=st.st_uid,
            stage_gid=st.st_gid,
            stage_mode=stat.S_IMODE(st.st_mode),
            marker_exact=_marker_exact(MARKER, source_sha),
            git_origin=origin,
            git_head_sha=head,
            git_detached=branch == "HEAD",
            tracked_clean=tracked == "",
        )

    def apply(self, plan: ApplicationStagePlan) -> Mapping[str, object]:
        if os.geteuid() != 0:
            _fail("Weather application stage mutation requires root boundary")
        if plan.operation_id != OPERATION_ID or plan.target_alias != TARGET_ALIAS:
            _fail("Weather application stage plan identity drifted")
        if plan.source_repository != SOURCE_REPOSITORY or plan.reviewed_origin != REVIEWED_ORIGIN:
            _fail("Weather application stage source identity drifted")
        if plan.prior_state == "EXACT":
            if plan.steps:
                _fail("exact application stage cannot contain mutations")
            return {
                "status": "ALREADY_EXACT",
                "source_sha": plan.source_sha,
                "production_mutation_started": False,
                "mutation_categories": [],
            }
        if plan.prior_state != "ABSENT" or tuple((s.category, s.maximum) for s in plan.steps) != MUTATION_BUDGET:
            _fail("Weather application stage mutation budget drifted")

        parent = STAGE_ROOT.parent
        try:
            parent_st = parent.lstat()
        except OSError:
            _fail("Weather application stage parent is unavailable")
        if not stat.S_ISDIR(parent_st.st_mode) or stat.S_ISLNK(parent_st.st_mode) or parent_st.st_uid != 0 or parent_st.st_gid != 0:
            _fail("Weather application stage parent metadata drifted")
        partial = Path(plan.steps[0].target)
        if partial.exists() or partial.is_symlink() or STAGE_ROOT.exists() or STAGE_ROOT.is_symlink():
            _fail("Weather application stage target changed before mutation")

        prefix = _fixed_git_prefix()
        _run(
            self._runner,
            prefix + (
                "clone", "--single-branch", "--branch", "main", "--no-tags", "--no-checkout",
                REVIEWED_ORIGIN, str(partial),
            ),
            "fixed clone",
        )
        _run(
            self._runner,
            prefix + ("-C", str(partial), "merge-base", "--is-ancestor", plan.source_sha, "refs/remotes/origin/main"),
            "authorized ancestry",
        )
        _run(
            self._runner,
            prefix + ("-C", str(partial), "checkout", "--detach", plan.source_sha),
            "exact checkout",
        )
        try:
            os.chown(partial, ROOT_UID, ROOT_GID)
            os.chmod(partial, STAGE_ROOT_MODE)
            marker = partial / MARKER.name
            fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0), MARKER_MODE)
            try:
                raw = (json.dumps(marker_value(plan.source_sha), sort_keys=True, separators=(",", ":")) + "\n").encode()
                os.write(fd, raw)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.chown(marker, ROOT_UID, ROOT_GID)
            os.chmod(marker, MARKER_MODE)
        except OSError as exc:
            raise WeatherNextPrivateApplicationStageError("Weather application stage marker write failed") from exc

        _rename_noreplace(partial, STAGE_ROOT)
        observed = self.observe(
            plan.source_sha,
            current_main_sha=plan.source_sha,
            exact_main_ci_success=True,
        )
        if classify_application_stage(observed) != "EXACT":
            _fail("Weather application stage postcondition is not exact")
        return {
            "status": "SUCCEEDED",
            "source_sha": plan.source_sha,
            "production_mutation_started": True,
            "mutation_categories": [category for category, _maximum in MUTATION_BUDGET],
        }
