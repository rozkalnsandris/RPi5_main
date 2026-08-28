# Owner-authorized deploy executor v1 — P9 trusted evidence provenance

Status: **SOURCE CONTRACT ONLY — NO HOST INSTALL / NO LIVE AUTHORIZATION**

Roadmap: `RPi5_main#236`  
Work item: `RPi5_main#255`  
Preceding evidence schema gate: `RPi5_main#251` / PR `#254`

## Purpose

The merged P9 evidence parsers accept short-lived governance and Hermes origin
baseline objects, but parser-valid JSON is not authority by itself. This gate
freezes the consumer-side provenance boundary that a later separately
owner-authorized host installation must satisfy before either object can enter
`run_p9_dry_run_canary()`.

The unprivileged executor must never gain a generic protected-host reader or an
arbitrary evidence path. It may consume only two fixed sanitized objects from a
root-controlled spool.

## Fixed spool contract

Source constant:

`/run/rozkalns-deploy-executor-evidence`

Required future host ownership/mode:

- directory: `root:rozkalns-deploy-executor`, mode exactly `0750`;
- governance object: `governance.json`, `root:rozkalns-deploy-executor`, mode exactly `0440`;
- Hermes baseline object: `hermes-origin-baseline.json`, same ownership/mode;
- evidence files must be regular, non-symlink files with link count exactly 1;
- each object is bounded to 64 KiB;
- the executor has no API for caller-selected paths or filenames.

The loader opens the directory and then the fixed filename with `dir_fd` and
`O_NOFOLLOW` where available, validates ownership/mode/type/link/size using the
opened descriptors, reads a bounded payload, re-checks file identity/size/time
metadata after the read, requires strict UTF-8 JSON with the expected schema,
and returns an immutable mapping plus SHA-256 of the exact bytes consumed.

The downstream P9 evidence parsers remain responsible for exact keys, freshness,
repository/source/operation/target bindings and all operation-specific boolean
claims. Provenance and semantic validation are deliberately separate fail-closed
layers.

## Producer boundary remains separate

This source gate does **not** implement or install either evidence producer.
A later reviewed producer gate must independently prove that:

1. only a root-owned reviewed producer can create/replace either fixed object;
2. the producer accepts no arbitrary path, command, shell, argv or generic JSON
   authority from the unprivileged executor;
3. protected Hermes registration/probe/dispatcher/workflow inspection occurs
   only inside the separately authorized STRICT boundary;
4. governance evidence comes from a fresh reviewed writer-set audit rather than
   a permanent `trusted=true` flag;
5. production writes use a same-directory temporary file followed by an atomic
   replace only after the complete sanitized object is ready;
6. the emitted object contains only the allowlisted schema fields already frozen
   by the P9 evidence contracts;
7. producer source identity and host placement are bound to an exact reviewed
   `RPi5_main` SHA before installation.

No HMAC/signing key is introduced by this gate. The trust root is the later
root-owned producer + root-owned spool placement, not a secret shared with the
unprivileged executor.

## Relationship to the current P8 service

The accepted P8 poller remains `NoNewPrivileges=true`, capability-free and
mutation-disabled. Its current writable surface remains its state directory.
This PR does not edit the installed service, timer, credential, registry or
sandbox.

A later source/runtime composition may add read-only visibility of the fixed
sanitized spool only after the producer/installation contract is separately
reviewed. It must not expose `/etc`, `/root`, runner worktrees, raw application
configuration or another protected tree to the executor.

## Regression requirements

The source suite must prove:

- valid governance and Hermes baseline fixed objects load;
- directory mode/ownership drift rejects;
- file mode/group drift rejects;
- symlinks and hard links reject;
- wrong evidence schema rejects;
- oversized evidence rejects;
- returned payload is immutable;
- public loader entrypoints accept no path argument.

## Explicit non-goals

This gate does not:

- read protected host state;
- create or run an evidence producer;
- create/change a `READY` deploy queue item or `LIVE-AUTH`;
- change the production registry (`execution_enabled=false`, `operations=[]`);
- change the P8 poller, service, timer or dispatcher;
- place/change either GitHub App credential or permission scope;
- add the Rozkalns Automation runtime client/credential wiring;
- invoke `adapter.apply()`, consume an authorization or enter a root helper;
- deploy production, write DB/Review/publication state, mutate Cloudflare, or
  retire Hermes Deals runners.

Merge remains a separate owner decision. Any actual spool/producer/credential/
systemd/host installation remains a later Composite STRICT owner gate.
