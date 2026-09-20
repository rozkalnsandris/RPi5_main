# RPi5 maintenance integration boundary

## Canonical ownership

`rozkalnsandris/RPi5-maintenance` is the canonical repository for the RPi5 maintenance control-plane source, policies, tests, systemd units, release metadata, updater/monitor/post-reboot/notifier implementation, and maintenance-specific recovery operators.

`RPi5_main` must not carry an independently mutable copy of that implementation after Phase 9 extraction cleanup.

## Pinned integration baseline

- canonical repository: `rozkalnsandris/RPi5-maintenance`
- stable release: `0.2.0`
- release commit: `7a5685908e06cc35aa4bb623dd9fa6a3081c4416`
- canonical continuity: `RPi5-maintenance/HANDOFF.md`
- machine-readable boundary: `ops/maintenance/rpi5-maintenance-integration.json`

The pinned release is an integration/provenance reference. It does not prove current production deployment state and it does not authorize a deployment.

## Runtime model

Production maintenance runs from installed artifacts such as `/usr/local/sbin/rpi5-update`, `/usr/local/sbin/rpi5-monitor`, `/usr/local/sbin/rpi5-post-reboot`, `/usr/local/sbin/rpi5-maintenance-notify`, and systemd units under `/etc/systemd/system`.

Repository source is not runtime evidence. Live identity must be verified from the RPi5 before any deployment, rollback, or recovery action.

## What remains owned here

`RPi5_main` may retain host/control-plane integrations that consume maintenance contracts without becoming the maintenance implementation owner. This includes Weather/control-plane lock coordination and separately defined backup ownership. In particular, `ops/bin/rpi5-backup` and `ops/bin/rpi5-backup-serialized` remain governed by their existing ownership contract and are not removed by the maintenance extraction cleanup.

One explicit source exception remains: `ops/lib/rpi5-maintenance-locks.sh`. The active controlled-deploy manifest `ops/deploy/targets.json` still uses it as the `maintenance-lock-lib` source for the retained backup bundle. This is a backup integration dependency, not authority for `RPi5_main` to carry the rest of the maintenance implementation. The exception is machine-recorded in `ops/maintenance/rpi5-maintenance-integration.json` and must not be generalized to other maintenance helpers.

Removing or rebinding that shared-lock source requires a separate coherent migration of the backup controlled-deploy contract; deleting it as an orphan would break the current repository validation and deployment model.

## Recovery and history

Historical maintenance source remains recoverable from Git history, while the extracted implementation and release/recovery lineage live in `RPi5-maintenance`. Do not restore predecessor copies into active `RPi5_main` ownership as a rollback mechanism.

Any live install, file replacement, `systemctl daemon-reload`, service/timer mutation, cleanup, package/Docker mutation, or reboot remains a separately authorized LIVE action.
