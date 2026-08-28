from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from .github_app_auth import (
    AppAuthError,
    DryRunAppConfig,
    GitHubAppInstallationTokenProvider,
    load_dry_run_config,
)
from .registry import RegistryError, load_registry
from .transport import (
    GitHubHttpsSender,
    GitHubRestClient,
    GitHubTransportError,
    PersistentETagStore,
)

STATUS_SCHEMA = "rozkalns.deploy-executor-p8-status.v1"
MAX_OPEN_ISSUES = 100


class P8PollerError(RuntimeError):
    pass


@dataclass(frozen=True)
class PollResult:
    result: str
    authenticated: bool
    repository_id: int
    candidate_count: int | None
    mutation_dispatch_enabled: bool
    production_mutation_started: bool


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("utf-8")
    fd, temp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass


def _validate_state_dir(path: str | Path) -> Path:
    state = Path(path)
    if not state.is_absolute():
        raise P8PollerError("state directory must be absolute")
    try:
        info = state.lstat()
    except FileNotFoundError as exc:
        raise P8PollerError("state directory is missing; systemd StateDirectory must create it") from exc
    if not state.is_dir() or state.is_symlink():
        raise P8PollerError("state directory must be a real directory")
    if info.st_mode & 0o077:
        raise P8PollerError("state directory must not be group/world accessible")
    return state


def _validate_repository(payload: Any, config: DryRunAppConfig) -> None:
    if type(payload) is not dict:
        raise P8PollerError("authorization repository response is not an object")
    if payload.get("id") != config.authorization_repository_id:
        raise P8PollerError("authorization repository id drifted")
    if payload.get("full_name") != config.authorization_repository:
        raise P8PollerError("authorization repository name drifted")


def _candidate_count(value: Any, prefix: str) -> int:
    if type(value) is not list:
        raise P8PollerError("open issue poll returned a non-array payload")
    count = 0
    for row in value:
        if type(row) is not dict:
            raise P8PollerError("open issue poll contains malformed item")
        if "pull_request" in row:
            continue
        title = row.get("title")
        if type(title) is str and title.startswith(prefix):
            count += 1
    return count


def poll_once(
    *,
    config_path: str | Path,
    registry_path: str | Path,
    state_dir: str | Path,
    credential_path: str | Path,
    token_provider: GitHubAppInstallationTokenProvider | None = None,
    sender: GitHubHttpsSender | None = None,
) -> PollResult:
    config = load_dry_run_config(config_path)
    if config.mutation_dispatch_enabled or config.result_writer_enabled:
        raise P8PollerError("P8 configuration unexpectedly enables a write path")

    try:
        registry = load_registry(registry_path)
    except RegistryError as exc:
        raise P8PollerError(f"production registry rejected: {exc.code}") from exc
    if registry.execution_enabled or registry.operations:
        raise P8PollerError("P8 requires an empty execution-disabled production registry")

    state = _validate_state_dir(state_dir)
    provider = token_provider or GitHubAppInstallationTokenProvider(
        config=config,
        private_key=credential_path,
    )
    client = GitHubRestClient(
        token_provider=provider,
        sender=sender or GitHubHttpsSender(),
        etag_store=PersistentETagStore(state / "etag-cache.json"),
        max_transport_attempts=1,
    )

    repository = client.get_json(f"/repos/{config.authorization_repository}")
    _validate_repository(repository.value, config)

    query = (
        f"/repos/{config.authorization_repository}/issues"
        "?state=open&per_page=100&sort=created&direction=desc"
    )
    response = client.conditional_get_json(query)
    if response.next_url is not None:
        raise P8PollerError(
            f"open issue set exceeds P8 bounded first page of {MAX_OPEN_ISSUES}"
        )

    if response.not_modified:
        result = PollResult(
            result="POLL_NOT_MODIFIED",
            authenticated=True,
            repository_id=config.authorization_repository_id,
            candidate_count=None,
            mutation_dispatch_enabled=False,
            production_mutation_started=False,
        )
    else:
        result = PollResult(
            result="POLL_OK",
            authenticated=True,
            repository_id=config.authorization_repository_id,
            candidate_count=_candidate_count(response.value, config.issue_title_prefix),
            mutation_dispatch_enabled=False,
            production_mutation_started=False,
        )

    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    _atomic_json(
        state / "status.json",
        {
            "schema": STATUS_SCHEMA,
            "timestamp": timestamp,
            "result": result.result,
            "authenticated": result.authenticated,
            "authorization_repository": config.authorization_repository,
            "authorization_repository_id": result.repository_id,
            "candidate_count": result.candidate_count,
            "mutation_dispatch_enabled": False,
            "result_writer_enabled": False,
            "production_mutation_started": False,
        },
    )
    return result


def render_status(result: PollResult) -> str:
    candidate = "unchanged" if result.candidate_count is None else str(result.candidate_count)
    return (
        "DEPLOY_EXECUTOR_P8="
        f"{result.result} authenticated=true candidates={candidate} "
        "mutation_dispatch=false production_mutation_started=false"
    )


def run(
    *,
    config_path: str | Path,
    registry_path: str | Path,
    state_dir: str | Path,
    credential_path: str | Path,
) -> int:
    try:
        result = poll_once(
            config_path=config_path,
            registry_path=registry_path,
            state_dir=state_dir,
            credential_path=credential_path,
        )
    except (AppAuthError, GitHubTransportError, P8PollerError) as exc:
        print(f"DEPLOY_EXECUTOR_P8=FAIL error_class={type(exc).__name__}")
        return 1
    print(render_status(result))
    return 0
