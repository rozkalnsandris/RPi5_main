# RPi5_main Netto v2 trusted checkout bootstrap

## Purpose

This source-only contract defines the bootstrap boundary for creating one exact detached
`RPi5_main` checkout from which the merged Netto v2 installer can be read-only preflighted.
It exists because the ordinary manager checkout may be stale or dirty while still being safe
to use only as a Git object/ref manager.

This document does not create the checkout, run the installer, install the helper, invoke the
helper, or authorize any LIVE mutation.

## Fixed identities

- manager repository: `rozkalnsandris/RPi5_main`;
- manager checkout: `RPi5_CHECKOUT_PARENT/RPi5_main`;
- origin: `https://github.com/rozkalnsandris/RPi5_main.git`;
- trusted target: `RPi5_CHECKOUT_PARENT/RPi5_main-netto-nonroot-preflight-v2-installer-trusted`;
- minimum reviewed ancestor: `9bdab44ecdbdf016626cd50cb5b37d0ee265fb24`;
- exact source SHA: supplied only by a future explicit Composite LIVE authorization and must be
  a lowercase 40-character SHA.

The manager checkout working tree may be stale or dirty. That fact grants no repair authority.
The bootstrap may not modify its working-tree bytes, index or HEAD.

## Allowed mutation sequence

A future LIVE transaction may perform exactly two Git mutations, in order:

1. `git fetch origin main` in the fixed `RPi5_main` manager repository;
2. `git worktree add --detach <fixed-target> <exact-authorized-sha>` in that same repository.

After the fetch and before worktree creation, local `origin/main` must equal the exact authorized
SHA and that SHA must descend from `9bdab44ecdbdf016626cd50cb5b37d0ee265fb24`. Main drift stops the transaction before worktree
creation.

Before the first mutation, the fixed manager identity/origin, exact SHA syntax and target absence
must be proven read-only. The target path is not caller-selectable.

## Forbidden Git authority

No `reset`, `rebase`, `clean`, checkout/switch, merge/pull, worktree remove/prune, branch, commit,
push or force operation is authorized. No manager checkout repair or reconciliation is implied.

If the first Git mutation has started, any error or ambiguity stops the transaction. There is no
automatic retry, cleanup or rollback.

## Required post-create proof

The new trusted checkout must be proven:

- exactly at the fixed target path;
- `HEAD == <exact-authorized-sha>`;
- detached;
- clean including untracked files;
- bound to the exact reviewed GitHub origin;
- containing `scripts/install-hermes-deals-netto-nonroot-preflight-v2.py` at that exact SHA.

Checkout preparation alone authorizes no installer execution.

## Relationship to the Hermes checkout

The installer still requires the separate fixed Hermes checkout
`RPi5_CHECKOUT_PARENT/hermes-deals-netto-nonroot-preflight-v2-trusted`, frozen by
`ops/deploy/hermes-deals-netto-nonroot-preflight-v2-installer.json`.

After the exact RPi5 checkout is created and freshly verified, the next gate is to prepare that
Hermes checkout under its already-reviewed exact LIVE scope, then run the installer only in its
default read-only preflight mode.

Merge never authorizes either checkout creation, installer `--apply`, helper execution or canary.
