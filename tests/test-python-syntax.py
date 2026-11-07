#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
fixed = [
    ROOT / "ops/lib/dashboard-evidence.py",
    ROOT / "ops/bin/hermes-tech-restore-drill",
    ROOT / "ops/lib/balkons-bot.py",
    ROOT / "ops/bin/balkons-bot-preflight",
    ROOT / "ops/bin/balkons-bot-deploy-verifier",
    ROOT / "ops/bin/balkons-bot-latency-operator",
    ROOT / "ops/bin/balcony-watering-hermes-preflight",
    ROOT / "ops/bin/simple-deploy-executor-upgrade-933",
    ROOT / "ops/bin/rozkalns-cv-live-stats-rollout-1000",
]
paths = sorted(
    {
        *ROOT.joinpath("scripts").glob("*.py"),
        *ROOT.joinpath("ops/lib/deploy_executor").glob("*.py"),
        *fixed,
    },
    key=lambda path: str(path),
)

for path in paths:
    source = path.read_text(encoding="utf-8")
    compile(source, str(path.relative_to(ROOT)), "exec")

print(f"Python syntax: PASS ({len(paths)} files)")
