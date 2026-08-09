# V21 weekly maintenance updater ownership contract

## Status

**Reviewed successor source imported, public-safe, and provenance-bound. Production unchanged.**

This phase moves the existing RPi5 weekly maintenance updater out of the interactive user's home directory and into reviewed host-infrastructure ownership. The repository source is now `ops/bin/rpi5-update`; the intended installed target is `/usr/local/sbin/rpi5-update`. Private runtime configuration remains outside Git.

Issue #95 owns the updater source import. Issues #96-#98 separately own monitor/post-reboot privilege repair, systemd scheduling, and cleanup-path regression protection. Issue #100 separately owns full backup/update mutual exclusion with a shared maintenance lock. This split prevents a source-ownership change from silently changing production scheduling, credentials, backup behavior, or cleanup ownership.

## Source lineage

The retained File Library contains the complete historical v16 updater source and the later reviewed v17 repair/verification operators. Those v17 operators prove the accepted Hermes dashboard/partial-update hardening and removal of broad `docker image prune -a` behavior. The 2026-08-09 host recovery additionally changed the two intentionally loopback-only application probes and corrected the displayed updater banner to v17.

The exact live file from the 2026-08-09 host incident is now available as review evidence and is SHA256-bound in `ops/maintenance/updater-source-provenance.json`:

- live v17 incident-fixed baseline: `bd0afe74dea18742a002c852d59fc67ec848a032116d2adc314c24848895e24c`, 47,190 bytes;
- reviewed public-safe V21 successor: `860b2dd0be0d7f32f2648742a356bccabb20f0c9f8e7073ba2b1c998aa212851`, 50,076 bytes;
- reviewed V21 Git blob: `67cd5b443dfdb8a48fd08aaa4015dc0f6b26e9ec`.

V21 is intentionally a **reviewed successor derived from the exact live baseline**, not a byte-identical import: the purpose of #95 is to preserve the known-good updater behavior while correcting the audited safety and ownership defects. Before any production installation, the then-live updater must still match the expected live baseline or an explicitly reviewed later baseline; unexpected runtime drift stops migration rather than being overwritten.

Because `RPi5_main` is public, concrete user-home paths and RFC1918 addresses are not tracked in the executable source. Compose/Hermes paths are derived from the configured maintenance user's runtime home, while `HOST_IPV4` is supplied by root-only `/etc/rpi-update.conf`. This keeps host-specific values outside Git without weakening the runtime validation boundary.

## 2026-08-09 incident boundary

A scheduled cron trigger reached a path that had been removed by an earlier home-directory cleanup. Recovery of the retained updater then exposed two source/runtime drift defects: two application origins had intentionally become loopback-only while the updater still probed their previous LAN addresses, and the runtime banner still reported the previous script version. A bounded host-only repair corrected those two items and `--check` returned success. The exact repaired live file is the SHA-bound V21 derivation baseline described above.

The same dry-run exposed a reporting defect: Hermes could report that its Git checkout was behind `origin/main` while the final summary still rendered an unchanged semantic version as fully current.

The full source audit exposed further stale/destructive assumptions. The imported V21 source corrects these #95-owned defects:

- backup-overlap detection no longer recognizes legacy process names; mutation modes use the authoritative V10 backup lock with a bounded wait;
- reboot package detection no longer treats `--check` APT simulation candidates as packages that were actually installed;
- unattended `docker network prune` is removed;
- Compose `--remove-orphans` is removed from normal recreation and rollback;
- Compose preflight compares the configured service set with services that actually have project containers before per-container health inspection;
- Compose recreation is explicitly `--no-build`, preserving the boundary between host maintenance and application builds/deploys;
- `--cleanup-only` is not rejected merely because the host is already below the normal free-space/inode update threshold;
- HTTP retry capture preserves a single normalized three-digit status code even when `curl` itself fails;
- Telegram credentials are not copied into a child process environment;
- concrete user-home paths and private-LAN addresses are removed from the tracked executable and remain runtime configuration/derivation only.

Broad home-directory cleanup ownership is intentionally not expanded inside #95; that remains #98. Full backup-vs-update mutual exclusion is intentionally not hidden inside #95; that remains #100 because it requires a coordinated change to the already-owned V10 backup implementation.

## Audited behavior to preserve

The updater is deliberately conservative:

- run only as root and hold a non-blocking duplicate-update process lock;
- require a root-only maintenance configuration;
- keep host-specific private values outside the public repository;
- load helper/notifier code only from the root-controlled `/usr/local/libexec/rpi5-maintenance` installation boundary and reject unsafe ownership/writability;
- validate free disk/inodes, Docker and both Compose projects before normal update/check mutation decisions;
- keep `--cleanup-only` usable under low-space pressure by separating cleanup eligibility from the normal update free-space threshold;
- prove every service defined by each targeted Compose project has a corresponding current container before mutation, then verify running/health state;
- wait a bounded time for the authoritative backup lock before mutation instead of guessing process names;
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
- treat intentionally loopback-only application origins as loopback health checks;
- keep Telegram delivery failure secondary to the authoritative maintenance result;
- block automatic reboot after any failed update/health phase.

## Documentation-backed decisions

### APT

Debian's APT semantics distinguish conservative `upgrade` from `full-upgrade`: the latter may remove packages to complete dependency changes. V21 therefore keeps the weekly automatic path removal-free and keeps `full-upgrade` as a visibility/manual-review signal rather than silently broadening unattended mutation scope.

The package list generated by `--check` is simulation evidence only. Kernel/firmware names in that list must not be described as already updated and must not create a package-applied reboot reason. A current `/var/run/reboot-required` marker may still be reported in check mode because it describes existing host state rather than a simulated change.

The updater requests automatic `needrestart` service restart behavior for a non-interactive APT run. Debian documents automatic mode as automatically restarting affected daemons. V21 preserves that behavior together with post-update service health verification and does not confuse daemon restart with a host reboot requirement.

### Cleanup-only recovery mode

The normal run/check path requires a configured minimum free-space threshold and a minimum free-inode threshold before it proceeds. `--cleanup-only` has a different purpose: reclaiming bounded updater-owned space. It must still require successful filesystem inspection and must remain bounded to reviewed cleanup targets, but it does **not** require the normal minimum-free-space threshold before it may start. Otherwise the recovery command becomes unusable precisely when the host is already below the update threshold.

The existing historical home wildcard cleanup rules remain visible in the successor for continuity but are separately owned by #98. Production cleanup-path retirement must not infer that unrelated recovery/deploy evidence is disposable merely because it has an `rpi5-*` name.

### Backup overlap

The encrypted V10 backup is the authoritative backup implementation and owns `/run/lock/rpi5-backup.lock`. V21 waits for that lock with a configurable bounded timeout before mutating APT/Hermes/Docker state. Matching process names is not an acceptable ownership boundary because executable names and paths can change while the lock contract remains stable. A timeout or lock setup error fails closed.

Waiting for the backup-specific lock does not by itself create full mutual exclusion after the wait is released: a manually started backup could otherwise begin during an updater mutation window. Issue #100 owns the coordinated shared-maintenance-lock change across both backup and update, including canonical acquisition order and deadlock tests. That coordinated behavior is intentionally not smuggled into #95.

### Docker cleanup

Docker image pruning without `-a/--all` is required. The all-images mode may remove any image not referenced by a container, including retained rollback/release images. Build-cache pruning is a separate cache operation and may remove old unused cache because it is reproducible build acceleration rather than runtime identity. Volumes are never pruned by this updater.

Network pruning is removed from the unattended weekly path. Docker defines an unused network as one not referenced by any container; an intentionally pre-created/external network may be unused at the instant of maintenance yet still be required by a later service start. Network inventory/drift may be reported, but deletion requires a separate reviewed action.

### Docker Compose

Pulling and recreating are separate gates. `docker compose pull --ignore-buildable` downloads registry-backed service images without starting containers and deliberately ignores services whose images are built locally. The following recreation therefore uses `--pull never --no-build --wait`: it consumes only the image state established before that gate and cannot turn a generic host update into a source build/application deploy. Failed runtime health enters the explicit image-tag rollback path rather than silently accepting a partially healthy stack.

Before mutation, project completeness is checked separately from per-container health: `docker compose config --services` is the expected service set and `docker compose ps --all --services` is the service set with current project containers. Any expected service missing from the latter is a preflight failure even if every remaining container is running/healthy. This prevents a partially missing project from being mistaken for a healthy baseline.

The unattended updater does not pass `--remove-orphans`. Docker documents that flag as removing containers for services absent from the current Compose definition. The existing rollback restores image tags for defined services; it does not reconstruct deleted orphan containers, so automatic orphan deletion violates the rollback boundary. Orphans may be reported and handled through a separate reviewed cleanup.

### HTTP health

The live v16b repair established two important semantics that V21 preserves in a dedicated helper: retry diagnostics go to stderr so command substitution captures only the status code, and exhausted retries are handled inside explicit conditionals so `set -e` cannot abort the updater before health state is recorded. V21 additionally normalizes a transport failure to exactly one `000` code even when `curl -w` already emitted `000` before returning a nonzero transport status.

### Telegram

Runtime Telegram credentials remain in root-only configuration outside Git. V21 no longer copies the token/chat ID into a child Python environment; the notifier receives the three values through a short-lived NUL-delimited stdin channel. Notification failure remains warning-only and cannot erase the original maintenance result.

### Public repository boundary

The executable source contains no concrete user-home path and no RFC1918 IPv4 address. The source validator independently rejects those classes in addition to the repository-wide public-safety guard. Runtime Compose and Hermes paths are derived from `UPDATE_HOME` unless explicitly supplied by root-only configuration; `HOST_IPV4` is required from that private configuration before health checks proceed.

### Journald cleanup

`journalctl --rotate --vacuum-time=...` is compatible with the retention goal: rotation archives the current journal files and vacuuming removes archived files older than the configured window. This remains a bounded log-retention action rather than arbitrary log deletion.

### rclone

When the installed rclone binary is owned by dpkg and update mode is `auto`, V21 leaves it under APT ownership and does not mix in-place self-update with package-manager state. rclone's own documentation provides check/stable/package-selection controls for deliberately selected self-update mode; that branch remains explicit rather than the default for an APT-managed installation.

### Hermes

`hermes update --check` is a preview/freshness check, not the installation itself. The updater represents three semantic states:

- `current` — check succeeded and no update-available signal was reported;
- `available` — the CLI reports a checkout behind/update available; this is informational/warning state, not a maintenance failure by itself;
- `error` — the check itself failed without an update-available signal.

The classifier deliberately recognizes both a nonzero-behind convention and the observed zero-exit-behind output. Checkout freshness is not inferred only from the semantic version string or only from one CLI exit-code convention.

## Source-to-installed target

| Repository source | Installed target | Expected owner/mode |
|---|---|---|
| `ops/bin/rpi5-update` | `/usr/local/sbin/rpi5-update` | `root:root`, `0750` |
| `ops/lib/rpi5-update-hermes-status.sh` | `/usr/local/libexec/rpi5-maintenance/rpi5-update-hermes-status.sh` | `root:root`, not group/world writable |
| `ops/lib/rpi5-update-locks.sh` | `/usr/local/libexec/rpi5-maintenance/rpi5-update-locks.sh` | `root:root`, not group/world writable |
| `ops/lib/rpi5-update-reboot.sh` | `/usr/local/libexec/rpi5-maintenance/rpi5-update-reboot.sh` | `root:root`, not group/world writable |
| `ops/lib/rpi5-update-compose-health.sh` | `/usr/local/libexec/rpi5-maintenance/rpi5-update-compose-health.sh` | `root:root`, not group/world writable |
| `ops/lib/rpi5-update-compose-policy.sh` | `/usr/local/libexec/rpi5-maintenance/rpi5-update-compose-policy.sh` | `root:root`, not group/world writable |
| `ops/lib/rpi5-update-space-policy.sh` | `/usr/local/libexec/rpi5-maintenance/rpi5-update-space-policy.sh` | `root:root`, not group/world writable |
| `ops/lib/rpi5-update-origin-policy.sh` | `/usr/local/libexec/rpi5-maintenance/rpi5-update-origin-policy.sh` | `root:root`, not group/world writable |
| `ops/lib/rpi5-update-http-health.sh` | `/usr/local/libexec/rpi5-maintenance/rpi5-update-http-health.sh` | `root:root`, not group/world writable |
| `ops/lib/rpi5-update-telegram.py` | `/usr/local/libexec/rpi5-maintenance/rpi5-update-telegram.py` | `root:root`, not group/world writable |

The current home-directory updater location is transitional only and must not remain the authoritative scheduler target after the systemd migration in #97.

## V21 repository gates

- exact live v17 baseline SHA256/size recorded in provenance;
- exact imported public-safe V21 source SHA256, Git blob identity, size and executable Git mode recorded/tested;
- Bash syntax for imported shell source and helper libraries;
- deterministic Hermes current/available/error classifier tests;
- deterministic backup-lock held/available/released/bounded-wait tests;
- deterministic check-vs-run reboot-package semantics tests;
- deterministic Compose expected-vs-actual service completeness tests;
- deterministic unattended Compose argument-policy tests;
- deterministic run/check-vs-cleanup free-space policy tests;
- deterministic HTTP retry/capture/transport-failure normalization tests;
- deterministic Telegram chunking/error-redaction tests;
- no concrete user-home path or RFC1918 IPv4 address in tracked updater source;
- no `docker image prune -a/--all` in the imported updater;
- no unattended `docker network prune` or obsolete network-prune capability gate;
- no unattended Compose `--remove-orphans`;
- require reviewed helper routing for `--pull never --no-build --wait` recreation and rollback;
- loopback-only application-origin health policy regression;
- no credentials/private configuration in tracked source;
- no temporary source-assembly workflow/staging files after import;
- normal repository `make validate` and pinned full-history secret scan before PR readiness.

## Production boundary

Merge does not authorize host installation, package upgrades, Docker pulls/recreates, Hermes update, reboot, timer enablement, cron removal, backup behavior changes, or credential changes. Production apply is a later explicit transaction after the required migration gates have been reviewed. Systemd scheduling remains #97, cleanup ownership remains #98, and full backup/update mutual exclusion remains #100.
