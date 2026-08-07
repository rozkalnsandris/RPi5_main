#!/usr/bin/env python3
"""Regression contract for V12 package-manager conflict detection."""
from __future__ import annotations

import ast
import re
from pathlib import Path

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

print("V12 maintenance conflict regression: PASS")
