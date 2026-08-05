# V09 encrypted backup ownership contract

## Purpose

V09 moves source ownership of the existing host-wide encrypted backup implementation from the Hermes Tech application repository to `RPi5_main`.

This is an ownership move, not a behavior change. The tracked files are byte-identical to the accepted Hermes Tech snapshot, and this repository performs no production deployment.

## Authoritative source lineage

Imported from:

- repository: `rozkalnsandris/hermes-tech`;
- source snapshot: `194083f0d850c888d23f751aeb51e69a561a047a`;
- original introduction commit: `36b8223710fd2dbe90b6d69898ffc17c34285da1`.

The machine-readable binding is `ops/backup/source-provenance.json`.

| Repository path | Source Git blob | SHA256 |
|---|---|---|
| `ops/bin/rpi5-backup` | `059ac81b6af5aebb56ebd92a03407a5c28847954` | `5ca85ae53bdf4fa3b99e21e1a30ddaa077d9e1791505b1e8389ee8587d011735` |
| `ops/backup/rpi5-backup.conf.example` | `7981cdd33c1be2b548fde61d0d47a6fd5ece58b8` | `65e4d465fc13c05c4a19842a4c6a5f4c3410bd5ac0ede1bffe79c54d359b2a8c` |
| `ops/cron.d/rpi5-backup` | `8dde57f1a8bcc8561a9fb27df318a7d9d8367f70` | `d9ef8658cb78ea85a3c7bb8e3853b03eab4c896399e58c35ef5b960df2a51697` |
| `ops/logrotate.d/rpi5-backup` | `7d1490e4c6f525f80e14490e7946da95ea0bbd1f` | `08e0b02be895592ffd1fd56ed6c5849cdc0e7b117c161e9382165ebcf05765e2` |

Git blob equality proves byte identity across the two repositories. SHA256 is independently calculated and enforced by CI.

## Source-to-installed mapping

| Repository source | Installed target | Repository mode | Expected installed ownership/mode |
|---|---|---:|---|
| `ops/bin/rpi5-backup` | `/usr/local/sbin/rpi5-backup` | `100755` | `root:root`, executable; verify before any write |
| `ops/backup/rpi5-backup.conf.example` | `/etc/rpi5-backup.conf` | `100644` | existing production mode remains authoritative until separately verified |
| `ops/cron.d/rpi5-backup` | `/etc/cron.d/rpi5-backup` | `100644` | `root:root`, regular file |
| `ops/logrotate.d/rpi5-backup` | `/etc/logrotate.d/rpi5-backup` | `100644` | `root:root`, regular file |

The tracked configuration is an example without secrets. Age private keys, recipients, rclone configuration, Telegram credentials, encrypted archives, logs, and runtime data remain outside Git.

## Preserved behavior

The transfer intentionally preserves:

- V12 script identity;
- root-only execution and non-blocking lock behavior;
- age X25519 encryption;
- local decrypt plus `tar -tzf` archive verification;
- SQLite online backup plus `PRAGMA quick_check`;
- Google Drive upload through rclone and remote-size verification;
- local retention of seven days and remote retention of thirty days;
- nightly cron execution at `02:00`;
- daily log rotation with fourteen rotations, compression, delayed compression, date suffixes, and `0600 root:root` log creation.

Changing any of these is outside V09 and requires a separate issue, tests, PR, migration plan, and production approval.

## Repository validation

Run:

```bash
make validate
```

`tests/test-backup-ownership.sh` fails on:

- source Git blob drift;
- SHA256 drift;
- repository mode drift;
- provenance manifest drift;
- missing or symlinked files;
- Bash syntax failure;
- cron schedule drift;
- logrotate contract drift;
- encryption, decrypt verification, upload, retention, SQLite snapshot, or integrity marker drift.

The normal repository secret guard also runs.

## Production verification gate

Repository merge does not authorize host access or deployment.

A separately approved verification must bind to the exact merged V09 commit and collect only bounded evidence:

1. Verify the repository commit and run `make validate` in a clean checkout.
2. Record SHA256, mode, owner, and group for the four installed targets without printing file contents.
3. Compare installed SHA256 values to the tracked manifest.
4. Confirm cron and logrotate files are regular root-owned files and not symlinks.
5. Run `bash -n` against a private copy of the installed script.
6. Run a debug-only logrotate parse against the installed configuration; do not rotate logs.
7. Record the cron service state and the installed schedule without reloading it.
8. Record only sanitized backup health metadata needed to show the existing job still behaves as before. Do not expose archive names, credentials, keys, configuration contents, or remote paths beyond the already tracked example.

If all installed hashes match, the correct ownership migration action is **no production write**. The installed backup remains untouched.

If any installed hash differs, stop. Treat it as unreviewed runtime drift. Do not overwrite the host merely to make it match Git.

## Future deployment procedure

A future deployment is allowed only through a separate explicit task after drift is understood.

Required controls:

1. exact source commit and expected SHA256 binding;
2. read-only preflight and clean repository validation;
3. private root-owned backups of every target being replaced;
4. atomic installation with explicit owner and mode;
5. syntax and debug-only configuration validation;
6. checksum verification after installation;
7. no backup execution, remote upload, retention deletion, cron reload, or log rotation unless separately approved;
8. documented rollback using the captured pre-change files;
9. post-rollback checksum and syntax verification.

## Hermes Tech removal gate

Hermes Tech may remove its duplicated host-wide files only after:

1. this `RPi5_main` PR has final pinned-checksum CI success;
2. this PR is squash-merged;
3. the exact merged commit is documented as the new source of truth;
4. a Hermes Tech PR removes only the duplicated host-wide implementation and keeps any application-specific backup expectations or links that remain useful;
5. both repositories retain normal Git history without rewriting it.

## Rollback

Before production apply, rollback is repository-only: revert the V09 ownership commit.

After a future approved host deployment, rollback restores the private pre-change copies to their original targets with their recorded owner and mode, then repeats checksum, syntax, cron, and logrotate verification. Runtime backups and secrets remain outside Git throughout.
