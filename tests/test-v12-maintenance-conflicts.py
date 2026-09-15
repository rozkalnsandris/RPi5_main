#!/usr/bin/env python3
"""Regression contract for V12 maintenance conflicts and root-only control state."""
from __future__ import annotations

import ast
import re
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

repo = Path(__file__).resolve().parents[1]
lib_path = repo / "scripts" / "rpi5_deploy_lib.py"
source = lib_path.read_text(encoding="utf-8")
tree = ast.parse(source)

assignments: dict[str, object] = {}
for node in tree.body:
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        continue
    target = node.targets[0]
    if isinstance(target, ast.Name) and target.id in {
        "MAINTENANCE_PROCESS_PATTERNS",
        "PACKAGE_MANAGER_LOCKS",
    }:
        assignments[target.id] = ast.literal_eval(node.value)

patterns = assignments.get("MAINTENANCE_PROCESS_PATTERNS")
locks = assignments.get("PACKAGE_MANAGER_LOCKS")
assert isinstance(patterns, tuple) and patterns
assert isinstance(locks, tuple) and locks

idle_waiter = (
    "/usr/bin/python3 "
    "/usr/share/unattended-upgrades/unattended-upgrade-shutdown --wait-for-signal"
)
assert not any(re.search(pattern, idle_waiter) for pattern in patterns), (
    "idle unattended-upgrade shutdown waiter must not block deploy planning"
)

active_commands = (
    "/usr/bin/apt update",
    "/usr/bin/apt-get upgrade",
    "/usr/bin/dpkg --configure -a",
    "/usr/bin/python3 /usr/share/unattended-upgrades/unattended-upgrade --download-only",
)
for command in active_commands:
    assert any(re.search(pattern, command) for pattern in patterns), (
        f"real package-manager activity must block: {command}"
    )

expected_locks = {
    "/var/lib/dpkg/lock-frontend",
    "/var/lib/dpkg/lock",
    "/var/cache/apt/archives/lock",
    "/var/lib/apt/lists/lock",
}
assert set(locks) == expected_locks

ensure = next(
    node for node in tree.body
    if isinstance(node, ast.FunctionDef) and node.name == "ensure_no_conflicts"
)
used_names = {
    node.id for node in ast.walk(ensure)
    if isinstance(node, ast.Name)
}
assert "MAINTENANCE_PROCESS_PATTERNS" in used_names
assert "PACKAGE_MANAGER_LOCKS" in used_names
assert 'r"apt-get|apt |dpkg|unattended-upgrade"' not in source

# The V12 engine installer runs as the normal repository owner. Children of
# /var/lib/rpi5-deploy are intentionally hidden behind root:root 0700, so the
# deploy.lock pre/post-state must be checked through fixed privileged metadata
# probes rather than normal-user Path.exists()/lstat().
sys.path.insert(0, str(repo / "scripts"))
import rpi5_deploy as deploy

LOCK = Path("/var/lib/rpi5-deploy/deploy.lock")


def response(returncode: int, stdout: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


def probe(responses: list[SimpleNamespace]) -> tuple[bool, list[list[str]]]:
    calls: list[list[str]] = []
    pending = list(responses)
    original = deploy.run

    def fake_run(args, **kwargs):
        calls.append(list(args))
        if not pending:
            raise AssertionError(f"unexpected command: {args}")
        return pending.pop(0)

    deploy.run = fake_run
    try:
        result = deploy._probe_deploy_lock()
    finally:
        deploy.run = original
    assert not pending, f"unused probe responses: {pending}"
    return result, calls


def expect_probe_error(responses: list[SimpleNamespace], text: str) -> None:
    try:
        probe(responses)
    except deploy.DeployError as exc:
        assert text in str(exc), str(exc)
    else:
        raise AssertionError(f"expected DeployError containing {text!r}")


absent, calls = probe([response(1), response(1)])
assert absent is False
assert calls == [
    ["sudo", "/usr/bin/test", "-L", str(LOCK)],
    ["sudo", "/usr/bin/test", "-e", str(LOCK)],
]

regular_mode = stat.S_IFREG | 0o600
present, calls = probe([
    response(1),
    response(0),
    response(0, f"{regular_mode:x}:0:0:1"),
])
assert present is True
assert calls == [
    ["sudo", "/usr/bin/test", "-L", str(LOCK)],
    ["sudo", "/usr/bin/test", "-e", str(LOCK)],
    ["sudo", "/usr/bin/stat", "--printf=%f:%u:%g:%h", "--", str(LOCK)],
]

expect_probe_error([response(0)], "control file drifted")
expect_probe_error([response(2)], "symlink probe failed")
expect_probe_error([response(1), response(2)], "existence probe failed")
expect_probe_error([response(1), response(0), response(2)], "metadata probe failed")
expect_probe_error(
    [response(1), response(0), response(0, f"{(stat.S_IFDIR | 0o600):x}:0:0:1")],
    "control file drifted",
)
expect_probe_error(
    [response(1), response(0), response(0, f"{regular_mode:x}:0:0:2")],
    "control file drifted",
)
expect_probe_error(
    [response(1), response(0), response(0, f"{regular_mode:x}:1000:0:1")],
    "control file drifted",
)
expect_probe_error(
    [response(1), response(0), response(0, f"{regular_mode:x}:0:1000:1")],
    "control file drifted",
)
expect_probe_error(
    [response(1), response(0), response(0, f"{(stat.S_IFREG | 0o644):x}:0:0:1")],
    "control file drifted",
)
expect_probe_error(
    [response(1), response(0), response(0, "not:valid:metadata")],
    "invalid output",
)

deploy_path = repo / "scripts" / "rpi5_deploy.py"
deploy_source = deploy_path.read_text(encoding="utf-8")
deploy_tree = ast.parse(deploy_source)
control_state = next(
    node for node in deploy_tree.body
    if isinstance(node, ast.FunctionDef) and node.name == "ensure_engine_control_state"
)
control_source = ast.get_source_segment(deploy_source, control_state) or ""
assert "lock_path.exists()" not in control_source
assert "lock_path.lstat()" not in control_source
assert "_probe_deploy_lock()" in control_source
assert 'Path("/var/lib/rpi5-deploy/deploy.lock")' in deploy_source
assert '"sudo", "/usr/bin/stat", "--printf=%f:%u:%g:%h"' in deploy_source

print("V12 maintenance conflict and root-only control-state regression: PASS")
