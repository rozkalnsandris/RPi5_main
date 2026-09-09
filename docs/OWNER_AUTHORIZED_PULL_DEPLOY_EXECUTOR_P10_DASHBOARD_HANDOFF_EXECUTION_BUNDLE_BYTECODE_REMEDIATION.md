# P10 Dashboard execution-bundle bytecode incident remediation

Status: **source only / execution disabled / separate LIVE/root gate required**.

## Incident prestate

The accepted `112f272e...` root execution bundle was initially exact, but the pre-#437 wrapper imported the trusted core without disabling Python bytecode writes. The first import created a root-owned `__pycache__` entry inside the otherwise immutable three-file bundle. PR #437 prevents recurrence for newly materialized bundles; it does not mutate or clean the already contaminated root namespace.

This remediation is deliberately incident-specific. The remediator accepts only the exact observed prestate: bootstrap blob `78dcf901...`, old wrapper blob `da6b3756...`, unchanged core blob `409ea15d...`, exact `112f272e... / 92036c09...` execution manifest, and the exact observed `.pyc` SHA-256 `5b1e05af...`. Any tree, hash, owner, mode, target or quarantine drift fails before mutation.

## Reviewed path

1. prepare/prove the normal fixed unprivileged execution ingress against fresh merged `RPi5_main/main`;
2. unprivileged remediation bootstrap emitter emits only the committed remediator bytes;
3. under a separate LIVE/root gate, write those bytes from stdin only to fixed root-owned `/var/lib/rozkalns-dashboard-handoff-exec/.bundle-remediator-v1.py`, set `root:root 0444`, and independently prove its Git blob/SHA-256 before Python execution;
4. unprivileged remediation payload emitter emits the current committed absent-only bundle materializer plus wrapper/core/manifest bytes from the fixed ingress;
5. execute only the fixed root remediator with `--apply --ack RPi5_main:DASHBOARD-HANDOFF-EXECUTION-BUNDLE-BYTECODE-REMEDIATE-V1` and the bounded JSON payload on stdin;
6. STOP and run the independent unprivileged remediation proof;
7. only after PASS may the normal fresh handoff/candidate continuation be reconsidered under its own gates.

## One-shot root mutation envelope

The remediator creates fixed partials first, re-verifies them, then uses `renameat2(RENAME_NOREPLACE)` only. It preserves the contaminated evidence by renaming:

- `.bundle-materializer-v1.py` -> `.bundle-materializer-v1.py.stale-78dcf901-112f272e`;
- `v1` -> `.v1.stale-112f272e-92036c09-bytecode-5b1e05af`.

It then publishes the fresh current bundle materializer and exact fresh execution bundle. There are no deletions, no overwrite, no symlink following, no caller-supplied path/source/command/script/environment authority, no Git/network/subprocess activity in the root remediator, and no handoff/candidate/deploy execution.

If any mutation has started and any subsequent step fails or becomes ambiguous, preserve all old/new/partial evidence and STOP. No automatic retry, cleanup, rollback or alternate path is authorized.

Source merge grants no LIVE/root authority. `LIVE-ALL` does not make this STRICT trust-boundary remediation ordinary or reusable.
