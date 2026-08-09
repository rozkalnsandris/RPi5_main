# V21 weekly maintenance updater ownership contract

## Status

**Reviewed successor import in progress. Production unchanged.**

This phase moves the existing RPi5 weekly maintenance updater out of the interactive user's home directory and into reviewed host-infrastructure ownership. The intended installed target is `/usr/local/sbin/rpi5-update`; private runtime configuration remains outside Git.

Issue #95 owns the updater import. Issues #96-#98 separately own monitor/post-reboot privilege repair, systemd scheduling, and cleanup-path regression protection. This split prevents a source-ownership change from silently changing production scheduling or credentials.

## Source lineage

The retained File Library contains the complete historical v16 updater source and the later reviewed v17 repair/verification operators. Those v17 operators prove the accepted Hermes dashboard/partial-update hardening and removal of broad `docker image prune -a` behavior. The 2026-08-09 host recovery additionally changed the two intentionally loopback-only application probes and corrected the displayed updater banner to v17.

The exact 2026-08-09 live 47 KiB host file is not available to this repository as one byte-for-byte artifact. V21 must therefore be described and reviewed as a **successor derived from the recovered v16 source plus proven v17 patches and the incident fixes**, not falsely labeled a byte-identical import. Before any production installation, the candidate is diffed against the then-live host updater and unexpected runtime drift stops the migration rather than being overwritten.

## 2026-08-09 incident boundary

A scheduled cron trigger reached a path that had been removed by an earlier home-directory cleanup. Recovery of the retained updater then exposed two source/runtime drift defects: two application origins had intentionally become loopback-only while the updater still probed their previous LAN addresses, and the runtime banner still reported the previous script version. A bounded host-only repair corrected those two items and `--check` returned success. Those host edits are not yet an authoritative repository deployment.

The same dry-run exposed a reporting defect: Hermes could report that its Git checkout was behind `origin/main` while the final summary still rendered an unchanged semantic version as fully current.

The source audit exposed further stale/destructive assumptions that must be corrected during the successor import:

- backup-overlap detection still recognized legacy `backup.sh` process names, while the authoritative V10 backup uses `/usr/local/sbin/rpi5-backup` and `/run/lock/rpi5-backup.lock`;
- reboot package detection consumed the APT simulation package list even in `--check` mode, so an available kernel/firmware package could be described as already updated even though check mode performed no package installation;
- automatic `docker network prune` can delete old custom networks merely because no container references them at that moment;
- Compose `--remove-orphans` deletes project containers absent from the current definition, but the updater's image-tag rollback cannot recreate a removed orphan;
- the legacy Compose runtime gate inspects only containers that already exist and can therefore miss one completely absent service while other project containers remain healthy;
- Compose recreation is not explicitly marked `--no-build`, despite the preceding pull phase deliberately ignoring buildable services, so generic host maintenance does not have a strong boundary against an application image build;
- `--cleanup-only` reaches the normal minimum free-space/inode rejection gate before cleanup, which can make the recovery mode unavailable precisely when disk pressure is the reason it was requested.

## Audited behavior to preserve

The updater is deliberately conservative:

- run only as root and hold a non-blocking process lock;
- require a root-only maintenance configuration;
- validate free disk/inodes, Docker and both Compose projects before normal update/check mutation decisions;
- keep `--cleanup-only` usable under low-space pressure by separating cleanup eligibility from the normal update free-space threshold;
- prove every service defined by each targeted Compose project has a corresponding current container before mutation, then verify running/health state;
- refuse to overlap the host backup workflow using its authoritative lock rather than process-name guessing;
- perform APT metadata refresh and dpkg integrity checks before other updates;
- use a no-removal APT upgrade path for unattended weekly maintenance;
- simulate `full-upgrade` only to surface packages/removals that need manual review;
- never run autoremove automatically;
- keep APT-managed rclone under APT instead of mixing package managers;
- run Hermes in the configured unprivileged user context, with backup and post-update health gates;
- preserve tagged Docker rollback/release images during retention cleanup;
- prune bounded build cache and dangling images only, not networks/volumes/containers;
- snapshot Compose image identity before pulls and attempt bounded image rollback on failed recreation;
- recreate pulled-image services with `--pull never --no-build --wait`, keeping application builds/deployments outside generic host maintenance;
- treat intentionally loopback-only origins as loopback health checks;
- block automatic reboot after any failed update/health phase.

## Documentation-backed decisions

### APT

Debian's APT semantics distinguish conservative `upgrade` from `full-upgrade`: the latter may remove packages to complete dependency changes. V21 therefore keeps the weekly automatic path removal-free and keeps `full-upgrade` as a visibility/manual-review signal rather than silently broadening unattended mutation scope.

The package list generated by `--check` is simulation evidence only. Kernel/firmware names in that list must not be described as already updated and must not create a package-applied reboot reason. A current `/var/run/reboot-required` marker may still be reported in check mode because it describes existing host state rather than a simulated change.

The updater currently requests automatic `needrestart` service restart behavior for a non-interactive APT run. Debian documents automatic mode as automatically restarting affected daemons. V21 may preserve that behavior only together with post-update service health verification and must not confuse daemon restart with a host reboot requirement.

### Cleanup-only recovery mode

The normal run/check path requires a configured minimum free-space threshold and a minimum free-inode threshold before it proceeds. `--cleanup-only` has a different purpose: reclaiming bounded updater-owned space. It must still require successful filesystem inspection and must remain bounded to reviewed cleanup targets, but it does **not** require the normal minimum-free-space threshold before it may start. Otherwise the recovery command becomes unusable precisely when the host is already below the update threshold.

### Backup overlap

The encrypted V10 backup is the authoritative backup implementation and owns `/run/lock/rpi5-backup.lock`. The weekly updater must test that lock non-destructively before mutation. Matching process names is not an acceptable ownership boundary because executable names and paths can change while the lock contract remains stable. A lock-probe error must fail closed rather than be treated as an idle backup.

### Docker cleanup

Docker image pruning without `-a/--all` is required. The all-images mode may remove any image not referenced by a container, including retained rollback/release images. Build-cache pruning is a separate cache operation and may remove old unused cache because it is reproducible build acceleration rather than runtime identity. Volumes are never pruned by this updater.

Network pruning is removed from the unattended weekly path. Docker defines an unused network as one not referenced by any container; an intentionally pre-created/external network may be unused at the instant of maintenance yet still be required by a later service start. Network inventory/drift may be reported, but deletion requires a separate reviewed action.

### Docker Compose

Pulling and recreating are separate gates. `docker compose pull --ignore-buildable` downloads registry-backed service images without starting containers and deliberately ignores services whose images are built locally. The following recreation must therefore use `--pull never --no-build --wait`: it consumes only the image state established before that gate and cannot turn a generic host update into a source build/application deploy. Failed runtime health enters the explicit image-tag rollback path rather than silently accepting a partially healthy stack.

Before mutation, project completeness must be checked separately from per-container health: `docker compose config --services` is the expected service set and `docker compose ps --all --services` is the service set with current project containers. Any expected service missing from the latter is a preflight failure even if every remaining container is running/healthy. This prevents a partially missing project from being mistaken for a healthy baseline.

The unattended updater must not pass `--remove-orphans`. Docker documents that flag as removing containers for services absent from the current Compose definition. The existing rollback restores image tags for defined services; it does not reconstruct deleted orphan containers, so automatic orphan deletion violates the rollback boundary. Orphans may be reported and handled through a separate reviewed cleanup.

### Journald cleanup

`journalctl --rotate --vacuum-time=...` is compatible with the retention goal: rotation archives the current journal files and vacuuming removes archived files older than the configured window. This remains a bounded log-retention action rather than arbitrary log deletion.

### rclone

When the installed rclone binary is owned by dpkg and update mode is `auto`, V21 leaves it under APT ownership and does not mix in-place self-update with package-manager state. rclone's own documentation provides check/stable/package-selection controls for deliberately selected self-update mode; that branch remains explicit rather than the default for an APT-managed installation.

### Hermes

`hermes update --check` is a preview/freshness check, not the installation itself. The updater must represent three semantic states:

- `current` — check succeeded and no update-available signal was reported;
- `available` — the CLI reports a checkout behind/update available; this is informational/warning state, not a maintenance failure by itself;
- `error` — the check itself failed without an update-available signal.

The classifier deliberately recognizes both a nonzero-behind convention and the observed zero-exit-behind output. Checkout freshness must not be inferred only from the semantic version string or only from one CLI exit-code convention.

## Source-to-installed target

| Repository source | Installed target | Expected owner/mode |
|---|---|---|
| `ops/bin/rpi5-update` (successor source pending integration) | `/usr/local/sbin/rpi5-update` | `root:root`, `0750` |
| `ops/lib/rpi5-update-hermes-status.sh` | bundled/installed with updater implementation | root-controlled, not independently scheduled |
| `ops/lib/rpi5-update-locks.sh` | bundled/installed with updater implementation | root-controlled, not independently scheduled |
| `ops/lib/rpi5-update-reboot.sh` | bundled/installed with updater implementation | root-controlled, not independently scheduled |
| `ops/lib/rpi5-update-compose-health.sh` | bundled/installed with updater implementation | root-controlled, not independently scheduled |
| `ops/lib/rpi5-update-compose-policy.sh` | bundled/installed with updater implementation | root-controlled, not independently scheduled |
| `ops/lib/rpi5-update-space-policy.sh` | bundled/installed with updater implementation | root-controlled, not independently scheduled |

The current home-directory updater location is transitional only and must not remain the authoritative scheduler target after the systemd migration in #97.

## V21 repository gates

- Bash syntax for imported shell source and helper libraries;
- deterministic Hermes current/available/error classifier tests;
- deterministic backup-lock held/available/released tests;
- deterministic check-vs-run reboot-package semantics tests;
- deterministic Compose expected-vs-actual service completeness tests;
- deterministic unattended Compose argument-policy tests;
- deterministic run/check-vs-cleanup free-space policy tests;
- no `docker image prune -a/--all` in the imported updater;
- no unattended `docker network prune`;
- no unattended Compose `--remove-orphans`;
- require `--no-build` on unattended Compose recreation;
- loopback-only application-origin health policy regression;
- no credentials/private configuration in tracked source;
- source-to-installed mapping and rollback contract;
- normal repository `make validate` before PR readiness.

## Production boundary

Merge does not authorize host installation, package upgrades, Docker pulls/recreates, Hermes update, reboot, timer enablement or cron removal. Production apply is a later explicit transaction after #95-#98 have the required migration gates.
