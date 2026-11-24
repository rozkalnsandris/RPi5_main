# Balcony MQTT logger argv remediation — final closeout

Issue: #173

Status: **completed in production on 2026-08-19**

## Final production state

The `balkons-log.service` logger has been migrated away from MQTT credentials in process argv. The production logger now uses a dedicated logger-only MQTT identity and the reviewed systemd credential/stdin path.

Exact source deployed by the successful transaction:

`a5e388e617300b03e918e9789fef2cabb2a4dc35`

The final owner-authorized v5 cutover artifact was bound to that exact source and completed with sanitized evidence:

```text
MUTATION_STARTED=YES
ROLLBACK_BUNDLE=VERIFIED
LOGGER_IDENTITY_ADD=PASS
BROKER_RELOAD=PASS
OLD_SHARED_AUTH=PASS
NEW_LOGGER_AUTH=PASS
SYSTEMD_STAGE=PASS
OUTPUT_PRE_RESTART=PASS
LOGGER_HOST_STOP=PASS
LEGACY_SET_RETIREMENT=PASS
LEGACY_ARGV_ZERO=PASS
LOGGER_START=PASS
ARGV_CLEAN=PASS
MANAGED_PROCESS_SINGLETON=PASS
OUTPUT_PRESERVED=PASS
MANAGED_LIFECYCLE_STOP=PASS
MANAGED_LIFECYCLE_RESTART=PASS
BROKER_HEALTH=PASS
ESP32_POSTCHECK=PASS
PUMP_UNCHANGED=PASS
MQTT_PUBLISH=NONE
ESP32_MUTATION=NONE
PUMP_COMMAND=NONE
FINAL_CUTOVER=PASS
```

No rollback was required for the successful v5 transaction.

## Security architecture after completion

The reviewed logger auth path is:

`root-only host credential -> systemd LoadCredential= -> credential file in $CREDENTIALS_DIRECTORY -> wrapper stdin -> docker exec -i -> mosquitto_sub -o /dev/stdin`

Properties that must remain true:

- no MQTT username/password in the logger process argv;
- no MQTT username/password in the non-secret runtime environment file;
- no real credential in Git;
- the logger has an explicit non-secret managed MQTT client ID;
- container-side cleanup targets only the exact managed logger identity and topic;
- lifecycle cleanup uses targeted SIGTERM only, with a bounded wait;
- no generic `pkill` or SIGKILL fallback;
- the existing private stdout/stderr append sink remains preserved through a runtime-only local systemd drop-in;
- broker auth reload uses HUP/reload semantics rather than a broker/container restart when the live gate supports it.

## Incident and remediation chain

The remediation required several fail-closed iterations. The important lessons are retained here so future changes do not repeat them.

### 1. Shared-account topology changed the rotation plan

The original finding suggested rotating the exposed credential immediately. A later broker-auth topology audit showed the pre-existing account was shared and potentially used by the ESP32 or other clients.

Therefore #173 intentionally migrated only the logger to a dedicated identity and left the old shared credential active. Shared-credential isolation and eventual revocation is separate work tracked in #189.

### 2. Production output semantics had to be preserved

The live unit wrote stdout and stderr to the same private `append:` target. The tracked unit's journal directives were only a repository fallback and were not production-equivalent.

The final contract therefore preserves the live private append target with a runtime-only local systemd drop-in and verifies the running FD1/FD2 destination after cutover. The private path is intentionally absent from Git and sanitized evidence.

### 3. Legacy container-side subscriber set required exact fingerprint retirement

Earlier host-side service restarts left orphaned `mosquitto_sub` processes inside the broker container. The production migration therefore captures the complete visible legacy logger set using PID + `/proc/<pid>/stat` start time + exact raw cmdline fingerprint, revalidates before targeted SIGTERM, and fails closed on any mismatch.

After an earlier rollback, the correct legacy population became one functional subscriber instead of three accidental duplicates. The final v5 preflight therefore accepted a complete exact set of one or more members rather than hard-coding the historical count of three.

### 4. `docker exec` cleanup helper requires stdin attachment

The v4 production attempt successfully migrated the logger and removed argv secrets, but failed lifecycle acceptance at:

`CUTOVER_FAILED=LIFECYCLE_STOP_PROCESS_REMAINED`

Automatic rollback passed.

The root cause was the cleanup helper transport: the wrapper supplied a shell helper via heredoc to `docker exec ... sh -s`, but omitted Docker's `-i` stdin attachment. PR #188 fixed the cleanup path to `docker exec -i` and strengthened the regression mock so cleanup is accepted only when stdin is explicitly attached.

Merged fix commit:

`a5e388e617300b03e918e9789fef2cabb2a4dc35`

The subsequent v5 production acceptance proved both:

- `MANAGED_LIFECYCLE_STOP=PASS`
- `MANAGED_LIFECYCLE_RESTART=PASS`

## Authorization ledger

Production authorizations were one-shot and scoped to exact reviewed transactions. Generic `turpini`/`continue` never authorized production mutation.

The successful v5 authorization was consumed when the transaction emitted `MUTATION_STARTED=YES`.

No #173 production authorization carries forward to any future work.

## Remaining separate security work

The legacy shared MQTT credential remains intentionally active pending a safe consumer-by-consumer migration. That work is tracked in:

- #189 — `Security: isolate and rotate legacy shared MQTT credential`

#189 requires fresh read-only discovery and its own narrow owner-gated production authorization. It must not inherit authorization from #173.

## Closeout

The original #173 finding is resolved: the balcony logger no longer exposes its MQTT credential in command-line argv, its managed subscriber lifecycle is restart-safe, broker/ESP32 health was preserved, and pump state was unchanged throughout the successful final cutover.
