#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops/bin/rpi5-update"
CUTOVER = ROOT / "ops/bin/rpi5-maintenance-systemd-cutover"
text = SOURCE.read_text(encoding="utf-8")
cutover = CUTOVER.read_text(encoding="utf-8")

required = (
    "rpi5-update-cleanup-policy.sh",
    "rpi5_cleanup_owned_path_kind",
    "cleanup_owned_maintenance_artifacts",
    "find /tmp",
    "-name 'rpi5-update-*'",
    "find /var/log",
    "-name 'rpi5-update.log.*'",
    "apt-get autoclean -y",
    "systemd-tmpfiles --clean",
    "--vacuum-time=\"$JOURNAL_RETENTION\"",
)
for marker in required:
    assert marker in text, f"missing cleanup ownership marker: {marker}"

forbidden = (
    'find "$UPDATE_HOME"',
    '"$UPDATE_HOME/update-script-backups"',
    "-name 'rpi5_*.log'",
    "-name 'rpi5-*.log'",
    "-name 'rpi5-*-backup-20*'",
    "-name 'cloudflare-ufw-backup-20*'",
    "-name 'rpi5-*-latest-backup'",
    "-name 'deploy_rpi5_*.sh'",
    "docker network prune",
    "--remove-orphans",
    "/usr/local/libexec/rpi5-maintenance",
)
for marker in forbidden:
    assert marker not in text, f"forbidden cleanup/control-plane marker remains: {marker}"
    assert marker not in cutover, f"forbidden cutover marker remains: {marker}"

assert '/usr/local/lib/rpi5-maintenance' in text
assert 'MAINTENANCE_LIB_DIR="/usr/local/lib/rpi5-maintenance"' in cutover

# cleanup-only remains usable when Docker itself is unavailable. The degraded
# Docker portion is visible/nonzero while non-Docker cleanup continues.
assert "DOCKER_COMMAND_AVAILABLE=1" in text
assert 'elif [[ "$MODE" == "cleanup" ]]; then' in text
assert 'DOCKER_AVAILABLE_FOR_CLEANUP="$DOCKER_COMMAND_AVAILABLE"' in text
assert "Docker komanda nav pieejama; Docker cleanup izlaists" in text
assert "Docker daemon nav pieejams; Docker cleanup izlaists" in text
assert 'if [[ "$MODE" != "cleanup" ]]; then\n    validate_compose_project' in text
assert 'if [[ "$MODE" != "cleanup" ]]; then\n    check_project_runtime' in text

# V27 keeps Hermes update checking read-only and outside cleanup-only. Cleanup
# exits before the advisory check, and the legacy auto-update toggle is gone.
cleanup_final = text.index('if [[ "$MODE" == "cleanup" ]]; then\n    END_EPOCH=')
cleanup_exit = text.index('    exit "$CLEANUP_STATUS"', cleanup_final)
hermes_phase = text.index('CURRENT_PHASE="Hermes update check"')
hermes_check = text.index('"$HERMES_BIN" update --check', hermes_phase)
assert cleanup_final < cleanup_exit < hermes_phase < hermes_check
assert "HERMES_UPDATE" not in text

# Production installer must ship and verify the cleanup policy helper together
# with the updater under the canonical maintenance library root.
assert cutover.count("rpi5-update-cleanup-policy.sh") == 3

print("Maintenance cleanup source contract: PASS")
