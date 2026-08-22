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

invocation = "0123456789abcdef0123456789abcdef"
assert helper.record_maintenance(
    invocation_id=invocation, service_result="success",
    occurred_at="2026-08-22T20:05:00Z", root=root,
)
assert not helper.record_maintenance(
    invocation_id=invocation, service_result="success",
    occurred_at="2026-08-22T20:06:00Z", root=root,
)
maintenance = json.loads((root / "maintenance.json").read_text())
assert maintenance["events"] == [{
    "invocationId": invocation,
    "occurredAt": "2026-08-22T20:05:00.000Z",
    "result": "SUCCESS",
    "unitResult": None,
}]

commit = "abcdef123456"
transaction = f"20260822T200500123456Z-{commit}"
assert helper.record_deploy(
    transaction_id=transaction, commit=commit,
    occurred_at="2026-08-22T20:07:00Z", root=root,
)
assert not helper.record_deploy(
    transaction_id=transaction, commit=commit,
    occurred_at="2026-08-22T20:08:00Z", root=root,
)
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
backup_wrapper = backup_wrapper_path.read_text()
service = service_path.read_text()
timer = timer_path.read_text()

entries = re.findall(r"^\s*'([^|]+)\|([^|]+)\|(https://[^']+)'$", collector, re.MULTILINE)
assert len(entries) == 8, entries
assert len({entry[0] for entry in entries}) == 8
assert not any("prometheus" in entry[0].lower() or "prometheus" in entry[2].lower() for entry in entries)
assert "401" in collector and "403" in collector
assert "systemctl show \"$UPDATE_UNIT\"" in collector
assert "docker " not in collector
assert "journalctl" not in collector
assert "/var/log/" not in collector
assert "usermod" not in collector and "SupplementaryGroups" not in collector

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
