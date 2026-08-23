#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
import stat
import subprocess
import tempfile
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
helper_path = repo / "ops/lib/dashboard-evidence.py"
collector_path = repo / "ops/bin/rpi5-dashboard-evidence"
backup_wrapper_path = repo / "ops/bin/rpi5-backup-serialized"
service_path = repo / "ops/systemd/rpi5-dashboard-evidence.service"
timer_path = repo / "ops/systemd/rpi5-dashboard-evidence.timer"

spec = importlib.util.spec_from_file_location("dashboard_evidence", helper_path)
assert spec and spec.loader
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
root = Path(tempfile.mkdtemp(prefix="dashboard-evidence-test-")) / "evidence"

assert helper.record_backup(
    run_id="backup-20260822T200000Z-1",
    started_at="2026-08-22T20:00:00Z",
    completed_at="2026-08-22T20:02:00Z",
    exit_code=0,
    size_bytes=123456,
    root=root,
)
assert not helper.record_backup(
    run_id="backup-20260822T200000Z-1",
    started_at="2026-08-22T20:00:00Z",
    completed_at="2026-08-22T20:02:00Z",
    exit_code=0,
    size_bytes=123456,
    root=root,
)
assert helper.record_backup(
    run_id="backup-20260822T210000Z-2",
    started_at="2026-08-22T21:00:00Z",
    completed_at="2026-08-22T21:00:01Z",
    exit_code=23,
    size_bytes=None,
    root=root,
)
backup = json.loads((root / "backups.json").read_text())
assert backup["schema"] == "dashboard-rpi5.backup-evidence.v1"
assert [item["result"] for item in backup["runs"]] == ["FAILED", "SUCCESS"]

assert helper.record_endpoint(
    endpoint_id="grafana", label="Grafana", state="UP", status_code=302,
    latency_ms=40, occurred_at="2026-08-22T20:00:00Z", root=root,
)
assert not helper.record_endpoint(
    endpoint_id="grafana", label="Grafana", state="UP", status_code=302,
    latency_ms=41, occurred_at="2026-08-22T20:02:00Z", root=root,
)
assert helper.record_endpoint(
    endpoint_id="grafana", label="Grafana", state="DOWN", status_code=None,
    latency_ms=None, occurred_at="2026-08-22T20:04:00Z", root=root,
)
endpoint = json.loads((root / "endpoints.json").read_text())
assert endpoint["events"][0]["fromState"] == "UP"
assert endpoint["events"][0]["toState"] == "DOWN"
assert endpoint["events"][1]["fromState"] == "UNKNOWN"

# Pre-fix collector-time timestamps must self-heal to the authoritative systemd
# execution exit timestamp for the same invocation/result.
invocation = "0123456789abcdef0123456789abcdef"
assert helper.record_maintenance(
    invocation_id=invocation, service_result="success",
    occurred_at="2026-08-22T20:06:00Z", root=root,
)
assert helper.record_maintenance(
    invocation_id=invocation, service_result="success",
    occurred_at="2026-08-22T20:05:00Z", root=root,
)
assert not helper.record_maintenance(
    invocation_id=invocation, service_result="success",
    occurred_at="2026-08-22T20:05:00Z", root=root,
)
maintenance = json.loads((root / "maintenance.json").read_text())
assert maintenance["events"] == [{
    "invocationId": invocation,
    "occurredAt": "2026-08-22T20:05:00.000Z",
    "result": "SUCCESS",
    "unitResult": None,
}]
try:
    helper.record_maintenance(
        invocation_id=invocation, service_result="exit-code",
        occurred_at="2026-08-22T20:05:00Z", root=root,
    )
except ValueError:
    pass
else:
    raise AssertionError("same maintenance invocation with conflicting result must fail closed")

# Seed the exact class of invalid evidence produced by the first #196 live
# operator, then prove deploy-sync replaces it only from RPi5_main controlled
# deploy state.
fake_commit = "abcdef123456"
fake_transaction = f"20260822T200500123456Z-{fake_commit}"
assert helper.record_deploy(
    transaction_id=fake_transaction, commit=fake_commit,
    occurred_at="2026-08-22T20:07:00Z", root=root,
)
state_root = Path(tempfile.mkdtemp(prefix="dashboard-deploy-state-test-")) / "state"
state_root.mkdir()
(state_root / "transactions").mkdir()
rpi_commit = "123456abcdef123456abcdef123456abcdef1234"
rpi_short = rpi_commit[:12]
rpi_transaction = f"20260822T195930123456Z-{rpi_short}"
tx_root = state_root / "transactions" / rpi_transaction
tx_root.mkdir()
(state_root / "latest-success").write_text(rpi_transaction + "\n", encoding="utf-8")
(tx_root / "transaction.json").write_text(json.dumps({
    "schema": "rpi5.controlled-deploy-transaction.v1",
    "id": rpi_transaction,
    "repository": "rozkalnsandris/RPi5_main",
    "commit": rpi_commit,
    "started_at": "2026-08-22T19:58:00+00:00",
    "completed_at": "2026-08-22T19:59:30+00:00",
    "status": "success",
    "targets": [],
}) + "\n", encoding="utf-8")
assert helper.sync_deploy_state(
    state_root=state_root,
    root=root,
    observed_at="2026-08-22T20:10:00Z",
)
deploy = json.loads((root / "deployments.json").read_text())
assert deploy == {
    "observedAt": "2026-08-22T20:10:00.000Z",
    "events": [{
        "transactionId": rpi_transaction,
        "commit": rpi_short,
        "occurredAt": "2026-08-22T19:59:30.000Z",
    }],
}
assert fake_commit not in (root / "deployments.json").read_text()

bad_state = Path(tempfile.mkdtemp(prefix="dashboard-deploy-state-bad-")) / "state"
bad_state.mkdir()
(bad_state / "transactions").mkdir()
bad_tx_root = bad_state / "transactions" / rpi_transaction
bad_tx_root.mkdir()
(bad_state / "latest-success").write_text(rpi_transaction + "\n", encoding="utf-8")
(bad_tx_root / "transaction.json").write_text(json.dumps({
    "schema": "rpi5.controlled-deploy-transaction.v1",
    "id": rpi_transaction,
    "repository": "rozkalnsandris/dashboard_RPi5",
    "commit": rpi_commit,
    "completed_at": "2026-08-22T19:59:30+00:00",
    "status": "success",
}) + "\n", encoding="utf-8")
try:
    helper.sync_deploy_state(
        state_root=bad_state,
        root=root,
        observed_at="2026-08-22T20:11:00Z",
    )
except ValueError:
    pass
else:
    raise AssertionError("non-RPi5_main controlled-deploy transaction must fail closed")

assert helper.record_throttle(raw_hex="0x50005", observed_at="2026-08-22T20:09:00Z", root=root)
throttle = json.loads((root / "throttle.json").read_text())
assert throttle == {
    "observedAt": "2026-08-22T20:09:00.000Z",
    "rawHex": "0x50005",
    "schema": "dashboard-rpi5.throttle-evidence.v1",
}

for name in helper.FILES.values():
    path = root / name
    if path.exists():
        assert stat.S_IMODE(path.stat().st_mode) == 0o644
        assert path.stat().st_size <= helper.MAX_BYTES

(root / "endpoints.json").write_text('{"schema":"dashboard-rpi5.endpoint-evidence.v1","events":[{"bad":true}]}')
try:
    helper.record_endpoint(
        endpoint_id="grafana", label="Grafana", state="UP", status_code=200,
        latency_ms=1, occurred_at="2026-08-22T21:00:00Z", root=root,
    )
except ValueError:
    pass
else:
    raise AssertionError("malformed retained evidence must fail closed")

subprocess.run(["bash", "-n", str(collector_path)], check=True)
subprocess.run(["bash", "-n", str(backup_wrapper_path)], check=True)
collector = collector_path.read_text()
helper_source = helper_path.read_text()
backup_wrapper = backup_wrapper_path.read_text()
service = service_path.read_text()
timer = timer_path.read_text()

entries = re.findall(r"^\s*'([^|]+)\|([^|]+)\|(https://[^']+)'$", collector, re.MULTILINE)
assert len(entries) == 8, entries
assert len({entry[0] for entry in entries}) == 8
assert not any("prometheus" in entry[0].lower() or "prometheus" in entry[2].lower() for entry in entries)
assert "401" in collector and "403" in collector
assert "systemctl show \"$UPDATE_UNIT\"" in collector
assert "ExecMainExitTimestamp" in collector
assert "ExecMainCode" in collector
assert "ExecMainStatus" in collector
assert 'date -u --date="$exit_timestamp"' in collector
assert "deploy-sync" in collector
assert "/var/lib/rpi5-deploy" in helper_source
assert "rpi5.controlled-deploy-transaction.v1" in helper_source
assert 'DEPLOY_REPOSITORY = "rozkalnsandris/RPi5_main"' in helper_source
assert "docker " not in collector
assert "journalctl" not in collector
assert "/var/log/" not in collector
assert "usermod" not in collector and "SupplementaryGroups" not in collector

# The collector must preserve the previous failed result for the exact systemd
# reset-failed shape observed on #196: Result=success while the same invocation
# still carries a normal non-zero main-process exit status. Exercise the pure
# shell normalizer directly without running the root collector.
normalizer = re.search(
    r"^normalize_maintenance_result\(\) \{.*?^\}",
    collector,
    re.MULTILINE | re.DOTALL,
)
assert normalizer is not None
normalizer_source = normalizer.group(0)

def normalize(service_result: str, exec_main_code: str, exec_main_status: str) -> str:
    result = subprocess.run(
        [
            "bash",
            "-c",
            normalizer_source + '\nnormalize_maintenance_result "$1" "$2" "$3"',
            "dashboard-evidence-test",
            service_result,
            exec_main_code,
            exec_main_status,
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout.strip()

assert normalize("success", "1", "1") == "exit-code"
assert normalize("success", "1", "42") == "exit-code"
assert normalize("success", "1", "0") == "success"
assert normalize("exit-code", "1", "1") == "exit-code"
assert normalize("success", "", "") == "success"

assert 'readonly BACKUP_METADATA_DIR="/opt/backups"' in backup_wrapper
assert "rpi5_backup_*.tar.gz.age" in backup_wrapper
assert "/var/log/rpi5-backup.log" not in backup_wrapper
assert "/etc/rpi5-backup.conf" not in backup_wrapper
assert "record_backup_evidence_best_effort" in backup_wrapper
assert 'exit "$backup_rc"' in backup_wrapper
assert "backup result unchanged" in backup_wrapper

assert "User=root" in service and "Group=root" in service
assert "ProtectSystem=strict" in service
assert "StateDirectory=dashboard-rpi5" in service
assert "DevicePolicy=closed" in service
assert "DeviceAllow=/dev/vcio rw" in service
assert "SupplementaryGroups=video" not in service
assert "OnUnitActiveSec=2min" in timer
assert "Persistent=false" in timer

print("Dashboard evidence producer source contract: PASS")
