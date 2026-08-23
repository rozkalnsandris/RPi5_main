# V12 controlled RPi5 deploy contract

## Purpose and current topology

V12 is the reviewed exact-commit deployment controller for `RPi5_main`. The
controller lineage remains V12, but its target contract must follow the current
production maintenance topology. Production was migrated to the V25 shared-lock
backup architecture, so the controller must never replace the canonical V25
wrapper with the older immutable backup core.

The operator workflow remains:

1. sync reviewed `main`;
2. run repository validation;
3. generate and inspect a short-lived exact-commit plan;
4. apply only the reviewed plan with its 12-character commit confirmation;
5. verify status, or use the guarded rollback for targets the controller actually changed.

A merge never deploys automatically. Repository source changes do not install a
deploy engine, create a transaction or mutate a production target.

## Root execution boundary

The repository controller runs as the normal repository owner. Privileged
commands are routed through the installed, versioned, root-owned engine. The
repository Python source is never executed directly as root.

Normal-user commands:

```bash
bash ./scripts/rpi5-deploy sync
bash ./scripts/rpi5-deploy test
```

After a reviewed engine-source change, installation remains separately gated:

```bash
bash ./scripts/rpi5-deploy install-engine --confirm <12-character-main-commit>
bash ./scripts/rpi5-deploy engine-status
```

The installer requires clean exact `main`, successful `make validate`, the
required successful exact-commit GitHub `validate` check and the expected RPi5
host identity before privileged installation. Versioned releases live below:

```text
/usr/local/libexec/rpi5-deploy/releases/<40-character-commit>/
```

The root-owned `/usr/local/sbin/rpi5-deploy` wrapper starts the installed engine
with `env -i` and a fixed minimal `PATH`. Repository/GitHub checks run through
`runuser` as the non-root repository owner. Every root command verifies the
installed release inventory and recorded source hashes. A changed controller,
engine module or target manifest therefore fails closed until a separately
reviewed engine installation updates that binding.

Production controller commands remain:

```bash
bash ./scripts/rpi5-deploy plan
bash ./scripts/rpi5-deploy deploy --confirm <12-character-planned-commit>
bash ./scripts/rpi5-deploy status
bash ./scripts/rpi5-deploy rollback --latest --confirm ROLLBACK
bash ./scripts/rpi5-deploy logs --lines 150
```

Running the repository controller itself with `sudo` is rejected.

## Current target contract

`ops/deploy/targets.json` is a reviewed declaration. The engine independently
hard-codes the complete tuple for every approved ID, source, target, owner,
group, mode and validator. A manifest that changes any tuple is rejected before
planning, deployment or status.

The current five targets are:

| ID | Repository source | Production target | Owner | Mode | Policy |
|---|---|---|---|---:|---|
| `backup-runner` | `ops/bin/rpi5-backup-serialized` | `/usr/local/sbin/rpi5-backup` | `root:root` | `0750` | **attestation-only** |
| `backup-core` | `ops/bin/rpi5-backup` | `/usr/local/lib/rpi5-maintenance/rpi5-backup-v10-core` | `root:root` | `0750` | **attestation-only** |
| `maintenance-lock-lib` | `ops/lib/rpi5-maintenance-locks.sh` | `/usr/local/lib/rpi5-maintenance/rpi5-maintenance-locks.sh` | `root:root` | `0644` | **attestation-only** |
| `backup-cron` | `ops/cron.d/rpi5-backup` | `/etc/cron.d/rpi5-backup` | `root:root` | `0644` | managed replace |
| `backup-logrotate` | `ops/logrotate.d/rpi5-backup` | `/etc/logrotate.d/rpi5-backup` | `root:root` | `0644` | managed replace |

The first three files form the V25 shared-maintenance backup control plane:
canonical serialized wrapper, immutable V10-ownership/runtime-V12 core and
shared-lock helper. Their topology is owned by the dedicated V25 maintenance
cutover path. Generic controlled deploy therefore **attests** them but does not
repair or replace them.

For every attestation-only target, `plan` requires the complete live fingerprint
(SHA-256, UID, GID and mode) to equal the reviewed source fingerprint. Any
difference fails closed with `attestation-only target drift`. The operator must
use the dedicated V25 maintenance procedure under its own production
authorization to repair that drift, then re-run controlled-deploy preflight.

This rule prevents a generic deploy from undoing the V25 shared-lock topology
or replacing only one member of the maintenance trust bundle.

Cron and logrotate remain ordinary managed targets. A reviewed difference in
those two files may be planned as `replace` and receives the normal
transaction/rollback protections.

`ops/backup/rpi5-backup.conf.example` remains **reference-only**. The real
`/etc/rpi5-backup.conf` may contain private host configuration and is never a
controlled-deploy target.

Docker Compose, systemd units, Cloudflare, application repositories and other
host configuration remain outside this controller unless separately imported
with their own exact target, validation and rollback contract.

## V25 baseline attestation and dashboard evidence

A successful transaction may contain only `unchanged` V25 attestation rows.
This is intentional. If the production wrapper/core/helper already match the
reviewed V25 source exactly, the controlled-deploy transaction can attest that
state without rewriting the maintenance control plane.

After all rows and host gates pass, a successful transaction records the exact
`RPi5_main` commit and atomically updates:

```text
/var/lib/rpi5-deploy/latest-success
```

That pointer is the authoritative controlled-deploy state consumed by the
sanitized dashboard deployment-evidence producer. It must never be fabricated
manually. Missing `latest-success` means no controlled-deploy production commit
has been proven and the dashboard correctly reports deployment state as
`UNKNOWN`.

## Repository and CI preflight

A production plan fails unless all of the following hold:

- origin is the approved credential-free `rozkalnsandris/RPi5_main` remote;
- branch is `main`;
- worktree is clean, including untracked files;
- a fresh fetch succeeds and local `HEAD == origin/main`;
- installed engine source hashes equal the current tracked engine inventory;
- the manifest equals the hard-coded current target contract;
- `make validate` succeeds as the non-root repository owner;
- exact-commit GitHub check runs exist;
- every returned exact-commit check is completed successfully;
- the required `validate` check is present.

The root-owned plan is written only after those gates pass.

## Host preflight

The plan/deploy host gate requires the reviewed RPi5/Debian/architecture
identity, a read-write root filesystem, disk/inode/memory headroom, bounded
load/temperature, clear throttling when available, no conflicting maintenance
or package-manager operation, no failed systemd units, active `cron.service`, a
recent successful encrypted backup marker and the reviewed Docker runtime
baseline.

The backup gate reads only a bounded timestamp projection and does not expose
private archive names, paths, credentials or configuration values.

## Plan binding

`plan` writes root-only state to:

```text
/var/lib/rpi5-deploy/plans/latest.json
```

The plan binds:

- exact full and short source commit;
- installed engine/source inventory;
- manifest SHA-256;
- repository/CI/sanitized host preflight;
- source SHA-256 for every target;
- exact live before fingerprint;
- exact desired fingerprint;
- `replace` or `unchanged` action;
- creation and expiry timestamps.

Plans expire after 30 minutes by default. `deploy` refuses expired state,
changed source/manifest/commit, unsafe target parents or any live fingerprint
that changed after planning. Matching bytes with wrong ownership or mode are
still drift.

Before a plan is persisted, every V25 attestation-only target must already be
`unchanged`. Immediately before transaction apply, `verify_plan_targets`
reasserts that each attestation-only row is still `unchanged` and
`before == desired`.

## Apply transaction

A deployment creates root-only transaction metadata below:

```text
/var/lib/rpi5-deploy/transactions/<UTC>-<short-commit>/
```

Every row is revalidated immediately before use. `unchanged` rows are validated
and recorded but never written. For an ordinary changed target, the engine:

1. verifies source and exact before fingerprint;
2. creates and fsyncs a private `0600` before-state snapshot;
3. records the prepared phase;
4. stages the reviewed source in the target directory;
5. applies exact owner/group/mode and target validator;
6. atomically replaces the target and fsyncs the directory;
7. verifies the complete desired fingerprint;
8. records the installed phase.

After all rows, the engine verifies final state, runs the final host preflight,
verifies final state again, records `status=success`, and atomically writes
`latest-success`.

The controller does not run a backup, upload data, delete retention data,
rotate logs, reload cron or restart services as a deployment side effect.

## Automatic rollback

An exception after a writable target entered the mutation set triggers reverse
rollback of **changed targets only**. V25 attestation-only rows cannot enter that
set because planning refuses their drift.

Restoration must exactly reproduce the reviewed before SHA-256, UID, GID and
mode. If failure happened after the new `latest-success` pointer was created,
the pointer is removed when it still references the failing transaction. A
fully restored failure is `rolled_back`; incomplete restoration is
`rollback_failed` and remains an incident.

## Manual rollback

Only the latest active successful transaction is eligible. Before the first
rollback write, every changed target must still equal its recorded post-state,
every private before snapshot must verify, and a private forward compensation
snapshot is created. Later content or metadata drift therefore blocks rollback.

If a rollback attempt fails after writes begin, already restored targets are
returned to their deployed state from the compensation snapshots and the
active `latest-success` pointer is restored when compensation succeeds.
Attestation-only V25 rows are not rollback targets because the generic deploy
never changed them.

## Logs and secret boundary

The deploy log remains root-only at `/var/log/rpi5-deploy.log`; bounded markers
also go to journald under `rpi5-deploy`. Logs contain phase, transaction ID,
short commit and bounded errors, never arbitrary configuration contents,
environment values, embedded remote credentials, tokens, keys or backup
payload data.

## Testing

`tests/test-controlled-deploy.sh` uses a temporary repository and fake root to
prove:

- exact five-target V25-aware manifest scope;
- reference-only private backup configuration;
- test-mode sandbox isolation;
- deterministic installed-engine staging;
- no production preflight bypass variables;
- **refusal to plan when the canonical V25 wrapper drifts**;
- three V25 attestation rows remain `unchanged` in a valid plan;
- cron/logrotate remain managed `replace` targets when drifted;
- exact-SHA confirmation;
- automatic rollback after a partial writable-target failure;
- successful transaction/status while the V25 bundle remains untouched;
- guarded manual rollback of only the writable targets.

`tests/test-controlled-deploy-rollback.py` additionally proves manifest tuple
hardening, source-symlink rejection, pointer cleanup after failure,
rollback-backup integrity, compensated mid-rollback failure and exact final
restoration while V25 attestation targets remain byte/mode stable.

Run all repository checks with:

```bash
make validate
```

The tests do not install production files, run a real backup, reload cron,
restart services or mutate the host.

## Production authorization boundary

This source contract does not authorize:

- syncing or fast-forwarding the production checkout;
- installing a new deploy-engine release;
- creating a production plan;
- creating the first controlled-deploy transaction / `latest-success` baseline;
- replacing cron/logrotate targets;
- invoking the V25 maintenance repair/cutover path;
- running backup/update/cleanup;
- restarting services or timers.

Those remain separate explicit owner-authorized production actions after a
fresh exact-main preflight. If an authorized production mutation starts and any
error, ambiguity or drift occurs, preserve evidence and stop; do not retry,
rollback, clean up or select an alternate mutation path without new authority.
