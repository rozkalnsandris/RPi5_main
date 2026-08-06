# V12 controlled RPi5 deploy contract

## Purpose

V12 adds a small operator interface for reviewed production deployment from
`RPi5_main`, while keeping a stricter safety boundary than an application
release. The visible workflow remains simple:

1. sync reviewed `main`;
2. run all repository tests;
3. generate and inspect a read-only deploy plan;
4. apply that exact short-lived plan with the printed commit confirmation;
5. verify status, or restore the exact recorded before-state.

A merge never deploys automatically. Merging V12 does not install the deploy
engine and does not write any managed production target.

## Root execution boundary

VS Code and the repository controller never execute user-writable repository
Python directly as `root`.

Normal-user commands run from the repository:

```bash
bash ./scripts/rpi5-deploy sync
bash ./scripts/rpi5-deploy test
```

After V12 is merged, or whenever one of the engine source files changes, the
operator performs one separately confirmed engine installation:

```bash
bash ./scripts/rpi5-deploy install-engine --confirm <12-character-main-commit>
bash ./scripts/rpi5-deploy engine-status
```

The installer requires clean, exact `main`, successful `make validate`, the
required successful GitHub `validate` check for the exact commit and the
expected RPi5 host identity before invoking any privileged install command.

It stages exact copies of the reviewed engine sources, verifies every staged
SHA-256 against the Git source, writes deterministic source metadata and then
installs a versioned, root-owned release below:

```text
/usr/local/libexec/rpi5-deploy/releases/<40-character-commit>/
```

The release files are `root:root`; the entry point is mode `0500`, imported
modules are mode `0400`, release metadata is mode `0400`, and the release
directory is mode `0700`. A new release is verified directly before the
root-owned `/usr/local/sbin/rpi5-deploy` wrapper is replaced. Previous releases
remain available for incident analysis or a separately reviewed engine-pointer
rollback.

The system wrapper is installed `root:root` mode `0700` and starts Python with
`env -i` plus a fixed minimal `PATH`. It therefore does not inherit test flags,
GitHub tokens, shell aliases, Python paths, Docker overrides or other caller
environment values. Git and GitHub checks run through `runuser` as the
non-root repository owner with that user's `HOME`.

Every root command verifies the installed release inventory, root ownership,
modes and SHA-256 values. Repository preflight also requires the current
tracked controller, engine modules and target manifest to match the source
hashes recorded when the engine was installed. A reviewed engine-source change
therefore fails closed until `install-engine` is run again from reviewed
`main`.

The normal repository controller routes only these commands to the installed
engine through `sudo`:

```bash
bash ./scripts/rpi5-deploy plan
bash ./scripts/rpi5-deploy deploy --confirm <12-character-planned-commit>
bash ./scripts/rpi5-deploy status
bash ./scripts/rpi5-deploy rollback --latest --confirm ROLLBACK
bash ./scripts/rpi5-deploy logs --lines 150
```

Running the repository controller itself with `sudo` is rejected.

## Initial managed scope

The target manifest is `ops/deploy/targets.json`. V12 manages exactly:

| Repository source | Production target | Owner | Mode | Validation |
|---|---|---:|---:|---|
| `ops/bin/rpi5-backup` | `/usr/local/sbin/rpi5-backup` | `root:root` | `0700` | `bash -n` |
| `ops/cron.d/rpi5-backup` | `/etc/cron.d/rpi5-backup` | `root:root` | `0644` | exact nightly cron contract |
| `ops/logrotate.d/rpi5-backup` | `/etc/logrotate.d/rpi5-backup` | `root:root` | `0644` | debug-only `logrotate -d` |

The engine independently hard-codes the complete approved tuple for every
entry: ID, source, production target, owner, group, mode and validators. A
manifest that preserves an approved ID but changes any other field is rejected
before engine installation, plan creation, deploy or status. The manifest is a
reviewed declaration, not authority to select arbitrary root paths.

`ops/backup/rpi5-backup.conf.example` is deliberately **reference-only**.
The real `/etc/rpi5-backup.conf` may contain private host configuration and
must never be replaced by the example.

Docker Compose, systemd units, Cloudflare, Home Assistant, monitoring, update
scripts and application repositories are not deploy targets in V12. Each must
first be imported and reviewed under its own source/installed mapping,
validation and rollback contract.

## VS Code tasks

The tracked `.vscode/tasks.json` exposes:

- `RPi5: Sync from GitHub`;
- `RPi5: Test`;
- `RPi5: Install deploy engine`;
- `RPi5: Deploy engine status`;
- `RPi5: Deploy plan`;
- `RPi5: Deploy reviewed plan`;
- `RPi5: Status`;
- `RPi5: Rollback latest`;
- `RPi5: Deploy logs`.

Engine installation is normally needed only once after V12 merge and again
when one of the five engine-source files changes. Plan and deploy are separate
tasks on purpose: the operator must inspect every before/desired fingerprint
before entering the commit confirmation.

## Repository and CI preflight

A production plan fails unless all of the following hold:

- the credential-free remote is exactly the approved GitHub repository;
- the checked-out branch is `main`;
- stable Git porcelain reports no tracked or untracked change;
- a fresh fetch succeeds and local `HEAD` equals `origin/main`;
- installed engine source hashes equal current tracked source hashes;
- the complete manifest equals the hard-coded approved V12 target contract;
- `make validate` succeeds as the non-root repository owner;
- GitHub CLI returns check runs for the exact commit;
- every latest returned exact-commit check run is completed with conclusion `success`;
- the required check name `validate` is present and successful.

A different successful check cannot substitute for the repository validation
job. The root-owned plan is written only after the required check-name gate has
passed.

A raw remote URL is never written into a plan or log. The stored projection is
the fixed repository identity only, so credentials accidentally embedded in a
remote cannot leak into deployment evidence.

## Host preflight

The read-only plan and deploy preflight require:

- hostname `rpi5`, Raspberry Pi 5 model, Debian 12 and arm64/aarch64;
- a read-write root filesystem;
- at least 2 GiB free and at least 5% free inodes;
- at least 256 MiB `MemAvailable`;
- bounded one-minute load and CPU temperature below 80 °C when exposed;
- `vcgencmd get_throttled` equal to `throttled=0x0` when available;
- no concurrent backup, update, APT/dpkg, unattended-upgrade or deploy lock;
- no failed systemd units and active `cron.service`;
- a sanitized successful encrypted-backup marker no older than 36 hours;
- every running container in the reviewed runtime baseline still present;
- every baseline container expected healthy still reported healthy.

The backup gate reads only a timestamp from the most recent bounded portion of
the backup log. It does not print archive names, remote paths, keys, tokens or
configuration contents.

The tracked runtime baseline is intentionally strict. A legitimate runtime
change must be collected, reviewed and promoted first instead of teaching the
deploy command to ignore drift.

## Plan binding

`plan` writes root-only state to:

```text
/var/lib/rpi5-deploy/plans/latest.json
```

The plan includes:

- exact full and 12-character source commit;
- installed engine/source binding;
- manifest SHA-256;
- repository, CI and sanitized host preflight results;
- source SHA-256 for every target;
- exact live before fingerprint: presence, SHA-256, UID, GID and mode;
- exact desired fingerprint: SHA-256, UID, GID and mode;
- `replace` or `unchanged` action;
- creation and expiry times.

The default lifetime is 30 minutes. `deploy` refuses an expired plan, a changed
manifest or source, a different commit, unsafe/symlinked target parents, or any
target whose complete live fingerprint no longer equals the reviewed
before-state. Every source is required to be a single regular non-symlink file;
this applies to status reporting as well as planning and deployment.

A file with matching content but wrong UID, GID or mode is `DRIFT`, not
`MATCH`, and is planned for correction.

## Apply transaction

After all gates pass, deploy creates a root-only transaction below:

```text
/var/lib/rpi5-deploy/transactions/<UTC>-<short-commit>/
```

Immediately before processing each row, including `unchanged` rows, the engine
rechecks that the source SHA and full live fingerprint still equal the reviewed
plan. For every changed target it then:

1. verifies all target parent components are real directories, not symlinks;
2. copies the old regular file into a private `0600` transaction backup;
3. fsyncs and verifies that backup against the reviewed before SHA-256;
4. records the prepared phase in transaction metadata;
5. copies the source to a temporary file in the target directory;
6. applies explicit owner, group and mode;
7. fsyncs and validates the temporary file;
8. replaces the target with same-directory `os.replace()` and fsyncs the directory;
9. verifies the complete desired fingerprint and validators again;
10. records the installed phase before moving to the next target.

After all rows are processed, every source and desired live fingerprint is
verified before and again after the final host preflight. Successful transaction
metadata and the `latest-success` pointer are written with fsync; the pointer is
replaced atomically.

V12 does not execute a backup, upload data, delete retention data, rotate logs,
reload cron, restart services or restart containers. The three initial targets
do not require a service restart.

## Automatic rollback

Any exception after a target enters the mutation set starts automatic rollback
in reverse order. The rollback-start audit log is best-effort and cannot block
the actual restoration. The old file is restored atomically, or a target that
was previously absent is removed. Every restored SHA-256, UID, GID and mode must
exactly equal the reviewed before-state. Transaction metadata records prepared,
installed, restored or restore-failed phases.

If failure occurs after a `latest-success` pointer was created, automatic
rollback removes that pointer when it still refers to the failing transaction.
A fully restored failure is marked `rolled_back`. An incomplete restore or
pointer cleanup is marked `rollback_failed` and reported clearly.

## Manual rollback

Only the latest successful transaction can be rolled back in V12. Before the
first live write, the command:

1. requires every changed target's complete current fingerprint to equal the
   recorded post-deploy fingerprint;
2. verifies every private before-state backup's type, mode, ownership and
   SHA-256;
3. creates and verifies a private `0600` post-state compensation snapshot for
   every changed target.

It therefore refuses to overwrite later content, ownership, group or mode
changes, and it cannot begin restoration with a corrupt transaction backup.
Targets are restored in reverse order. If a later restore or final verification
fails, every already restored target is atomically returned to its recorded
deployed state from the compensation snapshots and `latest-success` is
re-established. A completely compensated attempt remains an active successful
transaction with `rollback_attempt_status=compensated`; incomplete compensation
is marked `rollback_failed` and reported as an incident.

Rollback is deliberately not blocked by an unhealthy container or failed
systemd unit, because that may be the reason rollback is needed. It still
requires the verified installed engine, exact RPi5/Debian/architecture identity,
a read-write root filesystem, an exclusive deploy lock and no conflicting
maintenance process. After restoration, the full host preflight runs. If
runtime health still fails, the command reports that files were restored but
the wider incident remains.

## Logs and secret boundary

The deploy log is root-only at `/var/log/rpi5-deploy.log`; concise markers are
also sent to journald with tag `rpi5-deploy`. Logs contain command phase,
transaction ID, short commit and bounded sanitized errors. Command failures do
not copy arbitrary subprocess output into the root log. Logs do not contain
file contents, environment values, raw remote URLs, tokens, keys, backup names
or raw configuration.

## Testing

`tests/test-controlled-deploy.sh` runs without root, Docker or systemd changes.
It builds a temporary Git repository and fake root, then verifies:

- exact manifest scope and reference-only configuration guard;
- test mode cannot target `/` or escape its temporary sandbox;
- deterministic engine staging, source/installed SHA binding and `env -i` wrapper;
- repository root commands route to the system engine;
- no production preflight-bypass environment variable exists;
- plan creation and exact-SHA confirmation;
- complete before and desired fingerprints;
- rejection of a wrong confirmation;
- synthetic failure after a partial write and verified automatic rollback;
- durable rollback phase metadata;
- successful atomic deployment and status reporting;
- refusal to roll back over metadata-only drift;
- verified manual rollback to exact before fingerprints.

`tests/test-controlled-deploy-rollback.py` adds focused transaction-hardening
regressions for:

- rejection of an ID-preserving manifest target-path change;
- rejection of a repository source symlink during status;
- failure after `latest-success` creation, full automatic restoration and stale
  pointer cleanup;
- refusal of a corrupt before-state backup before any manual-rollback write;
- synthetic mid-rollback failure, deployed-state compensation and pointer
  preservation;
- a later successful exact rollback to the original bytes and modes.

Run all repository checks with:

```bash
make validate
```

The tests do not install `/usr/local/sbin/rpi5-deploy`, touch production state,
run the real backup, reload cron or restart any service.

## Research decision: manifest transaction before Ansible

Ansible check and diff modes are useful for later, larger subsystem imports.
However, check mode is a simulation, unsupported modules may report nothing,
and diff output can reveal sensitive information. V12 therefore starts with a
small manifest-driven transaction and no new production automation dependency.
When broader configuration is imported, Ansible can be placed inside this same
outer engine/commit/CI/plan/rollback contract, with diff disabled for private
configuration tasks.

Future Docker Compose targets must at minimum use Compose configuration
validation and an available dry-run before apply. They are intentionally not
part of the initial three-file transaction.

## Rollback before production use

Before any separately approved engine installation or target apply, repository
rollback is simply reverting the V12 commit. After engine installation, the
versioned old engine release remains present; changing the system wrapper back
to it requires a separate reviewed engine-pointer procedure. After a target
apply, use the guarded transaction rollback and retain its metadata for
incident review.
