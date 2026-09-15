#!/usr/bin/env python3
from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import rpi5_deploy as deploy
import rpi5_weathernext_bootstrap as wn


def expect_stop(fn, message: str) -> None:
    try:
        fn()
    except wn.BootstrapStop:
        return
    raise AssertionError(message)


assert wn.OPERATION_ID == "rpi5.weathernext-private-installer-boundary.install.v1"
assert wn.TARGET_ALIAS == "rpi5-weathernext-private-installer-boundary"
assert wn.MANAGER_CHECKOUT == "/home/andris/RPi5_main"
assert wn.TRUSTED_CHECKOUT == "/var/lib/rpi5-deploy/RPi5_main-weathernext-private-installer-trusted"
assert wn.ENTRYPOINT_DESTINATION == "/usr/local/sbin/rpi5-weathernext-private-host-privileged-install"
assert wn.MUTATION_BUDGET == [
    {"category": "git.weathernext-private-installer-checkout-fetch", "max_operations": 1},
    {"category": "git.weathernext-private-installer-checkout-worktree-add", "max_operations": 1},
    {"category": "filesystem.weathernext-private-installer-entrypoint-install", "max_operations": 1},
]
assert wn.ROLLBACK_POLICY == "NONE"
assert wn.capability_descriptor()["status"] == "SOURCE_READY_V12_ENGINE_UPGRADE_REQUIRED"

args = deploy.parser().parse_args([
    "weather-private-installer-bootstrap",
    "--authorization-issue-number", "123",
])
assert args.authorization_issue_number == 123
with contextlib.redirect_stderr(io.StringIO()):
    try:
        deploy.parser().parse_args([
            "weather-private-installer-bootstrap",
            "--authorization-issue-number", "123",
            "--path", "/tmp/not-allowed",
        ])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("WeatherNext parser accepted caller-selected path authority")

assert deploy.WEATHERNEXT_ENGINE_SOURCE in deploy.ENGINE_SOURCE_FILES
assert deploy.ENGINE_INSTALLED_FILES["rpi5_weathernext_bootstrap.py"] == "0400"
targets = deploy.require_target_contract()
assert [target.id for target in targets] == [
    "backup-runner", "backup-core", "maintenance-lock-lib", "backup-cron", "backup-logrotate"
]

hashes = deploy.engine_source_hashes()
with tempfile.TemporaryDirectory() as tmp:
    stage = Path(tmp) / "release"
    metadata_path, wrapper_path = deploy.stage_engine_release(
        stage,
        deploy.ENGINE_RELEASES / ("a" * 40),
        "a" * 40,
        hashes,
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert set(metadata["installed_files"]) == set(deploy.ENGINE_INSTALLED_FILES)
    assert metadata["installed_files"]["rpi5_weathernext_bootstrap.py"]["mode"] == "0400"
    assert (stage / "rpi5_weathernext_bootstrap.py").is_file()
    assert "exec /usr/bin/env -i" in wrapper_path.read_text(encoding="utf-8")

payload = {
    "schema": wn.LIVE_AUTH_SCHEMA,
    "request_id": "123e4567-e89b-42d3-a456-426614174000",
    "queue_repository": wn.QUEUE_REPOSITORY,
    "queue_issue": 44,
    "source_repository": wn.SOURCE_REPOSITORY,
    "source_sha": "a" * 40,
    "target_alias": wn.TARGET_ALIAS,
    "operation_id": wn.OPERATION_ID,
    "expected_baseline": wn.BASELINE,
    "mutation_budget": wn.MUTATION_BUDGET,
    "rollback_policy": wn.ROLLBACK_POLICY,
    "exclusions": wn.EXCLUSIONS,
    "dependencies": [*wn.FIXED_DEPENDENCIES, "queue-contract-sha256:" + "b" * 64],
}
body = wn.START_MARKER + "\n```json\n" + json.dumps(payload, separators=(",", ":")) + "\n```\n" + wn.END_MARKER
issue = {
    "id": 111,
    "number": 222,
    "state": "open",
    "pull_request": None,
    "title": f"[LIVE-AUTH][PENDING] {wn.TARGET_ALIAS}",
    "created_at": "2026-09-15T12:00:00Z",
    "body": body,
    "user": {"id": wn.OWNER_USER_ID, "type": "User"},
    "performed_via_github_app": None,
}
accepted = wn.accept_authorization(issue, server_time=datetime(2026, 9, 15, 12, 5, tzinfo=timezone.utc))
assert accepted.payload["operation_id"] == wn.OPERATION_ID

wrong_operation = dict(issue)
wrong_payload = dict(payload)
wrong_payload["operation_id"] = "arbitrary.root.command"
wrong_operation["body"] = wn.START_MARKER + "\n```json\n" + json.dumps(wrong_payload, separators=(",", ":")) + "\n```\n" + wn.END_MARKER
expect_stop(
    lambda: wn.accept_authorization(wrong_operation, server_time=datetime(2026, 9, 15, 12, 5, tzinfo=timezone.utc)),
    "wrong operation was accepted",
)
app_authored = dict(issue)
app_authored["performed_via_github_app"] = {"id": 1}
expect_stop(
    lambda: wn.accept_authorization(app_authored, server_time=datetime(2026, 9, 15, 12, 5, tzinfo=timezone.utc)),
    "App-authored LIVE-AUTH was accepted",
)

source = (SCRIPTS / "rpi5_weathernext_bootstrap.py").read_text(encoding="utf-8")
for forbidden in (
    "safe.directory=*", '"clone"', '"reset"', '"clean"', '"pull"', '"switch"', '"merge"', '"rebase"',
    "worktree remove", "worktree prune",
):
    assert forbidden not in source, f"forbidden bootstrap authority/mechanism present: {forbidden!r}"
assert '_manager_git(manager, "fetch"' in source
assert '_git_checkout(manager, "worktree", "add", "--detach"' in source
assert '_manager_git(manager, "show"' in source
assert source.count("_require_manager_snapshot(manager, manager_before)") >= 3
assert "retry/cleanup/rollback forbidden" in source
print("V12 WeatherNext fixed bootstrap capability: PASS")
