# V12 findings

## Sources reviewed

The design was derived from:

- the current `RPi5_main` V01–V11 contracts, tests, runtime baseline and exact V10 backup ownership map;
- the historical RPi5 audit, RPi5 master requirements and exported conversation index available in the File Library;
- the existing weekly update preflight and installer/rollback scripts;
- available Hermes, Qwen and RPi5 audit logs;
- real Hermes operator deployment screenshots showing successful checked deployment, dispatcher rollback and a root-only release-tool boundary failure;
- official Git documentation for stable porcelain and exact worktree semantics;
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

## Implemented result

V12 adds:

- a normal-user repository controller at `scripts/rpi5-deploy`;
- deterministic staging and separately confirmed installation of a versioned,
  root-owned deploy engine;
- a root-owned `/usr/local/sbin/rpi5-deploy` wrapper that starts with `env -i`;
- source/installed SHA-256, owner and mode verification for the engine;
- `ops/deploy/targets.json` with exactly three non-secret V10 targets;
- VS Code tasks for sync, test, engine installation/status, plan, deploy,
  status, rollback and logs;
- a short-lived root-owned plan with full before/desired fingerprints;
- private transaction backups, fsync and same-directory replacement;
- automatic reverse-order rollback and guarded manual rollback;
- non-root fake-root tests for sandboxing, engine staging, partial failure,
  durable rollback phases, successful apply and metadata-only drift refusal.

No engine installation, host deployment, service action, backup execution,
upload, retention deletion, log rotation or production write was performed
while implementing V12. Draft PR #31 remains the review boundary.
