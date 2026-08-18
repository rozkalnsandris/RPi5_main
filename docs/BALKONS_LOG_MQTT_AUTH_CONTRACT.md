# Balcony MQTT logger authentication contract

Issue: #173

## Purpose

This document defines the reviewed source-side remediation and production cutover contract for the balcony MQTT logger credential exposure found on 2026-08-17.

The source implementation removes MQTT authentication from process argv. Production mutation remains separately owner-gated.

## Read-only live evidence

The pre-remediation audits established the following sanitized facts:

- the live unit is the root-owned system unit `/etc/systemd/system/balkons-log.service` with no drop-ins;
- the unit is enabled and active;
- its current command shape is `docker exec ... mosquitto_sub ... -u <arg> -P <secret> ...`;
- the running process also exposes the same authentication secret in argv;
- the target container is `mosquitto`;
- the local broker image is `eclipse-mosquitto:2`, Linux arm64, with exact local Mosquitto version `2.1.2`;
- host systemd is version 252 and `systemd-creds` is available;
- broker authentication uses one `password_file`, no auth plugin, and `allow_anonymous false`;
- the password file contains exactly one entry and exactly one unique username;
- the logger uses that single username;
- available broker logs are rotated and do not cover broker start, so historical connection logs cannot prove that the single username was logger-only;
- the live unit has exactly one `StandardOutput=` and one `StandardError=` directive;
- both live directives use `append:` and resolve to the same private absolute filesystem target;
- the target exists, is not a symlink, and the observed live metadata is root-owned mode `0644`;
- the running service's FD 1 and FD 2 both resolve to that same filesystem target, proving the append sink is active runtime behavior rather than stale unit text.

The real username, password, password hash, broker host, output format, private log path, private network coordinates, and other private runtime values are intentionally absent from this public repository.

## Security consequence of the privileged preflight

The original source contract assumed that the old credential could be revoked after the logger was moved to a new path. The privileged read-only preflight disproved that assumption.

Because there is only one broker-side authenticated username and the logger uses it, the existing credential must be treated as **shared** for cutover planning. Revoking or changing it as part of the logger cutover could disconnect the ESP32 or another authenticated client.

Therefore #173 uses a logger-only migration:

1. keep the existing shared credential unchanged;
2. add a distinct logger-only broker user;
3. move only `balkons-log.service` to the logger-only credential;
4. verify the logger no longer exposes authentication in argv;
5. leave rotation/revocation of the old shared credential to a separate owner-gated ESP32/client credential-isolation task.

The logger cutover must never delete, replace, rotate, or revoke the pre-existing broker user.

## Output-preservation consequence of the final live gate

The tracked unit contains `StandardOutput=journal` and `StandardError=journal` only as a safe repository fallback. The final owner-authorized cutover preflight proved that those values are **not production-equivalent** to the current logger: production intentionally appends both stdout and stderr to the same private filesystem target.

The private output path must not be copied into this public repository. Instead, the production cutover must preserve the exact already-running output semantics with a **runtime-only local systemd drop-in** under `/etc/systemd/system/balkons-log.service.d/`.

Immediately before any mutation, the cutover must capture the exact current `StandardOutput=` and `StandardError=` directive values in memory and verify all of the following without printing the path:

1. exactly one direct stdout directive and one direct stderr directive exist;
2. both are `append:` directives;
3. both resolve to the same absolute path;
4. the target exists and is not a symlink;
5. the running FD 1 and FD 2 both point to that same target;
6. the path and file metadata remain stable through the pre-mutation gate.

The cutover may then create a root-owned local drop-in, for example `90-output-preserve.conf`, containing only:

```ini
[Service]
StandardOutput=append:<captured-private-runtime-path>
StandardError=append:<captured-private-runtime-path>
```

`<captured-private-runtime-path>` is a runtime placeholder in this document, not a literal value to commit. The deployed drop-in is private host state and must never be copied to Git, comments, CI logs, or sanitized public evidence.

After restart, acceptance requires both systemd's effective output configuration and the running process FD 1/FD 2 to resolve to the same pre-cutover private append target. A cutover that changes logger output to journal, another file, a pipe, a socket, or any other target is a rollback condition even if MQTT authentication succeeds.

## Reviewed source design

Tracked source consists of:

- `ops/bin/balkons-log-subscribe` — fail-closed subscriber launcher;
- `ops/systemd/balkons-log.service` — systemd unit using `LoadCredential=`;
- `tests/test-balkons-log-mqtt-credential.sh` — offline regression for the argv and runtime-output-preservation boundaries.

The authentication path is:

```text
root-only host credential source
        -> systemd LoadCredential=
        -> $CREDENTIALS_DIRECTORY/mqtt-client-config
        -> wrapper stdin redirection
        -> docker exec -i mosquitto
        -> mosquitto_sub -o /dev/stdin
```

Mosquitto 2.1+ supports `-o <config-file>`. The deployed 2.1.2 client can therefore read authentication options from `/dev/stdin` instead of receiving them in command-line arguments.

The host credential source is a Mosquitto client config with runtime-only values, for example:

```text
-u <logger-only-runtime-user>
-P <logger-only-runtime-secret>
```

That file is never tracked. The source unit maps it to the systemd credential ID `mqtt-client-config`.

## Non-secret runtime configuration

The unit reads `/etc/default/balkons-log`. This file must contain **only non-secret** operational values needed to preserve the existing subscriber behavior:

- `BALKONS_LOG_MQTT_HOST`;
- `BALKONS_LOG_MQTT_TOPIC`;
- `BALKONS_LOG_MQTT_FORMAT`;
- optionally `BALKONS_LOG_MQTT_CONTAINER` if the target differs from the default `mosquitto`.

Authentication values must not be placed in that environment file. The production cutover must copy the existing non-secret host/topic/format semantics from the live unit without publishing them to GitHub.

The private output path is also runtime-only, but it belongs in the local systemd output-preservation drop-in described above, not in `/etc/default/balkons-log`.

## Failure behavior

The wrapper exits before invoking Docker when:

- `$CREDENTIALS_DIRECTORY` is absent;
- the `mqtt-client-config` credential is missing, unreadable, empty, or a symlink;
- a required non-secret host/topic/format value is absent;
- the Docker client executable is unavailable.

It never falls back to `-u`, `-P`, an authentication URL, or environment-based secrets.

## Offline regression gate

The regression test replaces Docker with a local mock and performs no network, broker, container, MQTT, Home Assistant, or pump operation. It verifies that:

1. the complete mock authentication config is delivered through stdin;
2. Docker argv contains `exec -i`, `mosquitto_sub`, and `-o /dev/stdin`;
3. the password sentinel is absent from argv;
4. username/password CLI flags are absent from argv;
5. the tracked systemd unit uses `LoadCredential=` and the reviewed wrapper;
6. authentication is not placed in the unit environment;
7. missing and symlink credentials fail closed;
8. the tracked `journal` output directives are explicitly documented as fallback-only;
9. the production contract requires a runtime-only local drop-in that preserves the pre-existing private `append:` stdout/stderr target;
10. the public source does not contain a literal private append destination.

`make validate` includes this regression together with the repository secret scan and public-safety guard.

## Prepared logger-only production cutover

A production cutover requires a separate explicit owner authorization. It is one bounded transaction with a rollback point before every externally visible mutation.

### Gate 0 — exact source and live-state preflight

Immediately before mutation:

1. self-bind the current `RPi5_main/main` revision and require the reviewed #173 contract to remain an ancestor;
2. verify the exact wrapper/unit bytes and focused regression rather than failing only because unrelated `main` commits landed;
3. confirm the live unit is still enabled, active, and using the known argv-exposed form;
4. confirm the `mosquitto` container is running, its restart count is unchanged, and the image remains Mosquitto 2.1.2 arm64;
5. confirm broker auth still has `allow_anonymous false`, one password-file directive, and exactly one existing unique username;
6. confirm the logger still uses that existing username;
7. capture and validate the existing private stdout/stderr `append:` directives and running FD 1/FD 2 target as described in the output-preservation section;
8. abort if broker auth topology or logger output semantics changed since the privileged preflight.

### Gate 1 — backup and rollback capture

Before changing the password file or systemd:

1. create a root-only rollback directory with mode `0700`;
2. copy the live `balkons-log.service` preserving metadata;
3. copy the resolved broker password file preserving metadata;
4. back up any pre-existing `/etc/default/balkons-log`, credential source, installed wrapper, or output-preservation drop-in if present;
5. record sanitized SHA256, owner, group, mode, and output-target identity evidence without printing usernames, hashes, secrets, or the private path;
6. verify all required backups exist before continuing.

If backup verification fails, stop with no mutation.

### Gate 2 — create a logger-only broker identity

The new logger username must be distinct from the existing shared username.

The new password must be entered/generated without putting it in argv, environment variables, shell history, logs, Git, or terminal output. Do not use `mosquitto_passwd -b` because batch mode places the password on the command line.

Use the installed Mosquitto password-file tooling in its interactive password-entry mode. After it succeeds:

1. verify the broker password file still contains the original entry;
2. verify total entry count increased from one to two;
3. verify there are two unique usernames;
4. verify no username or password hash is printed as evidence;
5. preserve the password-file owner/group/mode expected by the running broker.

If any structural check fails, restore the password-file backup before any broker reload.

### Gate 3 — reload broker authentication only

Reload Mosquitto configuration/password data with the broker's reload signal; do not restart/recreate the container.

After reload:

1. confirm the container remains running;
2. confirm its restart count did not increase;
3. confirm the broker did not terminate or enter a restart loop;
4. confirm the password file is still readable by the broker;
5. do not disconnect or restart ESP32.

A password-file reload changes future authentication checks but must not be used to revoke the original shared username during #173.

If broker health fails, restore the password-file backup, reload the broker again, verify health, and stop before logger installation.

### Gate 4 — install logger-only systemd path without changing log destination

With broker health proven:

1. create the protected root-only Mosquitto client config for the new logger-only username/password;
2. create `/etc/default/balkons-log` from the existing live non-secret host/topic/format semantics only;
3. install the reviewed `balkons-log-subscribe` wrapper;
4. install the reviewed `balkons-log.service` unit;
5. create the runtime-only local output-preservation drop-in from the exact captured pre-cutover stdout/stderr append directives;
6. verify the drop-in is root-owned, not a symlink, and contains exactly one `[Service]`, `StandardOutput=append:<captured-private-runtime-path>`, and `StandardError=append:<captured-private-runtime-path>` with no additional directives;
7. run systemd unit verification with the local drop-in present;
8. run `systemctl daemon-reload`;
9. before restart, inspect the effective unit and prove the private append target is still selected without printing its path;
10. restart **only** `balkons-log.service`.

The Mosquitto broker container, ESP32, Home Assistant, watering automation, and pump must not be restarted or changed during this gate.

### Gate 5 — post-cutover verification

The cutover is accepted only if all of these pass:

1. `balkons-log.service` is active/running and does not enter a restart loop;
2. the effective systemd `ExecStart` contains no username/password argument;
3. `/proc/<MainPID>/cmdline` contains neither a password flag nor the old/new secret;
4. the subscriber uses `docker exec -i ... mosquitto_sub -o /dev/stdin`;
5. the logger continues receiving the intended `balkons/log` stream without printing payload evidence into the audit;
6. effective stdout and stderr still select the exact pre-cutover private `append:` target;
7. running FD 1 and FD 2 are filesystem descriptors for that same pre-cutover target;
8. the Mosquitto container remains running with unchanged restart count;
9. ESP32 remains MQTT-connected and healthy;
10. no pump command is issued and watering state is not changed by the verification.

Only sanitized structural evidence is retained.

### Gate 6 — completion boundary

After a successful logger cutover:

- keep the original shared broker username and password active;
- do **not** change ESP32 credentials in #173;
- do **not** revoke the original shared credential in #173;
- keep the logger's pre-existing private append output target unchanged;
- record that the logger argv exposure has been removed but the historically exposed shared credential still requires a separate credential-isolation/rotation task;
- keep #173 open until that follow-up relationship is recorded and the owner decides whether closure of #173 is appropriate or whether the credential-compromise portion remains tracked here.

## Rollback contract

Rollback is allowed without improvising new configuration.

### Before broker reload

Restore the password-file backup and stop. No service change is required.

### After broker reload but before logger restart

Restore the password-file backup, reload Mosquitto authentication, verify broker health, and stop.

### After logger restart

1. restore the previous live unit and previous installed wrapper/runtime files from backup;
2. restore the previous output-preservation drop-in state exactly: restore it if one existed before, otherwise remove the newly created drop-in;
3. restore the password-file backup;
4. reload Mosquitto authentication;
5. run `systemctl daemon-reload`;
6. restart only `balkons-log.service` on its previous configuration;
7. verify the previous logger is active, FD 1/FD 2 again resolve to the captured pre-cutover private append target, and Mosquitto/ESP32 remain healthy;
8. leave the pump untouched.

The pre-existing shared credential is never revoked during this transaction, so rollback does not require an ESP32 credential change.

## Production boundary

Preparation/source review does **not** authorize any of the following:

- editing `/etc/systemd/system/balkons-log.service`;
- creating or changing `/etc/systemd/system/balkons-log.service.d/` runtime drop-ins;
- creating `/etc/default/balkons-log`;
- creating or altering a live credential source;
- modifying the broker password file;
- signaling or reloading Mosquitto;
- running `systemctl daemon-reload` or restarting a service;
- executing an MQTT client against the live broker;
- rotating or revoking any MQTT credential;
- publishing MQTT;
- changing ESP32 firmware or connectivity;
- issuing any pump command.

Production deploy: **NO — an explicit owner authorization is required for the bounded logger-only cutover.**
