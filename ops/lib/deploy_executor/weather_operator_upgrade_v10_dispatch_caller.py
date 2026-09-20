from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import re
from typing import Any, Callable, Iterator, Mapping

from . import weather_operator_upgrade_v9_dispatch_caller as legacy
from . import weather_operator_upgrade_v9_host_capability as cap
from .dispatch_contract import DispatchRequest
from .transport import GitHubRestClient

ISSUE = 650
OPERATION_ID = "rpi5-main.weather-operator-upgrade-v10.v1"
TARGET_ALIAS = "rpi5-main-weather-operator-upgrade-v10"
AUTH_START = "<!-- rozkalns-weather-v10-live-auth:v1 -->"
AUTH_END = "<!-- /rozkalns-weather-v10-live-auth:v1 -->"
AUTH_SCHEMA = "rozkalns.rpi5-main.weather-operator-upgrade-v10-live-auth.v1"
AUTH_TITLE = "[LIVE-AUTH][PENDING] rpi5-main-weather-operator-upgrade-v10"
OLD_SHA256 = "48c8c5fb0cdc005bf0e4fbb05a203297e05d7ef62689ddd0d6d717c13acc0fcb"
MUTATION_BUDGET = (
    ("git.weather-operator-upgrade-v10-checkout-fetch", 1),
    ("git.weather-operator-upgrade-v10-checkout-worktree-add", 1),
    ("filesystem.weather-operator-upgrade-v10-atomic-replace", 1),
)
REQUIRED_EXCLUSIONS = (
    "no generic sudo/root shell or caller-selected command/path/argv/environment",
    "no cleanup/retry/rollback/worktree remove/prune/repair",
    "no Docker/systemd application mutation",
    "no SQLite/corpus/snapshot/database mutation",
    "no network/firewall/DNS/Cloudflare mutation",
    "no credential/secret/permission/repository-settings mutation",
    "no v9 LIVE authorization reuse",
)
RESULT_SCHEMA = "rozkalns.rpi5-main.weather-v10-successor-dispatch-caller-result.v1"

_CAP_FIELDS = (
    "OPERATION_ID",
    "TARGET_ALIAS",
    "AUTH_START",
    "AUTH_END",
    "AUTH_SCHEMA",
    "OLD_SHA256",
    "MUTATION_BUDGET",
    "REQUIRED_EXCLUSIONS",
)
_LEGACY_FIELDS = ("AUTH_START", "AUTH_END", "AUTH_TITLE", "_REQUEST_ID_RE", "RESULT_SCHEMA")


@contextmanager
def successor_profile() -> Iterator[None]:
    """Temporarily select the reviewed v10 authorization profile over the frozen v9 caller."""
    cap_saved = {name: getattr(cap, name) for name in _CAP_FIELDS}
    legacy_saved = {name: getattr(legacy, name) for name in _LEGACY_FIELDS}
    try:
        cap.OPERATION_ID = OPERATION_ID
        cap.TARGET_ALIAS = TARGET_ALIAS
        cap.AUTH_START = AUTH_START
        cap.AUTH_END = AUTH_END
        cap.AUTH_SCHEMA = AUTH_SCHEMA
        cap.OLD_SHA256 = OLD_SHA256
        cap.MUTATION_BUDGET = MUTATION_BUDGET
        cap.REQUIRED_EXCLUSIONS = REQUIRED_EXCLUSIONS

        legacy.AUTH_START = AUTH_START
        legacy.AUTH_END = AUTH_END
        legacy.AUTH_TITLE = AUTH_TITLE
        legacy._REQUEST_ID_RE = re.compile(
            re.escape(AUTH_START)
            + r"\n```json\n(?P<payload>.*?)\n```\n"
            + re.escape(AUTH_END),
            re.DOTALL,
        )
        legacy.RESULT_SCHEMA = RESULT_SCHEMA
        yield
    finally:
        for name, value in legacy_saved.items():
            setattr(legacy, name, value)
        for name, value in cap_saved.items():
            setattr(cap, name, value)


def discover_candidate(client: GitHubRestClient):
    with successor_profile():
        return legacy.discover_candidate(client)


def run_once(
    client: GitHubRestClient,
    *,
    state_dir: Path = legacy.STATE_DIR,
    dispatcher: Callable[[DispatchRequest], Mapping[str, Any]] = legacy.dispatch_to_broker,
) -> Mapping[str, Any]:
    with successor_profile():
        return legacy.run_once(client, state_dir=state_dir, dispatcher=dispatcher)


def runtime_main() -> int:
    with successor_profile():
        return legacy.runtime_main()


def source_readiness() -> Mapping[str, Any]:
    return {
        "schema": "rozkalns.rpi5-main.weather-v10-successor-dispatch-caller.v1",
        "issue": ISSUE,
        "result": "SOURCE_READY_FOR_SEPARATE_CALLER_REFRESH_LIVE_GATE",
        "operation_id": OPERATION_ID,
        "authorization_title": AUTH_TITLE,
        "identity_only_dispatch_schema": legacy.DISPATCH_SCHEMA,
        "authorization_repository": legacy.AUTHORIZATION_REPOSITORY,
        "fixed_socket": str(legacy.SOCKET_PATH),
        "historical_v9_caller_source_mutated": False,
        "v9_authorization_reuse": False,
        "caller_command_allowed": False,
        "caller_path_allowed": False,
        "caller_argv_allowed": False,
        "caller_environment_allowed": False,
        "automatic_retry": False,
        "source_merge_authorizes_live": False,
        "production_mutation_started": False,
    }
