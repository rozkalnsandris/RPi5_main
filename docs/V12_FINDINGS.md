# V12 findings

## Sources reviewed

The design was derived from:

- the current `RPi5_main` V01–V11 contracts, tests, runtime baseline and exact V10 backup ownership map;
- the historical RPi5 audit, RPi5 master requirements and exported conversation index available in the File Library;
- the existing weekly update preflight and installer/rollback scripts;
- available Hermes, Qwen and RPi5 audit logs;
- real Hermes operator deployment screenshots showing successful checked deployment, dispatcher rollback and a root-only release-tool boundary failure;
- official Git documentation for stable porcelain and exact worktree semantics;
- official GitHub check-run documentation for exact-commit status retrieval;
- official Docker Compose documentation for configuration validation and dry-run behavior;
- official Ansible documentation for check/diff limitations and secret exposure risk.

The available File Library did not expose clearly named raw Claude or Gemini
export archives. Searches for Claude, Gemini, exports, RPi5 and deployment
material returned the conversation index, RPi5 master documentation, audits,
screenshots and logs. Those available sources were reviewed; this document does
not claim that an unavailable raw Claude/Gemini archive was parsed.

## Main findings

1. `RPi5_main` is already a source-of-truth and evidence repository, not a full
   host configuration tree. A global “deploy everything” command would be
   unsafe until each subsystem is imported with its own contract.
2. The production `/etc/rpi5-backup.conf` must remain outside the deploy target
   set; the tracked file is only a secret-free example.
3. Existing RPi5 maintenance already uses strong gates: disk/inodes, Compose
   validation, container health, maintenance locks, safe APT simulation,
   backups and rollback. V12 should reuse those principles instead of creating
   a weaker parallel path.
4. Real operator incidents show that privilege leakage, dispatcher boundaries
   and release identity checks are common failure points. User-writable
   repository Python therefore must not be the code executed directly as
   `root` by the supported workflow.
5. A branch name is not an adequate deployment identity. Plan and apply must
   bind the exact commit, exact GitHub checks, exact engine source and complete
   live before/desired fingerprints.
6. Content-only comparison is insufficient for cron, executable and system
   configuration files. UID, GID and mode are part of both drift detection and
   rollback protection.
7. Test bypass variables are unsafe unless they are confined to a fake root
   inside an explicit temporary sandbox. Production has no environment switch
   that skips GitHub or host preflight.
8. Rollback must refuse later drift, but must not require a healthy runtime
   before restoring files during an incident. Identity, filesystem and
   concurrency gates remain mandatory before restore; full health runs after.
9. Ansible check mode is useful later, but it is not a transactional guarantee
   and diff output can reveal sensitive data. A small explicit manifest is the
   safer first deploy boundary for the three already imported files.

## Review hardening findings

The Draft PR security review found and corrected additional failure paths before
V12 was allowed to leave review:

1. The original manual rollback could partially restore several files and then
   fail, leaving a mixed before/post state while the transaction still appeared
   successful. Manual rollback now pre-verifies every backup, creates verified
   post-state compensation snapshots, and returns already restored files to the
   deployed state if a later restore fails.
2. A corrupt transaction backup was previously detected only after it had been
   copied toward a live target. Every before-state backup is now checksum,
   ownership and mode verified before the first manual-rollback write.
3. The first implementation verified the plan before entering the transaction,
   but did not recheck each source and live before-state at the exact row
   mutation boundary. It now rechecks every row, including `unchanged` rows,
   and verifies the complete desired set before and after final host preflight.
4. A failure after writing `latest-success` could leave a stale pointer to a
   transaction that automatic rollback had already undone. The pointer is now
   atomic and removed on a failed apply when it refers to that transaction.
5. Merely requiring “some successful GitHub check” permits a false PASS if the
   repository validation job is missing. V12 now requires the exact successful
   check name `validate` in addition to requiring all latest returned checks to
   be successful.
6. Checking only manifest IDs permits an ID-preserving change to a different
   root path. The engine now contains an independent exact allowlist for every
   target's ID, source, destination, owner, group, mode and validators.
7. Status reporting originally hashed a source path without first rejecting a
   repository symlink. All target sources must now be regular, single-link,
   non-symlink files in status as well as plan and deploy.
8. An audit-log failure must never prevent rollback from starting. The
   rollback-start log is best-effort; transaction state and live restoration
   remain authoritative.

Each of these findings has a fake-root regression scenario in the repository
validation suite.

## Implemented result

V12 adds:

- a normal-user repository controller at `scripts/rpi5-deploy`;
- deterministic staging and separately confirmed installation of a versioned,
  root-owned deploy engine;
- a root-owned `/usr/local/sbin/rpi5-deploy` wrapper that starts with `env -i`;
- source/installed SHA-256, owner and mode verification for the engine;
- `ops/deploy/targets.json` with exactly three non-secret V10 targets plus an
  engine-side exact target allowlist;
- VS Code tasks for sync, test, engine installation/status, plan, deploy,
  status, rollback and logs;
- a short-lived root-owned plan with full before/desired fingerprints and a
  required exact-commit `validate` check;
- private transaction backups, fsync, same-directory replacement and atomic
  success-pointer handling;
- automatic reverse-order rollback, guarded manual rollback and compensating
  restoration of the deployed state after a failed manual rollback;
- non-root fake-root tests for sandboxing, engine staging, manifest and symlink
  tampering, partial failure, stale-pointer cleanup, backup corruption,
  compensation, durable rollback phases, successful apply and metadata drift.

No engine installation, host deployment, service action, backup execution,
upload, retention deletion, log rotation or production write was performed
while implementing or reviewing V12. PR #31 is the implementation review
boundary; merging it still does not install the engine or deploy any target.
