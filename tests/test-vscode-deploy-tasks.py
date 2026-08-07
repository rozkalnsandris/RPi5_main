#!/usr/bin/env python3
"""Validate the reviewed VS Code deploy task safety contract."""
from __future__ import annotations

import json
from pathlib import Path


repo = Path(__file__).resolve().parents[1]
data = json.loads((repo / ".vscode/tasks.json").read_text(encoding="utf-8"))

labels = {task["label"] for task in data["tasks"]}
assert labels == {
    "RPi5: Sync from GitHub",
    "RPi5: Test",
    "RPi5: Install deploy engine",
    "RPi5: Deploy engine status",
    "RPi5: Deploy plan",
    "RPi5: Deploy reviewed plan",
    "RPi5: Status",
    "RPi5: Rollback latest",
    "RPi5: Deploy logs",
}

inputs = {item["id"]: item for item in data["inputs"]}
assert set(inputs) == {"engineCommit", "deployCommit", "rollbackConfirmation"}
assert inputs["rollbackConfirmation"]["type"] == "promptString"
assert "default" not in inputs["rollbackConfirmation"]

rollback = next(task for task in data["tasks"] if task["label"] == "RPi5: Rollback latest")
assert rollback["command"] == "bash"
assert rollback["args"] == [
    "./scripts/rpi5-deploy",
    "rollback",
    "--latest",
    "--confirm",
    "${input:rollbackConfirmation}",
]

print("V12 VS Code deploy task contract: PASS")
