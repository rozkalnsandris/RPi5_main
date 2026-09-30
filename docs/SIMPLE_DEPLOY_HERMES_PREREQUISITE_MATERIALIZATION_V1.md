# Hermes SIMPLE-DEPLOY host-prerequisite materialization v1

Issue: `#711`  
Status: **SOURCE READY CONTRACT / NOT LIVE**

## Purpose

Hermes is the first non-Weather reuse of the generic SIMPLE-DEPLOY v1 host reconciler. The reviewed compatibility adapter deliberately moved Hermes runtime dependencies into fixed RPi5-owned paths, but #690/#691 did not create or populate those paths. This outcome defines one deterministic operation for that prerequisite instead of widening the generic reconciler or relying on ad-hoc shell copy steps.

The operation is separate from `scripts/adopt-simple-deploy-hermes-v1.py`. Prerequisite materialization prepares the fixed host data/config/private-env inputs; target adoption later installs the reviewed Hermes Compose adapter and two-target registry. A future owner may authorize both in one bounded Composite LIVE, but source merge never authorizes either operation.

## Fixed source identity without publishing a user-home path

The source account is fixed as `andris`. The concrete home directory is resolved from the operating system passwd database for that account; it is not accepted from CLI input, environment, GitHub intent or another caller-controlled source.

Within that passwd-resolved home, the source identities are fixed structurally:

- checkout relative path: `hermes-deals`;
- data relative to checkout: `data/raw`;
- config relative to checkout: `config`;
- protected env relative to checkout: `.env`.

This representation preserves the exact host identity while keeping concrete user-home paths out of the public repository. The resolved home must be absolute and the source metadata must match the fixed account.

Destination identities remain absolute, public-safe and fixed:

- state root: `/var/lib/rozkalns-simple-deployer/hermes-deals`;
- data: `/var/lib/rozkalns-simple-deployer/hermes-deals/data/raw`;
- config: `/var/lib/rozkalns-simple-deployer/hermes-deals/config`;
- private env: `/etc/rozkalns-simple-deployer/private/hermes-deals-api.env`.

The CLI exposes only `--expected-source-sha` and `--apply`. There is no caller-selectable home, path, project-directory, env-file, key, repository, target, command, argv, Docker or systemd surface.

## Public-safe default preflight

Running the entrypoint without `--apply` is non-mutating and does **not** read `.env` values or application file contents. It validates the exact reviewed source checkout, machine contract, fixed path metadata and the public-safe destination shape.

It returns one of three states:

- `ABSENT`: fixed final destinations are absent and any already-existing parent directories have exact reviewed metadata;
- `EXACT_READY`: both final destinations exist with exact root-owned metadata and the fixed top-level shape;
- `PARTIAL_CONFLICT`: mixed presence, staging residue, symlink/type drift, ownership/mode drift, source metadata drift or unexpected top-level destination entries.

`EXACT_READY` at this public-safe layer deliberately means exact **metadata/shape readiness**. Protected content equivalence is checked only inside the future protected apply authority; public preflight must not leak app data or secret values merely to prove readiness.

## Protected plan and materialization

`--apply` is implemented for a future separately authorized Composite LIVE. #711 itself and its CI never invoke it.

Inside that future authority the entrypoint:

1. requires public preflight `ABSENT` or verifies an already-`EXACT_READY` destination;
2. reads only the fixed protected sources derived from the fixed account's passwd-resolved home;
3. rejects source symlinks, special files, ownership drift, world-writable/setuid/setgid entries and malformed protected env input;
4. projects exactly `DATABASE_URL` and `HTTP_USER_AGENT`, in that order, into the private env destination;
5. never emits either value in logs, diagnostics or receipts;
6. stages data/config under the fixed `/var/lib/rozkalns-simple-deployer` staging path, normalizing destination directories to `0755` and files to `0644` as `root:root`;
7. stages the private env as `root:root 0600` under the fixed private staging path;
8. verifies staged content against the protected source before publication;
9. publishes the state root, then publishes the private env without replacing an existing final file;
10. verifies public `EXACT_READY` plus protected content equivalence.

No destination merge or overwrite is allowed. Existing partial state is a conflict rather than a reconciliation hint.

## Failure semantics

The operation has no automatic retry, rollback or failure cleanup. Once the first authorized mutation occurs, any later error leaves evidence/staging/partial publication in place and terminates with a mutation-aware error receipt. A new owner decision is required before any retry, cleanup, rollback or alternate path.

The only success-path deletion is removal of the operation's own private-env staging hard link after the final private env has been published and fsynced.

## Dependency isolation preserved

This outcome does not alter the generic SIMPLE-DEPLOY executor, the generic first installer, the Hermes API-only Compose adapter or the #709 adoption semantics. It grants no lifecycle authority for `db`, `web` or `worker`, and it does not add `--remove-orphans`, project-directory, arbitrary env or arbitrary command authority.

## Source acceptance

The focused synthetic suite must prove:

- `ABSENT`, `EXACT_READY` and `PARTIAL_CONFLICT` classification;
- symlink/type/ownership/mode and unexpected-entry fail-closed behavior;
- no protected value read or emission in default preflight;
- missing, duplicate and malformed required env handling with redacted diagnostics;
- exact two-key private env projection;
- protected tree metadata validation and deterministic normalized copy;
- no overwrite of existing final destinations;
- no automatic cleanup after a post-mutation publication failure;
- CLI authority remains limited to the two reviewed options;
- machine contract keeps prerequisite materialization distinct from Hermes target adoption;
- source identity remains fixed through passwd-account resolution without a concrete user-home literal in public source.

CI uses synthetic fixtures only. It never reads the production `.env`, application data/config or RPi5 runtime.

## Future owner gate

After the source Outcome PR is merged and exact-main CI is green, only the public-safe default preflight is eligible without new LIVE authority. Any real `--apply` must be covered by a future exact owner envelope that binds the merged SHA, host `rpi5`, Hermes target, host filesystem/application-data materialization, protected-config/secret read+write and the expected no-retry/no-rollback/no-cleanup semantics. Target adoption and Docker reconciliation remain separately named classes even if that future envelope authorizes them together.
