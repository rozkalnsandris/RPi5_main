# Balcony MQTT logger authentication contract

Issue: #173

## Purpose

This document defines the reviewed source-side remediation and production cutover contract for the balcony MQTT logger credential exposure found on 2026-08-17.

The source implementation must remove MQTT authentication from process argv, preserve the current private logger output destination, and make the container-side subscriber lifecycle deterministic across service stop/restart. Production mutation remains separately owner-gated.

## Read-only live evidence

The pre-remediation audits established the following sanitized facts:

- the live unit is the root-owned system unit `/etc/systemd/system/balkons-log.service`;
- the unit is enabled and active;
- the legacy command shape is `docker exec ... mosquitto_sub ... -u <arg> -P <secret> ...`;
- the running legacy subscriber exposes the same authentication secret in argv;
- the target container is `mosquitto`;
- the local broker image is `eclipse-mosquitto:2`, Linux arm64, with exact local Mosquitto version `2.1.2`;
- host systemd is version 252 and `systemd-creds` is available;
- broker authentication uses one `password_file`, no auth plugin, and `allow_anonymous false`;
- before #173 cutover attempts, the password file contained exactly one entry and exactly one unique username;
- the logger uses that existing username, so it must be treated as shared with other authenticated clients including the ESP32;
- the live unit has exactly one `StandardOutput=` and one `StandardError=` directive;
- both live directives use `append:` and resolve to the same private absolute filesystem target;
- the target exists, is not a symlink, and the observed live metadata is root-owned mode `0644`;
- the running service FD 1 and FD 2 both resolve to that same filesystem target.

The real username, password, password hash, broker host, private log path, private network coordinates, and other private runtime values are intentionally absent from this public repository.

## Shared-credential consequence

Because there is only one pre-existing broker-side authenticated username and the logger uses it, the existing credential must be treated as **shared** for cutover planning.

Therefore #173 is a logger-only migration:

1. keep the existing shared credential unchanged;
2. add a distinct logger-only broker user;
3. move only `balkons-log.service` to the logger-only credential;
4. verify the logger no longer exposes authentication in argv;
5. leave rotation/revocation of the old shared credential to a separate owner-gated ESP32/client credential-isolation task.

The logger cutover must never delete, replace, rotate, or revoke the pre-existing broker user.

## Output-preservation consequence

The tracked unit contains `StandardOutput=journal` and `StandardError=journal` only as a safe repository fallback. Production intentionally appends both stdout and stderr to the same private filesystem target.

The private output path must not be copied into this public repository. Instead, production must preserve the exact already-running output semantics with a **runtime-only local systemd drop-in** under `/etc/systemd/system/balkons-log.service.d/`.

Immediately before mutation, the cutover must capture the exact current `StandardOutput=` and `StandardError=` directive values in memory and verify without printing the path that:

1. exactly one direct stdout directive and one direct stderr directive exist;
2. both are `append:` directives;
3. both resolve to the same absolute path;
4. the target exists and is not a symlink;
5. running FD 1 and FD 2 both point to that same target;
6. the path identity and file metadata remain stable through the pre-mutation gate.

The local drop-in contains only:

```ini
[Service]
StandardOutput=append:<captured-private-runtime-path>
StandardError=append:<captured-private-runtime-path>
```

`<captured-private-runtime-path>` is a runtime placeholder, not a literal value to commit. The deployed drop-in is private host state and must never be copied to Git, comments, CI logs, or sanitized public evidence.

Any output drift is a rollback condition even if MQTT authentication succeeds.

## Container-side subscriber lifecycle consequence

The first corrected production attempt with the portable `/proc/*/cmdline` verifier reached the new logger restart and then failed closed at `SECRET_IN_BROKER_PROCESS_ARGV`. Automatic rollback succeeded.

The tracked wrapper at that time used `exec docker exec -i mosquitto mosquitto_sub ...`. The host systemd unit therefore directly owned the Docker CLI process, while `docker exec` had created the actual `mosquitto_sub` as a process inside the already-running Mosquitto container. A host service restart was not sufficient evidence that the previous container-side subscriber had terminated.

The lifecycle contract is now explicit:

- every managed post-remediation subscriber uses the fixed, non-secret MQTT client id `balkons-log-service` unless a separately reviewed non-secret override is provided;
- the wrapper has a lifecycle cleanup mode that scans only the target container `/proc` namespace and matches an exact `mosquitto_sub` process by both that client id and the intended logger topic;
- the cleanup sends `SIGTERM` only to matching managed logger processes and waits a bounded period for them to disappear;
- no generic `pkill`, username-based kill, password-based kill, broker restart, or all-subscriber termination is allowed;
- the systemd unit uses `ExecStop=/usr/local/sbin/balkons-log-subscribe --stop` with a bounded stop timeout;
- normal startup first retires any stale subscriber carrying the same managed client id before launching a replacement;
- unrelated Mosquitto, ESP32, probe, and subscriber processes must never be targeted by lifecycle cleanup.

The first production migration still has one special case: the currently deployed legacy subscriber predates the managed client id and therefore cannot be selected by the new `ExecStop` identity.

Before the first lifecycle-aware cutover mutation, the operator must capture the **captured legacy subscriber PID**, its `/proc/<pid>/stat` start-time value, and an in-memory exact argv fingerprint proving that it is the current legacy `mosquitto_sub` for the logger topic and contains the already-known legacy auth shape. None of those private argv values may be printed.

After the old host service is stopped, the cutover may terminate that captured legacy subscriber only if all of the following still match the pre-mutation capture:

1. the same container PID still exists;
2. the process start-time value is unchanged;
3. the command is still `mosquitto_sub`;
4. the logger topic still matches;
5. the legacy auth shape still matches the in-memory preflight fingerprint.

If any fingerprint field differs, the transaction must stop and roll back rather than kill a process by guesswork.

## Reviewed source design

Tracked source consists of:

- `ops/bin/balkons-log-subscribe` — fail-closed subscriber launcher and exact managed-subscriber lifecycle cleanup;
- `ops/systemd/balkons-log.service` — systemd unit using `LoadCredential=` and explicit `ExecStop=` cleanup;
- `tests/test-balkons-log-mqtt-credential.sh` — offline regression for auth, lifecycle, and output-preservation boundaries.

The authentication path is:

```text
root-only host credential source
        -> systemd LoadCredential=
        -> $CREDENTIALS_DIRECTORY/mqtt-client-config
        -> wrapper stdin redirection
        -> docker exec -i mosquitto
        -> mosquitto_sub -o /dev/stdin
```

The managed lifecycle identity is non-secret:

```text
BALKONS_LOG_MQTT_CLIENT_ID=balkons-log-service
        -> mosquitto_sub -i balkons-log-service
        -> ExecStop exact /proc match by client id + logger topic
```

Mosquitto 2.1+ supports `-o <config-file>`, so authentication is read from `/dev/stdin` rather than command-line auth flags.

The host credential source is a Mosquitto client config with runtime-only values, for example:

```text
-u <logger-only-runtime-user>
-P <logger-only-runtime-secret>
```

That file is never tracked. The source unit maps it to the systemd credential ID `mqtt-client-config`.

## Non-secret runtime configuration

The unit reads `/etc/default/balkons-log`. This file contains only non-secret operational values needed to preserve subscriber behavior:

- `BALKONS_LOG_MQTT_HOST`;
- `BALKONS_LOG_MQTT_TOPIC`;
- `BALKONS_LOG_MQTT_FORMAT`;
- optionally `BALKONS_LOG_MQTT_CONTAINER` if the target differs from `mosquitto`;
- optionally `BALKONS_LOG_MQTT_CLIENT_ID` if a later reviewed deployment intentionally changes the default non-secret lifecycle id.

Authentication values must not be placed in that environment file. The private output path also remains runtime-only and belongs only in the local systemd output-preservation drop-in.

## Failure behavior

Normal start fails closed before launching a subscriber when:

- `$CREDENTIALS_DIRECTORY` is absent;
- the `mqtt-client-config` credential is missing, unreadable, empty, or a symlink;
- a required non-secret host/topic/format value is absent;
- the Docker client executable is unavailable;
- the managed client id is malformed;
- a stale managed subscriber cannot be retired exactly and within the bounded timeout.

Stop cleanup fails closed when an exact managed subscriber remains after the bounded `SIGTERM` wait.

The wrapper never falls back to `-u`, `-P`, an authentication URL, or environment-based secrets.

## Offline regression gate

The regression test replaces Docker with a local mock and performs no network, broker, container, MQTT, Home Assistant, or pump operation. It verifies that:

1. the complete mock authentication config is delivered through stdin;
2. Docker argv contains `exec -i`, `mosquitto_sub`, and `-o /dev/stdin`;
3. the password sentinel is absent from argv;
4. username/password CLI flags are absent from argv;
5. the non-secret managed client id is present;
6. pre-start lifecycle cleanup is invoked;
7. `--stop` invokes lifecycle cleanup without starting another subscriber;
8. the tracked systemd unit uses `LoadCredential=`, the reviewed wrapper, and `ExecStop=`;
9. stop handling is bounded by `TimeoutStopSec`;
10. authentication is not placed in the unit environment;
11. missing and symlink credentials fail closed;
12. tracked `journal` output directives remain explicitly fallback-only;
13. the production contract requires the runtime-only append-preservation drop-in;
14. the production contract requires exact one-time legacy subscriber retirement;
15. public source contains no literal private append destination.

`make validate` includes this regression together with the repository secret scan and public-safety guard.

## Prepared logger-only production cutover

A production cutover requires a separate explicit owner authorization. It is one bounded transaction with a rollback point before every externally visible mutation.

### Gate 0 — exact source and live-state preflight

Immediately before mutation:

1. self-bind current `RPi5_main/main` and require the reviewed #173 contract to remain an ancestor;
2. verify exact wrapper/unit bytes and focused regression;
3. confirm the live unit is still enabled, active, and using the known legacy argv-exposed form;
4. confirm the Mosquitto container is running with unchanged restart count and remains Mosquitto 2.1.2 arm64;
5. confirm broker auth still has `allow_anonymous false`, one password-file directive, and exactly one existing unique username before the additive logger identity is created;
6. confirm the logger still uses that existing username;
7. capture and validate the private stdout/stderr append target and FD 1/FD 2 identity;
8. prove the portable container `/proc/*/cmdline` inspector can see the known legacy logger process without printing argv;
9. capture the legacy subscriber PID, its `/proc/<pid>/stat` start-time value, and exact in-memory logger fingerprint required by the one-time retirement rule;
10. abort on any relevant source, broker, logger, lifecycle, or output-semantics drift.

### Gate 1 — backup and rollback capture

Before changing password-file or systemd state:

1. create a root-only rollback directory with mode `0700`;
2. copy the live `balkons-log.service` preserving metadata;
3. copy the resolved broker password file preserving metadata;
4. back up any pre-existing `/etc/default/balkons-log`, credential source, installed wrapper, and output-preservation drop-in state;
5. verify required backups before continuing;
6. retain only sanitized metadata/checksum evidence.

If backup verification fails, stop with no further mutation.

### Gate 2 — create a logger-only broker identity

The new logger username must be distinct from the existing shared username.

The new password must be generated/entered without putting it in argv, environment variables, shell history, logs, Git, or terminal output. `mosquitto_passwd -b` is forbidden.

After interactive password-file tooling succeeds:

1. verify the original password-file entry is byte-identical;
2. verify total entry count increased from one to two;
3. verify two unique usernames exist;
4. preserve password-file owner/group/mode;
5. print no username or password hash.

### Gate 3 — reload broker authentication only

Reload Mosquitto authentication with its reload signal; do not restart or recreate the broker container.

After reload:

1. confirm the container remains running;
2. confirm restart count did not increase;
3. confirm password-file readability;
4. prove old shared auth still works;
5. prove new logger-only auth works;
6. prove ESP32 remains online and pump retained state is unchanged.

### Gate 4 — install lifecycle-aware logger path and retire the exact legacy subscriber

With broker health proven:

1. create the protected root-only logger Mosquitto client config;
2. create `/etc/default/balkons-log` from existing live non-secret host/topic/format semantics only;
3. install the reviewed lifecycle-aware `balkons-log-subscribe` wrapper;
4. install the reviewed `balkons-log.service` unit containing `ExecStop=`;
5. create the runtime-only local output-preservation drop-in from the exact captured private append target;
6. verify unit, wrapper, credential, runtime env, and drop-in metadata/content structurally;
7. run systemd unit verification;
8. run `systemctl daemon-reload`;
9. prove effective output remains the captured append target before stopping the old service;
10. stop **only** `balkons-log.service`;
11. inspect the previously captured legacy container PID; if it is gone, continue; if it remains, require the exact captured start-time and argv fingerprint to still match and then send `SIGTERM` only to that PID;
12. wait a bounded interval and require the captured legacy process to disappear;
13. scan the Mosquitto container and require that no process argv contains the legacy secret before starting the replacement;
14. start **only** `balkons-log.service` on the reviewed lifecycle-aware unit.

The Mosquitto broker container, ESP32, Home Assistant, watering automation, and pump must not be restarted or changed during this gate.

### Gate 5 — post-cutover verification

The cutover is accepted only if all of these pass:

1. `balkons-log.service` is active/running and does not enter a restart loop;
2. effective systemd `ExecStart` contains no username/password argument;
3. `/proc/<MainPID>/cmdline` contains no auth flag, old/new secret, or auth value;
4. the subscriber uses `docker exec -i ... mosquitto_sub -o /dev/stdin`;
5. the managed subscriber argv contains the reviewed non-secret client id;
6. whole-container `/proc/*/cmdline` inspection finds neither the old nor new secret in any process argv;
7. exactly one managed logger subscriber exists for the reviewed client id + logger topic;
8. an explicit stop/start lifecycle can retire the managed subscriber through `ExecStop=` and recreate exactly one replacement without leaving a stale managed process;
9. logger subscription to the intended `balkons/log` stream succeeds without printing payload evidence;
10. effective stdout/stderr still select the exact pre-cutover private append target;
11. running FD 1 and FD 2 resolve to that same pre-cutover target;
12. the Mosquitto container remains running with unchanged restart count;
13. ESP32 remains MQTT-connected and healthy;
14. pump state remains unchanged and no pump command is issued.

Only sanitized structural evidence is retained.

### Gate 6 — completion boundary

After successful logger cutover:

- keep the original shared broker username/password active;
- do not change ESP32 credentials in #173;
- do not revoke the original shared credential in #173;
- keep the logger private append output target unchanged;
- record that logger argv exposure and container lifecycle are remediated;
- track historical shared-credential isolation/rotation separately.

## Rollback contract

Rollback is allowed without improvising new configuration.

### Before broker reload

Restore the password-file backup and stop.

### After broker reload but before logger stop/start

Restore the password-file backup, reload Mosquitto authentication, verify broker/ESP32 health, and stop.

### After lifecycle-aware unit installation or logger stop/start

1. stop the lifecycle-aware logger if it is running;
2. use its exact managed client-id cleanup to retire any managed container-side subscriber;
3. restore the previous live unit, installed wrapper/runtime files, credential source, and output-drop-in state from backup;
4. restore the password-file backup;
5. reload Mosquitto authentication;
6. run `systemctl daemon-reload`;
7. restart only `balkons-log.service` on its previous configuration;
8. verify the previous logger is active, FD 1/FD 2 again resolve to the captured private append target, Mosquitto/ESP32 remain healthy, and pump state is unchanged.

The pre-existing shared credential is never revoked during this transaction, so rollback does not require an ESP32 credential change.

## Production boundary

Preparation/source review does **not** authorize any of the following:

- editing live systemd files or runtime drop-ins;
- creating `/etc/default/balkons-log`;
- creating or altering a live credential source;
- modifying the broker password file;
- signaling/reloading Mosquitto;
- stopping, starting, or restarting `balkons-log.service`;
- terminating any live container process;
- executing an MQTT client against the live broker;
- rotating or revoking any MQTT credential;
- publishing MQTT;
- changing ESP32 firmware/connectivity;
- issuing any pump command.

Production deploy: **NO — an explicit owner authorization is required for the bounded lifecycle-aware logger-only cutover after source merge and exact-main CI.**
