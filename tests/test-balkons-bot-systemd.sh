#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."
unit="ops/systemd/balkons-bot.service.in"

[[ -f "$unit" ]]
grep -Fq 'User=@SERVICE_USER@' "$unit"
grep -Fq 'ExecStart=@PYTHON_EXECUTABLE@ @BOT_SOURCE_PATH@' "$unit"
grep -Fq 'Restart=@RESTART_POLICY@' "$unit"
grep -Fq 'RestartSec=@RESTART_SEC@' "$unit"
grep -Fq 'TimeoutStopSec=@TIMEOUT_STOP_SEC@' "$unit"

for name in telegram-token telegram-chat-id mqtt-host mqtt-username mqtt-secret; do
  grep -Eq "^LoadCredential=${name}:/etc/credstore/" "$unit"
done

[[ "$(grep -c '^LoadCredential=' "$unit")" -eq 5 ]]
! grep -Eq '^Environment=.*(TOKEN|CHAT_ID|MQTT_(USER|PASS|PASSWORD|SECRET))=' "$unit"
! grep -Eq '^ExecStart=.*(--?(user|username|pass|password|token|secret)|-u[[:space:]]|-P[[:space:]])' "$unit"
grep -Fq 'SendSIGKILL=no' "$unit"
grep -Fq 'NoNewPrivileges=yes' "$unit"
grep -Fq 'ProtectSystem=strict' "$unit"
grep -Fq 'ProtectHome=read-only' "$unit"
grep -Fq 'CapabilityBoundingSet=' "$unit"

# The tracked template must fail closed against accidental direct deployment.
grep -Eq '@(SERVICE_USER|PYTHON_EXECUTABLE|BOT_SOURCE_PATH|RESTART_POLICY|RESTART_SEC|TIMEOUT_STOP_SEC)@' "$unit"

echo 'Balkons bot systemd template tests: PASS'
