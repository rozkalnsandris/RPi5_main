# V02A access-model diagnostic contract

V02A is a strictly read-only diagnostic for normal-user access to a fixed set of Docker, systemd, socket, interface, command-path, namespace, and context metadata. It does not grant access, change host configuration, or use privilege escalation.

Run `scripts/diagnose-access-model.sh --output DIR --context LABEL`. The result directory must be below ignored `evidence/` or `exports/`; it is private, timestamped, bounded, sanitized, checksummed, and verified with `scripts/verify-access-diagnostic.sh RESULT_DIR`.

Each attempted probe records command presence, exit code, stable classification, byte count, timestamps, and context. Classifications describe direct diagnostic evidence only. The decision output does not prescribe host changes.

The fixed allowlist excludes Docker inspect and mutation commands, configuration/data reads, full environment capture, process environments, raw journals, raw Compose data, and socket API requests. Compose output is projected to project name and status only; `ConfigFiles` and other raw fields are discarded.

When two verified contexts are available, `scripts/compare-access-diagnostics.sh` produces a separate ignored comparison artifact containing only allowed metadata and classifications. It is not a privilege-escalation mechanism.
