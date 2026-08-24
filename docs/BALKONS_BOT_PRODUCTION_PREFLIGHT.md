# Balkons bot production preflight contract

Issue: `RPi5_main#192`

This document defines the **source-only** production preflight artifact for the
Git-tracked `balkons-bot` source introduced by PR #193.

It does not authorize or perform deployment, service lifecycle changes, credential
creation/change, broker mutation, Home Assistant changes, ESP32 changes, MQTT
publish/probe, or pump commands.

## Current source binding

The preflight artifact is prepared from canonical `RPi5_main/main` after PR #193
was squash-merged.

At source preparation time:

- canonical main: `faaa5ccea3f10edd14119cdcd57ea5c82c246d00`
- merged source PR: #193
- canonical H3 live-source provenance SHA256:
  `54e7c58bae49a4a78fc033bd86eaa752cf21583bb86a0ba10d7ba9a617b1afd9`

The future live preflight must be invoked with the exact reviewed repository SHA
that contains the preflight artifact. It fails closed when the checkout HEAD does
not match that expected SHA.

## Strict read-only allowlist

`ops/bin/balkons-bot-preflight` may perform only these read-only operations:

1. `git rev-parse HEAD` for exact repository identity;
2. `git status --porcelain` limited to the tracked bot source, systemd template and
   preflight artifact;
3. one `systemctl show balkons-bot.service` call restricted to these properties:
   `LoadState`, `ActiveState`, `SubState`, `User`, `ExecStart`, `Restart`,
   `RestartUSec`, `TimeoutStopUSec`, `SendSIGKILL`, and `FragmentPath`;
4. hash the single absolute Python source path derived from `ExecStart`;
5. invoke the same Python interpreter with a fixed `-c` probe that returns only
   the installed `paho-mqtt` version and whether `CallbackAPIVersion` exists;
6. hash the tracked source, tracked unit template, and preflight artifact itself.

The artifact must not:

- call `systemctl cat`, `status`, `restart`, `reload`, `stop`, `start`, `enable`,
  `disable`, `kill`, or `daemon-reload`;
- read process/container environments, `/proc/*/environ`, Docker runtime/config,
  journal contents, raw systemd unit files, credential files, `.env` files, Home
  Assistant storage/config, broker configuration, or backups;
- invoke MQTT clients or publish/probe any MQTT topic;
- write files or modify the host.

The live Python source is secret-bearing historical evidence. The artifact may
stream its bytes only to compute SHA256; source bytes and its absolute path must
never be printed.

## Sanitized output contract

The preflight prints one JSON object. Public output may include:

- expected and observed Git SHA;
- SHA256 of the preflight artifact, tracked bot source and tracked unit template;
- exact live-source SHA256 and whether it matches the reviewed H3 provenance;
- service load/active/sub states;
- lifecycle values (`Restart`, `RestartUSec`, `TimeoutStopUSec`, `SendSIGKILL`);
- installed Paho version and compatibility class;
- blocker codes and final `PASS` / `BLOCKED` state.

Private runtime identity is represented only by SHA256:

- service user;
- Python executable path;
- live bot source path;
- systemd fragment path.

The JSON must not contain the actual service user, executable path, live source
path, unit path, source content, credentials, command payloads, private addresses,
or raw subprocess error text.

## Fail-closed gates

The preflight is `PASS` only when all of the following hold:

- expected repository SHA and live-source SHA inputs are structurally valid;
- repository HEAD equals the expected SHA;
- the critical tracked paths are clean;
- the service is loaded and `active/running`;
- a single absolute Python source can be derived from `ExecStart`;
- the live source exists and its SHA256 matches the reviewed expected provenance;
- the service user and fragment path are present;
- `SendSIGKILL=no`;
- the Paho compatibility probe succeeds and returns a bounded version string plus
  versioned/legacy callback classification.

Any parse failure, unexpected command failure, provenance drift, ambiguous
`ExecStart`, dirty critical path or lifecycle mismatch returns `BLOCKED` without
printing private data.

## Authorization boundary

Preparing, reviewing and merging this artifact is source-only work.

**Running it on the RPi5 is not authorized by generic `turpini`.** Although the
artifact is read-only, the live run intentionally reads protected runtime metadata
and hashes the secret-bearing historical source. Under the repository's FAST-LANE
v2.2 contract, that live inspection is part of a separately authorized Composite
STRICT preflight.

A future Composite Live authorization must bind at minimum:

- exact merged `RPi5_main` SHA containing this artifact;
- exact SHA256 of `ops/bin/balkons-bot-preflight`;
- exact host/target;
- expected H3 live-source SHA256 or an explicitly reviewed successor;
- read-only preflight scope and explicit no-mutation boundary.

A `PASS` result still does **not** authorize deployment. It is evidence for the
next source-only step: prepare and review the production deployment/rollback
artifact bound to the observed sanitized lifecycle/identity contract.

## Relationship to #189 and #194

This preflight does not revoke or rotate the legacy shared MQTT credential tracked
by #189.

It also does not implement #194's delivery/client-ID hardening. The production
preflight for #192 preserves the #193 transport contract; stable client identity,
QoS changes, retries and command-class delivery policy remain isolated to #194.
