# V12 controlled RPi5 deploy contract

## Purpose

V12 adds a simple operator interface for reviewed production deployment from
`RPi5_main`, while keeping the host-wide safety boundary stricter than an
application deploy. It provides the same small set of actions used by the
simplified Hermes workflow—sync, test, plan, deploy, status, rollback and
logs—but does not turn a merge into an automatic production change.

The workflow remains:

1. branch, tests, Draft PR, CI, review and squash merge;
2. sync `main` on the RPi5;
3. run and review a read-only deployment plan;
4. apply that exact short-lived plan with the exact 12-character commit;
5. verify the transaction, or automatically restore its before-state.

V12 itself is repository tooling only. Merging V12 does not authorize or
perform a production deployment.

## Initial managed scope

The target manifest is `ops/deploy/targets.json`. V12 manages exactly:

| Repository source | Production target | Owner | Mode | Validation |
|---|---|---:|---:|---|
| `ops/bin/rpi5-backup` | `/usr/local/sbin/rpi5-backup` | `root:root` | `0700` | `bash -n` |
| `ops/cron.d/rpi5-backup` | `/etc/cron.d/rpi5-backup` | `root:root` | `0644` | exact nightly cron contract |
| `ops/logrotate.d/rpi5-backup` | `/etc/logrotate.d/rpi5-backup` | `root:root` | `0644` | debug-only `logrotate -d` |

`ops/backup/rpi5-backup.conf.example` is deliberately **reference-only**.
The real `/etc/rpi5-backup.conf` may contain private host configuration and
must never be replaced by the example.

Docker Compose, systemd units, Cloudflare, Home Assistant, monitoring, update
scripts and application repositories are not deploy targets in V12. Each must
first be imported and reviewed under its own source/installed mapping,
validation and rollback contract.

## Operator commands

Run normal repository actions without root:

```bash
bash ./scripts/rpi5-deploy sync
bash ./scripts/rpi5-deploy test
```

Run host inspection and transactions through sudo:

```bash
sudo bash ./scripts/rpi5-deploy plan
sudo bash ./scripts/rpi5-deploy deploy --confirm <12-character-commit>
sudo bash ./scripts/rpi5-deploy status
sudo bash ./scripts/rpi5-deploy rollback --latest --confirm ROLLBACK
sudo bash ./scripts/rpi5-deploy logs --lines 150
```

The matching VS Code tasks are tracked in `.vscode/tasks.json`. `Deploy plan`
and `Deploy reviewed plan` are separate tasks on purpose: the operator must see
the planned before/source SHA values before entering the confirmation SHA.

## Repository and CI preflight

A production plan fails unless all of the following hold:

- the remote is `rozkalnsandris/RPi5_main`;
- the checked-out branch is `main`;
- `git status --porcelain=v1 --untracked-files=all` is empty;
- a fresh fetch succeeds and local `HEAD` equals `origin/main`;
- `make validate` succeeds as the normal repository owner;
- GitHub CLI returns at least one check run for the exact commit;
- every exact-commit check run is completed with conclusion `success`.

Git porcelain v1 is used because Git documents it as stable for scripts. The
exact commit and live target fingerprints are written into a short-lived plan,
not inferred again from a branch name at apply time.

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

The backup gate reads only the timestamp of the successful log marker. It does
not print archive names, remote paths, keys, tokens or configuration contents.

The tracked runtime baseline is intentionally strict. When the runtime has
legitimately changed, update and review the baseline first instead of teaching
the deploy command to ignore drift.

## Plan binding

`plan` writes root-only state to:

```text
/var/lib/rpi5-deploy/plans/latest.json
```

The plan includes:

- exact full and 12-character source commit;
- manifest SHA-256;
- repository, CI and sanitized host preflight results;
- source SHA-256 for every target;
- exact live before-state: presence, SHA-256, UID, GID and mode;
- `replace` or `unchanged` action;
- creation and expiry times.

The default lifetime is 30 minutes. `deploy` refuses an expired plan, a changed
manifest or source, a different commit, or any target whose live fingerprint no
longer equals the reviewed before-state.

## Apply transaction

After all gates pass, deploy creates a root-only transaction below:

```text
/var/lib/rpi5-deploy/transactions/<UTC>-<short-commit>/
```

For every changed target it:

1. copies the old regular file into a private `0600` transaction backup;
2. verifies the private backup SHA-256 against the reviewed before-state;
3. copies the source to a temporary file in the target directory;
4. applies explicit owner, group and mode;
5. validates the temporary file;
6. replaces the target with same-directory `os.replace()`;
7. verifies SHA-256, UID, GID, mode and validators again.

V12 does not execute a backup, upload data, delete retention data, rotate logs,
reload cron, restart services or restart containers. The three initial targets
do not require a service restart.

## Automatic rollback

Any exception after a target enters the mutation set starts automatic rollback
in reverse order. The old file is restored atomically, or a target that was
previously absent is removed. Every restored fingerprint must exactly equal the
reviewed before-state. The transaction is marked `rolled_back`; an incomplete
restore is marked `rollback_failed` and reported clearly.

## Manual rollback

Only the latest successful transaction can be rolled back in V12. Before
restoring a target, the command requires its current SHA-256 to equal the
transaction's post-deploy SHA-256. This prevents rollback from overwriting a
later manual or reviewed change.

Rollback is deliberately not blocked by a failed container or failed systemd
unit, because those may be the reason rollback is needed. It still requires the
correct host, an exclusive deploy lock and no conflicting maintenance process.
After restoration, the full host preflight runs. If runtime health still fails,
the command reports that files were restored but the incident remains.

## Logs and secret boundary

The deploy log is root-only at `/var/log/rpi5-deploy.log`; concise markers are
also sent to journald with tag `rpi5-deploy`. Logs contain command phase,
transaction ID, short commit and sanitized error text. They do not contain file
contents, environment values, tokens, keys, backup names or raw configuration.

## Testing

`tests/test-controlled-deploy.sh` runs without root, Docker or systemd changes.
It builds a temporary Git repository and fake root, then verifies:

- exact manifest scope and reference-only configuration guard;
- plan creation and exact-SHA confirmation;
- rejection of a wrong confirmation;
- synthetic failure after a partial write and verified automatic rollback;
- successful atomic deployment and status reporting;
- refusal to roll back over later drift;
- verified manual rollback to exact before fingerprints.

Run all repository checks with:

```bash
make validate
```

## Research decision: manifest transaction before Ansible

Ansible check and diff modes are valuable for later, larger subsystem imports.
However, Ansible documents that check mode is only a simulation, unsupported
modules may report nothing, and diff output can reveal sensitive information.
V12 therefore uses a small manifest-driven transaction with no new production
dependency. When broader configuration is imported, Ansible can be added under
this same outer commit/CI/plan/rollback contract, with `diff: false` on private
configuration tasks.

Docker Compose changes later must at minimum use `docker compose config --quiet`
and an available Compose dry-run before any apply. They are intentionally not
part of the initial three-file transaction.

## Repository rollback

Before any separately approved production use, revert the V12 repository
commit. After production use, use the guarded transaction rollback and retain
the transaction metadata for incident review.
