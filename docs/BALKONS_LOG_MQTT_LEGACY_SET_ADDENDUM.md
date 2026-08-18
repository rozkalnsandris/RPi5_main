# Balcony MQTT legacy process-set retirement addendum

Issue: #173

## Status and precedence

This addendum supplements `docs/BALKONS_LOG_MQTT_AUTH_CONTRACT.md` after the 2026-08-18 lifecycle-aware read-only v3 preflight. For the one-time legacy retirement step, this document **supersedes singular wording** such as `captured legacy subscriber PID` in the earlier contract.

It does not change the reviewed post-remediation wrapper, systemd unit, MQTT credential path, output-preservation rules, shared-account boundary, ESP32 boundary, or pump boundary.

Production mutation remains separately owner-gated.

## New live evidence

The read-only v3 preflight on exact `RPi5_main/main` `200d32042d1795f487303e30170461532f71e515` established, without printing any PID, username, password, argv, private path, or MQTT payload:

- exact-main source gate: PASS;
- exact-main push CI: PASS;
- live service/output gates: PASS;
- `MOSQUITTO_SUB_PROCESS_COUNT=3`;
- `LOGGER_TOPIC_PROCESS_COUNT=3`;
- `OLD_SECRET_PROCESS_COUNT=3`;
- `LEGACY_AUTH_PROCESS_COUNT=3`;
- `LEGACY_EXACT_RUNTIME_PROCESS_COUNT=3`;
- `MANAGED_LOGGER_PROCESS_COUNT=0`;
- runtime reference from the live systemd MainPID: PASS;
- legacy fingerprint capture: PASS;
- broker topology: PASS;
- ESP32 online precheck: PASS;
- pump retained-state precheck: PASS;
- `MUTATION_STARTED=NO`.

The three legacy subscribers are exact runtime clones of the current live MainPID `mosquitto_sub` subcommand. The runtime reference, not the raw unit-file `-F` text, is authoritative because systemd may expand specifiers before executing `ExecStart=`.

## Captured legacy subscriber set

The next production transaction must capture a **legacy subscriber set** before its first production write.

For every exact runtime clone, keep only in root-only ephemeral memory/state:

1. container PID;
2. `/proc/<pid>/stat` start-time value;
3. exact raw `/proc/<pid>/cmdline` fingerprint.

The captured set must contain at least one member. Every currently visible logger-topic process carrying the old auth shape/secret must belong to this exact runtime-clone set. A mixed or ambiguous process population is a pre-mutation blocker.

No PID, argv, username, password, password hash, private log path, or secret-bearing fingerprint may be printed, committed, or retained as public evidence.

## One-time retirement rule

After the new source/runtime files are staged and verified, but before starting the replacement logger:

1. stop only `balkons-log.service`;
2. re-scan each member of the captured legacy set;
3. if a captured PID has already disappeared, treat that member as already retired;
4. if it still exists, require the same PID start-time and byte-identical cmdline fingerprint;
5. send `SIGTERM` only to members that still match all captured fields;
6. wait a bounded interval for all matching members to disappear;
7. abort and roll back if any surviving captured PID has changed start-time or cmdline, or if any unexpected old-secret/logger-topic subscriber exists outside the captured set;
8. require whole-container inspection to show zero old-secret argv exposure before the replacement logger is started.

Generic `pkill`, process-name-only killing, username/password matching as the kill selector, broker restart, container restart, and all-subscriber termination are forbidden.

## Post-remediation lifecycle

The one-time legacy subscriber set is only for migration from the old service. After migration, the reviewed #185 design owns its lifecycle through the non-secret client id `balkons-log-service`, exact topic matching, pre-start stale-process cleanup, and `ExecStop=` cleanup.

Acceptance still requires exactly one managed logger subscriber after start, no old/new credential in any process argv, preserved private append output semantics, unchanged broker restart count, ESP32 online, unchanged pump retained state, no MQTT publish, no ESP32 mutation, and no pump command.

## Rollback consequence

Once stale legacy clones have been safely retired, rollback must **not recreate orphan duplicates** merely to restore their previous accidental process count. Rollback restores the previous broker password-file state, old unit/runtime configuration, private output sink, broker/ESP32 health, and one functional legacy logger service instance. Any managed post-remediation subscriber must be retired through the reviewed managed lifecycle cleanup before the old service is restored.

This is intentional: duplicate orphan legacy subscribers are unsafe residual processes, not configuration state that rollback should reproduce.

## Production boundary

This addendum authorizes no production action by itself. A lifecycle-aware apply requires a new exact artifact, a fresh read-only gate against its bound source, and a fresh explicit owner authorization before the first production write or process termination.
