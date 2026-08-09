# V24 RPi5 maintenance cleanup ownership contract

## Status

Repository-only implementation for issue #98. Production unchanged.

V24 removes name-based retention cleanup from the maintenance user's home and narrows custom deletion to artifacts that the weekly updater itself owns. It also makes `--cleanup-only` useful as a degraded recovery path when Docker/Compose is unavailable instead of requiring a healthy application stack before non-Docker cleanup can begin.

V24 builds on the merged V21 updater and V22/V23 health/systemd work. It does not install, activate, delete production files, prune Docker state, modify cron/systemd, or run cleanup on the RPi5 by itself.

## Incident-derived ownership rule

The 2026-08-09 incident was caused by a home cleanup that removed operational scripts while cron still referenced them. The repaired V21 updater still inherited broad historical retention patterns under the maintenance user's home. Even with age, maxdepth and xdev guards, names such as `rpi5-*` are not proof of ownership.

V24 therefore adopts a strict rule:

> Automatic weekly retention may delete a custom path only when the updater can prove that path belongs to an artifact class created by the updater itself.

User-home content, recovery evidence, backup directories, symlinks and deploy/repair scripts are not inferred disposable from their names.

## Custom deletion allowlist

The pure helper `ops/lib/rpi5-update-cleanup-policy.sh` recognizes exactly two custom retention classes:

1. direct children matching `/tmp/rpi5-update-*` — updater-created temporary run directories;
2. direct children matching `/var/log/rpi5-update.log.*` — updater log rotations.

Nested paths and every other location are rejected.

The updater deletion functions call this helper immediately before `rm`; the allowlist is therefore an execution boundary, not documentation only.

## Explicitly removed automatic home cleanup

V24 removes automatic scans/deletions for:

- `$UPDATE_HOME/update-script-backups`;
- `$UPDATE_HOME/rpi5_*.log` and `$UPDATE_HOME/rpi5-*.log`;
- `$UPDATE_HOME/rpi5-*-backup-20*`;
- `$UPDATE_HOME/cloudflare-ufw-backup-20*`;
- `$UPDATE_HOME/rpi5-*-latest-backup` symlinks;
- `/tmp/rpi5_*.sh`, `/tmp/rpi5-*.sh`, and `/tmp/deploy_rpi5_*.sh`.

This means recovery/deploy artifacts and future control-plane files cannot be deleted merely because they share an RPi5 naming convention.

## System/package cleanup that remains

The following bounded system-managed cleanup remains:

- `apt-get autoclean -y` for package-cache data APT itself considers obsolete;
- `journalctl --rotate --vacuum-time=...` for journal retention;
- `systemd-tmpfiles --clean` for administrator/package-defined tmpfiles age policy;
- Docker dangling-image pruning with a retention filter;
- Docker build-cache pruning with a retention filter.

The updater still does **not** prune Docker volumes, containers, networks, or all unused/tagged images.

## `--cleanup-only` degraded recovery semantics

Normal `run` and `check` keep strict Docker/Compose preflight. `cleanup-only` has a different purpose and therefore uses a narrower dependency boundary.

In cleanup mode:

- normal free-space/inode minimum thresholds do not block cleanup from starting;
- Compose capability checks are skipped;
- Compose config validation is skipped;
- Compose runtime validation is skipped;
- Hermes update capability checks are skipped;
- if the Docker CLI is absent, Docker cleanup is skipped, the result is marked degraded/nonzero, and non-Docker cleanup continues;
- if the Docker CLI exists but the daemon is unavailable, Docker cleanup is skipped, the result is marked degraded/nonzero, and non-Docker cleanup continues;
- Docker `system df` is only called when Docker is available.

A partial cleanup is never reported as fully successful merely because the non-Docker steps completed.

## Control-plane boundary

Maintenance executables are owned under `/usr/local/sbin`; internal maintenance helpers are owned under the canonical `/usr/local/lib/rpi5-maintenance`; systemd units are under `/etc/systemd/system`; scheduler state is under `/var/lib/rpi5-maintenance-scheduler`.

The former `/usr/local/libexec/rpi5-maintenance` helper root is not part of the reviewed merged control plane and V24 must not reintroduce it.

None of those control-plane paths is part of V24 custom retention cleanup.

The V23 cutover operator is extended so `rpi5-update-cleanup-policy.sh` is installed and validated together with the updater. A production install cannot intentionally deploy the V24 updater without its ownership-policy helper.

## Public repository boundary

V24 preserves the public-safe V21 design: no concrete maintenance-user home path, RFC1918 host address, credentials, required-container inventory or root-only configuration content is tracked in the updater source.

## Repository gates

- pure allowlist tests accept only updater temp directories and updater log rotations;
- nested paths and control/recovery paths are rejected;
- source-level test forbids historical home/tmp wildcard cleanup markers;
- source-level test requires Docker-degraded cleanup semantics;
- source-level test requires Compose/Hermes preflight bypass in cleanup mode only;
- source-level test proves the V23 installer ships the new helper under `/usr/local/lib/rpi5-maintenance`;
- exact updater SHA256/Git-blob/size/mode remains bound through the provenance manifest and source ownership test;
- V24 provenance derives from the merged FHS-correct V21 candidate, not stale pre-FHS stacked artifacts;
- public-safety and full-history secret scan remain mandatory;
- temporary transform workflows must be absent before PR readiness.

## Production boundary

Merge does not authorize running `--cleanup-only`, deleting any host artifact, pruning Docker cache/images, installing V24, modifying cron/systemd, or changing retention settings. Production adoption remains the later explicit migration transaction in #123 with live preflight and rollback evidence.
