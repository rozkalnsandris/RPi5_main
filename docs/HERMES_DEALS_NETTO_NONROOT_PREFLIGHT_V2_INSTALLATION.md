# Hermes Deals Netto non-root preflight v2 — first-install contract

## Purpose

This document defines the narrow source contract for first installation of the already-reviewed
Netto non-root preflight v2 helper and its root-owned registration. It does not assert current
host state, authorize installation, create execution wiring, or authorize a canary.

The installer exists because trusted-host read-only evidence can legitimately find the helper
or registration absent after the source binding is merged. That observation is never treated as
a durable baseline: every future installer preflight revalidates the exact source, checkout,
shared-parent metadata, and target absence.

## Frozen provenance

The installer binds one immutable Hermes source:

- repository: `rozkalnsandris/hermes-deals`;
- source SHA: `067db7bd4b8057bc16a9bf0ef9ed8487127a0a05`;
- helper path: `tools/runner/netto_missing_normal_price_nonroot_preflight_v2.py`;
- helper Git blob: `0f8b01ed3129323cc59e526262b369cf33346aba`;
- helper SHA-256: `275b1e3296f8f9c7312447dec1b1acb3ffd5d09beaab62ac5ca216275d98360c`.

Source bytes may come only from the fixed sibling checkout
`<RPi5-checkout-parent>/hermes-deals-netto-nonroot-preflight-v2-trusted`.
The installer requires that checkout to be detached, clean, at the exact SHA, with the exact
GitHub origin and with the frozen SHA reachable from local `origin/main`. The helper bytes must
match both the reviewed Git blob and SHA-256.

The installer does not create, fetch, repair, reset, clean, rebase, or otherwise mutate that
trusted checkout.

## Exact first-install surface

The installer is `scripts/install-hermes-deals-netto-nonroot-preflight-v2.py`.
Its default mode is read-only preflight. `--apply` requires root and a separate exact LIVE owner
authorization after the merged installer source has been freshly revalidated.

The owned first-install targets are exactly:

1. `/usr/local/libexec/hermes-deals-audits/netto-missing-normal-price-nonroot-preflight-v2`
   — directory, `root:root 0755`;
2. `/usr/local/libexec/hermes-deals-audits/netto-missing-normal-price-nonroot-preflight-v2/netto_missing_normal_price_nonroot_preflight_v2.py`
   — exact helper bytes, `root:root 0555`;
3. `/etc/hermes-deals-audits.d/netto-missing-normal-price-nonroot-preflight-v2.json`
   — canonical registration, `root:root 0444`.

The generated registration contains exactly:

- schema `rozkalns.hermes-deals.netto-nonroot-preflight-v2-registration.v1`;
- capability `netto-missing-normal-price-nonroot-preflight-v2`;
- registered source SHA `067db7bd4b8057bc16a9bf0ef9ed8487127a0a05`;
- helper SHA-256 `275b1e3296f8f9c7312447dec1b1acb3ffd5d09beaab62ac5ca216275d98360c`.

Its canonical 291-byte payload is frozen by SHA-256
`887ad4e9295864307a24df6773e98f75056961aebeedd57b95641ba3e7386a1f`
and Git blob `848773cf981f49265ca3e3a968c71fdd93c8aee2`.

Existing owned targets are never adopted, replaced, chmodded, chowned, or reconciled. Any one
existing target makes first-install preflight fail closed and requires a separate source decision.

## Shared parents

The installer validates but never creates or mutates these shared parents:

- `/usr/local/libexec/hermes-deals-audits` — `root:root 0755`;
- `/etc/hermes-deals-audits.d` — `root:root 0755`.

A missing or metadata-drifted shared parent is not silently repaired by this capability.

## Mutation and failure boundary

The complete apply budget is exactly one directory materialization plus two file
materializations. Files are created exclusively, with no symlink following, fixed bytes and
fixed modes. Post-write verification reopens each file descriptor-safely and rechecks inode,
ownership, mode, Git-blob identity and SHA-256 identity.

There is no automatic retry, cleanup or rollback. Once the first target creation begins, any
failure is reported with `mutation_started=true` and exact completed materialization counts.
The operator must stop; later reconciliation needs fresh evidence and new authorization.

This installer grants no arbitrary command, path, argv or environment authority. It does not
execute the helper, parser or canary; read credentials; call GitHub; write a database or Review;
deploy anything; mutate users/groups, Docker or systemd; or create execution wiring.

## Execution identity remains separate

Installing the helper does not make the read-only Netto canary runnable. The helper itself
requires non-root execution and rejects Docker-group authority. Selection or construction of a
compliant execution identity is deliberately outside this installer.

No user/group mutation, supplementary-group manipulation, service unit, broker, dispatcher or
generic privileged execution path is added by this source slice. That is a later source/trust
decision after a successful installation is freshly verified.

## Gate sequence

1. Merge and freshly verify this source contract and exact-main CI.
2. Freshly revalidate the current host before any mutation.
3. If absent, prepare the fixed Hermes trusted detached checkout only under its own exact LIVE
   scope; allowed Git changes are limited to `git fetch origin main` plus one fixed detached
   worktree creation. Reset/rebase/clean/force are forbidden.
4. Run the installer in default read-only preflight mode.
5. Only a successful preflight may lead to a separate exact root LIVE `--apply` authorization
   for the 1+2 mutation budget.
6. After apply, verify all three targets read-only.
7. Re-evaluate the non-root/no-Docker execution identity as a separate source gate.
8. A genuine Netto preflight invocation/canary remains a later independent READY/LIVE-AUTH gate.

Merge never authorizes LIVE work. Installation never authorizes helper invocation or runner
retirement.
