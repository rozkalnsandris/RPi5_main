# Balcony MQTT logger authentication contract

Issue: #173

## Purpose

This document defines the reviewed source-side remediation for the balcony MQTT logger credential exposure found on 2026-08-17. It is a **source contract only**. It does not authorize installation, service reload/restart, broker mutation, MQTT credential rotation, ESP32 changes, MQTT publication, or pump activation.

## Read-only live evidence

The pre-remediation audit established the following sanitized facts:

- the live unit is the root-owned system unit `/etc/systemd/system/balkons-log.service` with no drop-ins;
- the unit is enabled and active;
- its current command shape is `docker exec ... mosquitto_sub ... -u <arg> -P <secret> ...`;
- the running process also exposes the same authentication secret in argv;
- the target container is `mosquitto`;
- the local broker image is `eclipse-mosquitto:2`, Linux arm64, with exact local Mosquitto version `2.1.2`;
- host systemd is version 252 and `systemd-creds` is available.

The real username, password, broker host, output format, private network coordinates, and other private runtime values are intentionally absent from this public repository.

## Reviewed source design

Tracked source consists of:

- `ops/bin/balkons-log-subscribe` — fail-closed subscriber launcher;
- `ops/systemd/balkons-log.service` — systemd unit using `LoadCredential=`;
- `tests/test-balkons-log-mqtt-credential.sh` — offline regression for the argv boundary.

The authentication path is:

```text
root-only host credential source
        -> systemd LoadCredential=
        -> $CREDENTIALS_DIRECTORY/mqtt-client-config
        -> wrapper stdin redirection
        -> docker exec -i mosquitto
        -> mosquitto_sub -o /dev/stdin
```

Mosquitto 2.1+ supports `-o <config-file>`. The deployed 2.1.2 client therefore can read its authentication options from `/dev/stdin` instead of receiving them in command-line arguments.

The host credential source is a Mosquitto client config with runtime-only values, for example:

```text
-u <runtime-user>
-P <new-runtime-secret>
```

That file is never tracked. The source unit maps it to the systemd credential ID `mqtt-client-config`.

## Non-secret runtime configuration

The unit reads `/etc/default/balkons-log`. This file must contain **only non-secret** operational values needed to preserve the existing subscriber behavior:

- `BALKONS_LOG_MQTT_HOST`;
- `BALKONS_LOG_MQTT_TOPIC`;
- `BALKONS_LOG_MQTT_FORMAT`;
- optionally `BALKONS_LOG_MQTT_CONTAINER` if the target differs from the default `mosquitto`.

Authentication values must not be placed in that environment file. The production cutover must copy the existing non-secret host/topic/format semantics from the live unit without publishing them to GitHub.

## Failure behavior

The wrapper exits before invoking Docker when:

- `$CREDENTIALS_DIRECTORY` is absent;
- the `mqtt-client-config` credential is missing, unreadable, or empty;
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
7. missing credentials fail closed.

`make validate` includes this regression together with the repository secret scan and public-safety guard.

## Owner-gated production cutover contract

A later production change requires a separate explicit owner authorization. Before any mutation it must take a fresh backup and record a rollback path. The bounded cutover order is:

1. re-check the live unit, container identity, Mosquitto version, broker health, ESP32 MQTT health, and subscriber state;
2. back up the existing live unit and any related host-only runtime configuration;
3. generate a **new** MQTT logger credential without printing or committing it;
4. create the protected root-only Mosquitto client config for `LoadCredential=`;
5. create the non-secret `/etc/default/balkons-log` values from the existing live host/topic/format behavior;
6. install the reviewed wrapper and unit;
7. daemon-reload and restart only `balkons-log.service`;
8. verify sanitized `systemctl` and `/proc/<pid>/cmdline` evidence contains no authentication secret or password CLI flag;
9. verify the subscriber still receives `balkons/log` and that the ESP32 remains MQTT-connected and healthy;
10. only after the new path is proven healthy, revoke the old exposed credential;
11. if any verification fails before old-credential revocation, restore the backup and restart the previous unit while keeping the pump untouched.

The old credential is considered exposed because it has existed in argv. Source merge does not rotate or revoke it.

## Production boundary

This source change deliberately does **not**:

- edit `/etc/systemd/system/balkons-log.service`;
- create `/etc/default/balkons-log`;
- create or alter a live credential source;
- run `systemctl daemon-reload`, restart, or enable a service;
- execute `docker exec`;
- alter the Mosquitto broker or password database;
- rotate or revoke any MQTT credential;
- publish MQTT;
- change ESP32 firmware or connectivity;
- issue any pump command.

Production deploy: **NO — explicit owner authorization is required later.**
