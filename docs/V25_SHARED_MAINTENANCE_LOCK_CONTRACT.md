# V25 shared RPi5 maintenance lock contract

## Status

Repository-only implementation for issue #100. Production unchanged.

V25 builds directly on the merged V24 cleanup-ownership baseline and closes the remaining race between the encrypted backup workflow and the weekly updater. V21 could only probe the backup-private lock before mutation; a backup started after that probe could overlap APT, Hermes, Docker or cleanup mutation.

V25 introduces one cross-job exclusive lock:

`/run/lock/rpi5-maintenance-exclusive.lock`

Real updater runs, cleanup-only runs and canonical backup runs hold this lock throughout their mutation-sensitive lifetime. Updater `--check` remains non-mutating and intentionally does not take the shared lock.

## Lock responsibilities

The duplicate-run locks remain separate:

- updater duplicate lock: `/run/lock/rpi5-update.lock`;
- backup duplicate lock: `/run/lock/rpi5-backup.lock`;
- cross-job exclusivity: `/run/lock/rpi5-maintenance-exclusive.lock`.

Private locks answer whether another copy of the same job is already running. The shared lock answers whether another mutation-sensitive maintenance job is running.

## Explicit contention status

`ops/lib/rpi5-maintenance-locks.sh` reserves:

`RPI5_LOCK_CONFLICT_RC=200`

Every bounded or non-blocking `flock` call sets `--conflict-exit-code 200`. Therefore:

- `0` means acquired;
- `200` means lock contention / timeout only;
- `2` is used by the helper for invalid arguments or lock-file setup failure before `flock`;
- any other nonzero `flock` status is propagated as a genuine lock error and must not be logged as contention.

This separation is deliberate. util-linux `flock` documents a caller-selected conflict exit code while other errors use separate `sysexits` statuses. Using an application-reserved code outside that range prevents a real `flock` failure from being mislabeled as a busy lock.

Updater and backup wrapper may translate the internal contention result into their existing external temporary-failure policy only **after** checking specifically for `RPI5_LOCK_CONFLICT_RC`. Migration quiescence uses the explicit code to distinguish a busy host from a broken lock operation.

## Updater order and lifetime

The V25 updater keeps its own duplicate updater lock first:

`updater-private → shared maintenance`

For `run` and `cleanup` modes it then acquires the shared maintenance lock with bounded `MAINTENANCE_LOCK_TIMEOUT`. The returned file descriptor remains open until updater process exit, covering retention cleanup, APT, Hermes, Docker recreation/rollback, health checks and reboot scheduling decisions.

The previous backup-private probe/wait path is removed. `BACKUP_WAIT_TIMEOUT` is accepted only as a backwards-compatible configuration fallback for `MAINTENANCE_LOCK_TIMEOUT`; new configuration should use the new name.

`--check` does not acquire the shared lock.

## Backup artifact identity: V10 ownership snapshot, runtime V12

The immutable backup artifact has two different historical labels that must not be conflated:

- **V10 ownership snapshot** — the repository import/ownership milestone used by the RPi5 infrastructure project;
- **runtime backup version 12** — the byte-identical backup script itself starts with `RPi5 šifrētais backup runneris V12`.

The authoritative identity is neither label. It is the SHA256 of `ops/bin/rpi5-backup`:

`5ca85ae53bdf4fa3b99e21e1a30ddaa077d9e1791505b1e8389ee8587d011735`

V25 never rewrites that file. All core installation, verification, rollback and saved-copy checks use this SHA. The installed internal path retains the historical name `rpi5-backup-v10-core` for continuity, but documentation and logs describe it as the **V10 ownership snapshot / runtime V12 core**.

## Backup order and lifetime

`ops/bin/rpi5-backup-serialized` becomes the future canonical backup wrapper. It validates the root-controlled lock helper and exact immutable backup core, then executes this order:

`shared maintenance → exact backup core → backup-private`

The wrapper acquires the shared lock first and deliberately does **not** `exec` the core. Keeping the wrapper alive retains the shared-lock FD while the exact core runs. The core then acquires its unchanged `/run/lock/rpi5-backup.lock` duplicate-run lock.

The wrapper returns the core exit status unchanged. Encryption, snapshot, integrity, upload, retention and existing notification behavior remain inside the immutable core.

## Deadlock model

Canonical updater and backup paths are:

- updater: updater-private → shared;
- backup: shared → backup-private (inside the immutable core).

There is no cycle: updater never waits for backup-private and backup never waits for updater-private.

The migration operator acquires updater-private, backup-private and shared locks only with non-blocking `flock` semantics. It never waits while holding part of a migration lock set. Any contention returns the reserved conflict code immediately; genuine `flock` errors retain their distinct status.

## FHS ownership

Administrator entrypoints remain under `/usr/local/sbin`.

Internal maintenance code and the immutable backup core are installed under the canonical FHS hierarchy:

`/usr/local/lib/rpi5-maintenance`

The former `/usr/local/libexec/rpi5-maintenance` path is forbidden by V21–V25 regressions and is not reintroduced by V25.

## Canonical backup migration

`ops/bin/rpi5-maintenance-lock-cutover` owns the separately approved production transition.

### `--check`

Read-only preflight verifies:

- repository backup SHA equals the immutable ownership snapshot SHA;
- repository backup runtime marker still identifies V12;
- installed updater equals the current V25 provenance candidate;
- if migration is inactive, canonical `/usr/local/sbin/rpi5-backup` equals the immutable snapshot;
- if migration is active, canonical backup equals the reviewed wrapper and the internal core still equals the immutable snapshot.

### `--install`

Before replacement it verifies updater/core identity and obtains a fail-fast quiescent window over updater-private, backup-private and shared locks. Each lock call uses the explicit conflict code; contention and real lock errors are reported differently.

Then it:

1. saves the exact current canonical backup in root-only migration state;
2. verifies the saved copy by SHA;
3. installs the exact immutable core under `/usr/local/lib/rpi5-maintenance`;
4. installs the shared-lock helper there;
5. stages and SHA-verifies the serialized wrapper;
6. atomically moves the wrapper onto `/usr/local/sbin/rpi5-backup`;
7. verifies wrapper/core/helper state;
8. writes a root-only active marker.

Failed post-replacement verification immediately restores the saved immutable snapshot.

### `--verify`

Requires current V25 updater provenance, reviewed wrapper identity, exact immutable internal core and exact saved rollback copy.

### `--rollback`

Requires a fresh fail-fast quiescent window, atomically restores the saved immutable snapshot at the canonical backup path, verifies the SHA, then removes the active marker.

Neither install nor verify runs a real backup or updater merely as a test.

## Actual entrypoint lock-order regression

V25 tests no longer use the old simplified model that incorrectly represented both jobs as private-lock-first.

The regression binds to the actual repository entrypoints:

- `ops/bin/rpi5-update` must acquire updater-private before shared and must not reference backup-private;
- `ops/bin/rpi5-backup-serialized` must acquire shared before invoking `rpi5-backup-v10-core`;
- immutable `ops/bin/rpi5-backup` must acquire backup-private inside the core;
- runtime concurrency scenarios reproduce those exact two entrypoint orders and prove that either job can start first without overlap or deadlock.

## Installation ordering with V23/V24 systemd cutover

The reviewed V23/V24 systemd installer remains intentionally unchanged in V25. Its `--install` phase may install the V25 updater binary, but it does not activate timers or retire legacy cron.

The V25 lock-cutover transaction owns installation and verification of `rpi5-maintenance-locks.sh` together with the serialized backup path. Therefore #123 must preserve this order inside one guarded maintenance window:

1. run the existing systemd `--install` phase while legacy cron is still authoritative and new timers remain inactive;
2. immediately run V25 lock-cutover `--install` and `--verify`, which installs the shared helper and serializes the canonical backup path;
3. verify the V25 updater, wrapper, immutable core and shared helper as one set;
4. only then allow scheduler `--activate --allow-persistent-catchup`.

The temporary interval after systemd `--install` does not change the active scheduler: legacy cron still points to the reviewed home-directory v17 updater, while `/usr/local/sbin/rpi5-update` is not yet scheduled. The transaction must not be paused or declared complete until V25 lock-cutover verification passes.

## Production ordering

Shared serialization becomes effective only when both sides use the shared lock. The production transaction therefore treats these as one guarded window:

1. install reviewed V25 updater without activating it;
2. install/verify the shared-lock helper and migrate canonical backup to the serialized wrapper under the fail-fast quiescent window;
3. verify exact updater/wrapper/core/helper identities;
4. only then retire legacy cron and activate the reviewed systemd scheduler.

Leaving the host indefinitely half-migrated is not an accepted state.

## Repository gates

- immutable backup SHA remains unchanged and runtime V12 marker is asserted;
- shared lock acquire/timeout/release/nonblock tests use conflict code 200;
- a genuine `flock` error cannot be classified as contention;
- actual updater/wrapper/core lock acquisition order is structurally asserted;
- runtime concurrency tests reproduce the actual two entrypoint orders;
- updater run/cleanup takes shared lock while check skips it;
- updater backup-private probe is forbidden;
- wrapper holds shared lock around immutable core;
- migration quiescent lock acquisition is non-blocking and distinguishes conflict from error;
- atomic canonical-path replacement and exact-SHA rollback are tested;
- lock-cutover installs/verifies the shared-lock helper before scheduler activation is permitted;
- FHS `/usr/local/lib/rpi5-maintenance` boundary remains mandatory;
- V24 cleanup ownership regressions remain green;
- exact updater provenance, public-safety and full-history secret scans remain mandatory.

## Production boundary

Merge does not authorize installing V25, replacing `/usr/local/sbin/rpi5-backup`, moving the immutable backup core, taking production maintenance locks, running backup/update/cleanup, changing timers/cron, sending Telegram messages or rebooting the host. Production migration remains the later explicit #123 transaction with live preflight, rollback evidence and separate user approval.
