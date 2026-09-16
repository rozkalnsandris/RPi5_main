#!/usr/bin/env python3
from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
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


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout.strip()


assert wn.OPERATION_ID == "rpi5.weathernext-private-installer-boundary.install.v1"
assert wn.TARGET_ALIAS == "rpi5-weathernext-private-installer-boundary"
assert wn.MANAGER_CHECKOUT_BASENAME == "RPi5_main"
assert wn.MANAGER_CHECKOUT_RESOLVER == "repo-owner-home/RPi5_main"
assert wn.TRUSTED_CHECKOUT == "/var/lib/rpi5-deploy/RPi5_main-weathernext-private-installer-trusted"
assert wn.ENTRYPOINT_DESTINATION == "/usr/local/sbin/rpi5-weathernext-private-host-privileged-install"
assert wn.MUTATION_BUDGET == [
    {"category": "git.weathernext-private-installer-checkout-fetch", "max_operations": 1},
    {"category": "git.weathernext-private-installer-checkout-worktree-add", "max_operations": 1},
    {"category": "filesystem.weathernext-private-installer-entrypoint-install", "max_operations": 1},
]
assert wn.ROLLBACK_POLICY == "NONE"
assert wn.capability_descriptor()["status"] == "SOURCE_READY_V12_ENGINE_UPGRADE_REQUIRED"
assert wn.capability_descriptor()["manager_checkout_resolver"] == "repo-owner-home/RPi5_main"

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
accepted = wn.accept_authorization(
    issue,
    server_time=datetime(2026, 9, 15, 12, 5, tzinfo=timezone.utc),
)
assert accepted.payload["operation_id"] == wn.OPERATION_ID

wrong_operation = dict(issue)
wrong_payload = dict(payload)
wrong_payload["operation_id"] = "arbitrary.root.command"
wrong_operation["body"] = (
    wn.START_MARKER + "\n```json\n" + json.dumps(wrong_payload, separators=(",", ":"))
    + "\n```\n" + wn.END_MARKER
)
expect_stop(
    lambda: wn.accept_authorization(
        wrong_operation,
        server_time=datetime(2026, 9, 15, 12, 5, tzinfo=timezone.utc),
    ),
    "wrong operation was accepted",
)
app_authored = dict(issue)
app_authored["performed_via_github_app"] = {"id": 1}
expect_stop(
    lambda: wn.accept_authorization(
        app_authored,
        server_time=datetime(2026, 9, 15, 12, 5, tzinfo=timezone.utc),
    ),
    "App-authored LIVE-AUTH was accepted",
)

# Exact source bytes are proven by Git blob identity, not text-mode git-show output.
with tempfile.TemporaryDirectory() as tmp:
    manager = Path(tmp) / "manager"
    trusted = Path(tmp) / "trusted"
    subprocess.run(["git", "init", str(manager)], check=True, stdout=subprocess.DEVNULL)
    git(manager, "config", "user.name", "test")
    git(manager, "config", "user.email", "test@example.com")
    source = manager / wn.ENTRYPOINT_SOURCE
    source.parent.mkdir(parents=True)
    expected_bytes = b"#!/bin/sh\nprintf '%s\\n' exact\n"
    source.write_bytes(expected_bytes)
    git(manager, "add", wn.ENTRYPOINT_SOURCE)
    git(manager, "commit", "-m", "fixture")
    sha = git(manager, "rev-parse", "HEAD")
    before = (git(manager, "rev-parse", "HEAD"), git(manager, "status", "--porcelain=v1"))
    subprocess.run(
        ["git", "-C", str(manager), "worktree", "add", "--detach", str(trusted), sha],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert wn._source_blob(trusted, trusted / wn.ENTRYPOINT_SOURCE) == wn._expected_blob(manager, sha)
    assert wn._reviewed_source_bytes(manager, trusted, sha) == expected_bytes
    after = (git(manager, "rev-parse", "HEAD"), git(manager, "status", "--porcelain=v1"))
    assert after == before

# Strict WeatherNext locking requires pre-existing V12 control state and never creates it.
with tempfile.TemporaryDirectory() as tmp:
    state_dir = Path(tmp) / "state"
    state_dir.mkdir()
    old = (wn.CTX.test_mode, wn.CTX.state_dir, wn.CTX.lock_path)
    try:
        wn.CTX.test_mode = True
        wn.CTX.state_dir = state_dir
        wn.CTX.lock_path = state_dir / "deploy.lock"
        try:
            wn._existing_operation_lock()
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("missing V12 deploy lock was created or accepted")
        assert not wn.CTX.lock_path.exists()
        wn.CTX.lock_path.write_bytes(b"")
        os.chmod(wn.CTX.lock_path, 0o600)
        with wn._existing_operation_lock():
            assert stat.S_IMODE(wn.CTX.lock_path.stat().st_mode) == 0o600
    finally:
        wn.CTX.test_mode, wn.CTX.state_dir, wn.CTX.lock_path = old

bootstrap_source = (SCRIPTS / "rpi5_weathernext_bootstrap.py").read_text(encoding="utf-8")
deploy_source = (SCRIPTS / "rpi5_deploy.py").read_text(encoding="utf-8")
contract_path = ROOT / "ops/deploy/weather-private-bigquery-host-privileged-installer.json"
contract = json.loads(contract_path.read_text(encoding="utf-8"))
doc_source = (ROOT / "docs/V12_WEATHERNEXT_BOOTSTRAP.md").read_text(encoding="utf-8")

for text in (bootstrap_source, deploy_source, contract_path.read_text(encoding="utf-8"), doc_source):
    assert re.search(r"/home/[A-Za-z0-9._-]+/", text) is None
    assert "safe.directory=*" not in text
    assert "update-ref" not in text

for forbidden in (
    '"clone"', '"reset"', '"clean"', '"pull"', '"switch"', '"merge"', '"rebase"',
    "worktree remove", "worktree prune",
):
    assert forbidden not in bootstrap_source, f"forbidden bootstrap authority/mechanism present: {forbidden!r}"

fetch_source_block = bootstrap_source[bootstrap_source.index("def _fetch_source"):bootstrap_source.index("def _add_trusted_worktree")]
assert '"fetch",' in fetch_source_block
assert '"--no-tags",' in fetch_source_block
assert '"refs/heads/main:refs/remotes/origin/main",' in fetch_source_block
assert '_git_checkout(manager, "worktree", "add", "--detach"' in bootstrap_source
assert '"hash-object", "--no-filters"' in bootstrap_source
assert "O_CREAT" not in bootstrap_source[bootstrap_source.index("def _existing_operation_lock"):bootstrap_source.index("def _final_authority_revalidation")]
assert bootstrap_source.count("_require_manager_snapshot(manager, manager_before)") >= 3
assert "retry/cleanup/rollback forbidden" in bootstrap_source
assert 'if args.command != "weather-private-installer-bootstrap":' in deploy_source
assert "ensure_engine_control_state()" in deploy_source
assert 'branch not in {"", "main"}' in deploy_source
assert "execute_weathernext_bootstrap(" not in deploy_source[
    deploy_source.index("def install_engine"):deploy_source.index("def engine_status")
]

boundary = contract["privileged_boundary"]
assert boundary["manager_checkout_resolver"] == "repo-owner-home/RPi5_main"
assert boundary["caller_authority"] == ["authorization_issue_number"]
assert boundary["bootstrap_mutation_budget"] == wn.MUTATION_BUDGET
assert boundary["rollback_policy"] == "NONE"
assert boundary["preconsume_persistent_logging_allowed"] is False
assert boundary["existing_v12_lock_required"] is True

activation = contract["v12_engine_activation"]
assert activation["trusted_engine_source_checkout_resolver"] == "repo-owner-home/RPi5_main-v12-engine-trusted"
assert activation["manager_branch_ref_mutation_allowed"] is False
assert activation["engine_install_accepts_exact_detached_current_main"] is True
assert activation["weather_bootstrap_executes_during_engine_upgrade"] is False
assert activation["engine_control_state"]["lock"] == "/var/lib/rpi5-deploy/deploy.lock"

assert "SOURCE_READY_V12_ENGINE_UPGRADE_REQUIRED" in doc_source
assert "HOST_V12_WEATHERNEXT_BOOTSTRAP_CAPABILITY_INSTALLED" in doc_source
assert "worktree add --detach" in doc_source

print("V12 WeatherNext fixed bootstrap capability: PASS")
