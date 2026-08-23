# V12 controlled RPi5 deploy contract

## Purpose

V12 adds a small operator interface for reviewed production deployment from
`RPi5_main`, while keeping a stricter safety boundary than an application
release. The visible workflow remains simple:

1. sync reviewed `main`;
2. run all repository tests;
3. generate and inspect a deploy plan;
4. apply that exact short-lived plan with the printed commit confirmation;
5. verify status, or restore the exact recorded before-state.

A merge never deploys automatically. Merging V12 does not install the deploy
engine and does not write any managed production target.

The controller lineage remains V12, but its reviewed target contract follows
the current production maintenance topology. Production was migrated to the V25
shared-lock backup architecture, so the generic controller must never replace
the canonical V25 wrapper with the older immutable backup core.

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

## Current managed and attested scope

The target manifest is `ops/deploy/targets.json`. The current contract contains
exactly five production files:

| ID | Repository source | Production target | Owner | Mode | Validation | Policy |
|---|---|---|---:|---:|---|---|
| `backup-runner` | `ops/bin/rpi5-backup-serialized` | `/usr/local/sbin/rpi5-backup` | `root:root` | `0750` | `bash -n` | **attestation-only** |
| `backup-core` | `ops/bin/rpi5-backup` | `/usr/local/lib/rpi5-maintenance/rpi5-backup-v10-core` | `root:root` | `0750` | `bash -n` | **attestation-only** |
| `maintenance-lock-lib` | `ops/lib/rpi5-maintenance-locks.sh` | `/usr/local/lib/rpi5-maintenance/rpi5-maintenance-locks.sh` | `root:root` | `0644` | `bash -n` | **attestation-only** |
| `backup-cron` | `ops/cron.d/rpi5-backup` | `/etc/cron.d/rpi5-backup` | `root:root` | `0644` | exact nightly cron contract | managed replace |
| `backup-logrotate` | `ops/logrotate.d/rpi5-backup` | `/etc/logrotate.d/rpi5-backup` | `root:root` | `0644` | debug-only `logrotate -d` | managed replace |

The first three files are the V25 shared-maintenance trust bundle: the canonical
serialized wrapper, immutable V10-ownership/runtime-V12 core and shared-lock
helper. Their topology was established by the dedicated V25 maintenance
cutover. Generic controlled deploy therefore **attests** those files but never
repairs them.

For an attestation-only target, `plan` requires the complete live fingerprint
(SHA-256, UID, GID and mode) to equal the reviewed source fingerprint. Any
difference fails closed with `attestation-only target drift`; no plan is
persisted. Repair must use the dedicated V25 maintenance path under separate
production authorization, followed by a fresh controlled-deploy preflight.

Cron and logrotate remain ordinary managed targets. Reviewed drift in those two
files may be planned as `replace` and receives the existing transaction and
rollback protections.

The engine independently hard-codes the complete approved tuple for every
entry: ID, source, production target, owner, group, mode and validators. A
manifest that preserves an approved ID but changes any other field is rejected
before engine installation, plan creation, deploy or status. The manifest is a
reviewed declaration, not authority to select arbitrary root paths.

`ops/backup/rpi5-backup.conf.example` is deliberately **reference-only**.
The real `/etc/rpi5-backup.conf` may contain private host configuration and
must never be replaced by the example.

Docker Compose, systemd units, Cloudflare, Home Assistant, monitoring, update
scripts and application repositories are not deploy targets in this contract.
Each must first be imported and reviewed under its own source/installed mapping,
validation and rollback contract.

## Baseline attestation and dashboard evidence

A successful transaction may contain `unchanged` V25 attestation rows. If the
production wrapper/core/helper already match reviewed source exactly, the
controller can attest that state without rewriting the V25 trust bundle.

After the full transaction and host verification succeed, the engine records
the exact `RPi5_main` commit and atomically writes `/var/lib/rpi5-deploy/latest-success`.
That pointer is the authoritative private source projected by the sanitized
dashboard deployment-evidence producer. It must never be fabricated manually.
If it is absent, no controlled-deploy production commit has been proven and the
dashboard correctly reports deployment state as `UNKNOWN`.

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
- the complete manifest equals the hard-coded approved current target contract;
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

The plan and deploy preflight require:

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

For ordinary managed targets, a file with matching content but wrong UID, GID
or mode is `DRIFT` and may be planned for correction. For V25 attestation-only
targets, any content or metadata mismatch fails planning instead. Immediately
before apply, `verify_plan_targets` also requires every attestation-only row to
remain `unchanged` with `before == desired`.

## Apply transaction

After all gates pass, deploy creates a root-only transaction below:

```text
/var/lib/rpi5-deploy/transactions/<UTC>-<short-commit>/
```

Immediately before processing each row, including `unchanged` rows, the engine
rechecks that the source SHA and full live fingerprint still equal the reviewed
plan. Attestation-only rows are validated and recorded as unchanged, with no
write. For every ordinary changed target it then:

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

The controller does not execute a backup, upload data, delete retention data,
rotate logs, reload cron, restart services or restart containers. Attestation of
the V25 bundle itself performs no target-file writes.

## Automatic rollback

Any exception after an ordinary target enters the mutation set starts automatic
rollback of changed targets in reverse order. V25 attestation-only rows cannot
enter that mutation set because their drift is rejected during planning. The
rollback-start audit log is best-effort and cannot block the actual restoration.
The old file is restored atomically, or a target that was previously absent is
removed. Every restored SHA-256, UID, GID and mode must exactly equal the
reviewed before-state. Transaction metadata records prepared, installed,
restored or restore-failed phases.

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

Attestation-only V25 rows are never manual-rollback targets because generic
controlled deploy did not write them.

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

- exact five-target V25-aware manifest scope and reference-only configuration guard;
- test mode cannot target `/` or escape its temporary sandbox;
- deterministic engine staging, source/installed SHA binding and `env -i` wrapper;
- repository root commands route to the system engine;
- no production preflight-bypass environment variable exists;
- V25 wrapper drift is rejected before a plan is persisted;
- valid V25 wrapper/core/lock-helper rows remain `unchanged`;
- cron/logrotate drift remains ordinary managed `replace` work;
- exact-SHA confirmation;
- synthetic failure after a partial writable-target change and verified automatic rollback;
- durable rollback phase metadata;
- successful transaction and status reporting without rewriting the V25 bundle;
- refusal to roll back over metadata-only drift;
- verified manual rollback to exact before fingerprints.

`tests/test-controlled-deploy-rollback.py` adds focused transaction-hardening
regressions for:

- rejection of an ID-preserving manifest target-path change;
- rejection of a repository source symlink during status;
- failure after `latest-success` creation, full automatic restoration and stale
  pointer cleanup;
- proof that only cron/logrotate enter the mutation/rollback set while V25
  attestation rows remain unchanged;
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
part of the current constrained backup transaction.

## Rollback before production use

Before any separately approved engine installation or target apply, repository
rollback is simply reverting the reviewed source commit. After engine
installation, the versioned old engine release remains present; changing the
system wrapper back to it requires a separate reviewed engine-pointer
procedure. After a target apply, use the guarded transaction rollback and retain
its metadata for incident review.

The first production controlled-deploy baseline is a separate live action. It
requires a fresh exact-main preflight and explicit owner authorization for any
checkout sync, deploy-engine installation, plan/state creation or transaction
write. Missing `latest-success` must remain `UNKNOWN` until that authorized
transaction succeeds.
