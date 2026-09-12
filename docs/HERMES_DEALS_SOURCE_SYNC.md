# Hermes Deals source-sync static operation contract

Issue #484 implements Phase 4 bundle #472 Job 6 as **source-only** trust-boundary metadata. It does not provide a runnable host adapter and does not authorize or perform a source checkout update.

## Fixed identity

- Operation: `hermes-deals.source-sync.v1`
- Future LIVE gate: `hermes-deals.source-sync.sync.v1`
- Target alias: `hermes-deals-source-sync`
- Repository: `rozkalnsandris/hermes-deals` (`1317143994`)
- Canonical checkout: `/home/andris/hermes-deals`
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
