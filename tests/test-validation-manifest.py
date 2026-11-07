#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ci/validate-groups.json"
EXPECTED_GROUPS = [
    "syntax-policy",
    "weather",
    "ausmalwiese-coloring",
    "hermes-cv",
    "deploy-control",
    "cloudflare-ingress",
    "balcony",
    "host-a",
    "host-b",
    "misc",
]

payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
assert payload["schema"] == "rpi5.validate-groups.v1"
assert list(payload["groups"]) == EXPECTED_GROUPS

commands: list[tuple[str, ...]] = []
for group in EXPECTED_GROUPS:
    entries = payload["groups"][group]
    assert entries, group
    for argv in entries:
        assert isinstance(argv, list) and argv
        assert all(isinstance(part, str) and part for part in argv)
        assert "-c" not in argv
        commands.append(tuple(argv))

assert len(commands) == 304
assert len(set(commands)) == len(commands)

for argv in commands:
    candidates = [part for part in argv if part.startswith("./tests/")]
    for candidate in candidates:
        path = ROOT / candidate.removeprefix("./")
        assert path.is_file(), candidate

shell_syntax = (ROOT / "tests/test-shell-syntax.sh").read_text(encoding="utf-8")
assert "python3 ./tests/" not in shell_syntax
assert "bash ./tests/" not in shell_syntax

workflow = (ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
for group in EXPECTED_GROUPS:
    assert f"          - {group}\n" in workflow
assert "if: ${{ always() }}" in workflow
assert "Require every validation dependency to pass" in workflow
assert "python3 ./scripts/require-validation-results.py" in workflow

all_text = "\n".join(" ".join(argv) for argv in commands)
for required in (
    "./tests/test-dashboard-issue226-trusted-read-bridge.sh",
    "./tests/test-cloudflare-p1d04-prelive-prep.py",
    "./tests/test-browser-lifecycle.py",
    "./tests/test-ui-proof-guarded.py",
    "./tests/test-adguard-dns-hardening.py",
    "./tests/test-adguard-resolver-phase2.py",
    "./tests/test-adguard-resolver-phase2-recovery.py",
    "./tests/test-adguard-dhcpv4-migration.py",
    "./tests/test-ausmalwiese-stats-legacy-id-migration-v1.py",
    "./tests/test-ausmalwiese-stats-legacy-id-runtime-v1.py",
    "./tests/test-ausmalwiese-stats-legacy-id-runtime-installer-v1.py",
    "./tests/test-ausmalwiese-catalog-classification-apply-v1.py",
    "./tests/test-ausmalwiese-catalog-classification-review-to-apply-v1.py",
    "./tests/test-ausmalwiese-goatcounter-household-waf-install-v1.py",
):
    assert all_text.count(required) == 1, required

source_job_workflows: list[str] = []
for workflow_path in sorted((ROOT / ".github/workflows").glob("*.yml")):
    workflow_text = workflow_path.read_text(encoding="utf-8")
    if re.search(r"(?m)^  source:\\s*$", workflow_text) is not None:
        source_job_workflows.append(workflow_path.relative_to(ROOT).as_posix())

assert not source_job_workflows, f"ambiguous source jobs remain: {source_job_workflows}"

python_syntax = (ROOT / "tests/test-python-syntax.py").read_text(encoding="utf-8")
for required in (
    'ROOT / "ops/bin/rpi5-weathernext-private-installer-boundary-bootstrap"',
    'ROOT / "ops/bin/rpi5-weathernext-private-installer-boundary-refresh-runtime"',
):
    assert required in python_syntax, required

assert "      - workflow-security\n" in workflow
assert "WORKFLOW_SECURITY_RESULT: ${{ needs['workflow-security'].result }}" in workflow

print(f"Validation manifest: PASS ({len(commands)} commands / {len(EXPECTED_GROUPS)} groups)")
