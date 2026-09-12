# Hermes Deals source-sync static operation contract

Issue #484 implements Phase 4 bundle #472 Job 6 as **source-only** trust-boundary metadata. It does not provide a runnable host adapter and does not authorize or perform a source checkout update.

## Fixed identity

- Operation: `hermes-deals.source-sync.v1`
- Future LIVE gate: `hermes-deals.source-sync.sync.v1`
- Target alias: `hermes-deals-source-sync`
- Repository: `rozkalnsandris/hermes-deals` (`1317143994`)
- Canonical checkout: `RPi5_CHECKOUT_PARENT/hermes-deals`
- Branch/ref/upstream: `main` / `refs/heads/main` / `origin/main`
- Reviewed workflow: `.github/workflows/rpi-source-sync.yml`
- Reviewed workflow blob: `b2f4eee1d1c503cf0c47b6099e748d6e6fd6d560`
- Registry remains globally `execution_enabled=false`; the operation is `STRICT`, ordinary-LIVE-ineligible, and rollback is `NONE`.

The checkout path, repository identity, branch/ref/upstream, Git operation shape, command, argv and environment are fixed source policy. They are not caller-selectable authority.

## Target provenance and fast-forward boundary

A future target must be one exact 40-hex SHA derived from a merged same-repository PR, reachable from current `hermes-deals/main`, with successful exact-target CI or explicitly validated tree-equivalent exact PR-head CI matching the reviewed workflow contract.

A future implementation may advance only the fixed canonical checkout by **fast-forward to that exact authorized SHA**. Reset, force checkout, rebase, hard clean, arbitrary-ref fetch, history rewrite and generic privileged Git/shell transport are outside the operation.

Before any future mutation, the implementation must prove read-only that the checkout exists as a Git worktree, is clean, has the exact repository/remote/branch/ref/upstream identity, and that the target is a valid fast-forward descendant with current provenance and CI.

After a future successful mutation, HEAD must equal the authorized SHA, the checkout must remain clean on `main`, and repository/remote/ref/upstream identities must remain exact. Production deploy, database, Review/publication/evidence, scheduler, systemd, Docker, network, package, user/group, credential and runner mutations are excluded.

## Job boundary

Job 6 stops at this static contract. It performs no network fetch, Git checkout update, dispatcher/helper invocation, replay consumption, READY/LIVE-AUTH creation or runtime receipt. Job 7 is responsible for executable preflight/postcondition and sanitized future canary-evidence source. Any real canonical checkout mutation still requires a separate reviewed owner LIVE authorization.

## Job 7 — executable read-only validation and future evidence

Issue #490 adds a dedicated source-only validator at `ops/lib/deploy_executor/hermes_deals_source_sync_evidence.py` and the closed machine contract `ops/contracts/hermes-deals-source-sync-evidence-v1.json`. The validator accepts one exact authorized target SHA plus a closed set of repository-controlled observations; caller-selected checkout paths, remotes, Git subcommands, commands, argv, environments and extra fields fail closed. It performs no Git or shell execution and grants no source-sync execution authority.

The preflight requires the fixed `HERMES_DEALS_CANONICAL_SOURCE_CHECKOUT` identity, repository ID `1317143994`, exact origin URL, `main` / `refs/heads/main` / `origin/main`, a clean worktree, merged same-repository target provenance, reachability from current main, exact-SHA CI or explicitly validated tree-equivalent PR-head CI, the reviewed workflow blob, and read-only fast-forward ancestry proof.

The deterministic postcondition is exactly `HEAD_EQUALS_EXACT_TARGET_AND_CLEAN_MAIN_CHECKOUT` plus unchanged repository/remote/checkout/branch/ref/upstream identity. The validator does not repair, fetch, merge, reset, checkout, clean or otherwise mutate the checkout.

Future canary evidence uses `rozkalns.hermes-deals.source-sync-canary-evidence.v1`, a closed field set that binds the exact RPi5 source SHA, Hermes target SHA, owner authorization issue/body hash, preflight/fast-forward facts, mutation-entry/fetch/head-change facts, postcondition result and explicit false attestations for every excluded mutation class. Synthetic PASS evidence is rejected.

A future owner LIVE gate must bind the exact RPi5 source SHA and exact immutable Hermes target SHA, provenance/CI, `hermes-deals.source-sync.v1`, `hermes-deals-source-sync`, the expected preflight baseline, one `FAST_FORWARD_TO_EXACT_AUTHORIZED_SHA_ONLY` mutation and `rollback_policy=NONE`. Job 7 creates no authorization and consumes no replay state. Future authorization is consumed at mutation-capable entry; after that point any error, ambiguity or drift requires evidence + STOP with no undeclared retry, cleanup, rollback or alternate path. Source execution remains disabled after #490.
