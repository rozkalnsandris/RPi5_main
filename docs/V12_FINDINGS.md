# V12 findings

## Sources reviewed

The design was derived from:

- the current `RPi5_main` V01–V11 contracts and exact V10 backup ownership map;
- the historical RPi5 audit and exported conversation index;
- the existing weekly update preflight and installer/rollback scripts;
- real Hermes operator deployment screenshots and controlled Hermes Deals logs;
- official Git, Docker Compose and Ansible documentation.

The available File Library did not expose clearly named raw Claude or Gemini
export archives. The review used the available conversation index, RPi5 master
requirements, audit files, Hermes/Qwen audit and deployment evidence. A future
raw export can be reviewed separately without weakening the V12 boundary.

## Main findings

1. `RPi5_main` is already a source-of-truth and evidence repository, not a full
   host configuration tree. A global “deploy everything” command would be
   unsafe until each subsystem is imported.
2. The production `/etc/rpi5-backup.conf` must remain outside the deploy target
   set; the tracked file is only a secret-free example.
3. Existing RPi5 maintenance already uses strong gates: disk/inodes, Compose
   validation, container health, maintenance locks, safe APT simulation,
   backups and rollback. V12 reuses those principles instead of creating a
   weaker parallel path.
4. Real operator incidents show that privilege leakage, dispatcher boundaries
   and release identity checks are common failure points. V12 separates normal
   Git/test actions from the root transaction and binds apply to exact source
   and target fingerprints.
5. A branch name is not an adequate deployment identity. The deploy plan must
   bind exact commit, exact CI result and exact live before-state.
6. Rollback must refuse later drift, but must not require a healthy runtime
   before restoring files during an incident.

## Implemented result

V12 adds:

- `scripts/rpi5-deploy` and three small Python modules;
- `ops/deploy/targets.json`;
- VS Code tasks for sync, test, plan, deploy, status, rollback and logs;
- a short-lived root-owned plan;
- private transaction backups and same-directory replacement;
- exact metadata/checksum validation;
- automatic and guarded manual rollback;
- non-root fake-root regression tests.

No host deployment, service action, backup execution or production write was
performed while implementing V12.
