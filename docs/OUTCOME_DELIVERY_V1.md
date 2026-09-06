# Outcome Delivery v1 — RPi5_main

Status: **ACTIVE repository-local delivery contract**

Machine contract: `.github/outcome-delivery-v1.json`

This contract narrows how `FAST-LANE v2.2` and `AUTO-RUN FULL v2` package source work. It does **not** weaken `AGENTS.md`, the active `main` ruleset, merge authority, or any LIVE/runtime boundary.

## Goal

Optimize for **time from an approved outcome to a verified outcome**, not for the number of PRs, commits, proof objects, or handoff comments.

The default unit of delivery is:

```text
one outcome issue
  -> one outcome branch
  -> 2-5 closely related same-risk work items
  -> one Outcome PR
  -> required GitHub checks/review convergence
  -> one merge decision model
  -> optional one bounded Composite LIVE
  -> verified outcome
```

Small commits are encouraged **inside** the Outcome PR. A PR should stay conceptually focused, but it should also contain enough of the vertical slice to be independently useful and testable.

## What belongs in one Outcome PR

Include the pieces needed to make the stated outcome coherent, as applicable:

- implementation;
- wiring/integration;
- focused and adversarial tests;
- operator/preflight/validation entrypoint;
- documentation and provenance/current-state update.

Do not create a separate PR merely because one of those pieces is a different internal layer. Split only when the new piece is independently valuable, crosses a different risk/trust boundary, targets a different runtime/owner decision, or would otherwise stop being a coherent review unit.

This preserves the existing FAST allowance to batch **2-5 closely related same-risk work items** while making the batch outcome-bearing rather than proof-object-bearing.

## Native stacked pull requests

GitHub native stacked pull requests are **not the default for `RPi5_main`**.

As reviewed on 2026-09-06, GitHub stacked PRs are in public preview, require a fully linear stack history, and normal stack maintenance uses cascading rebases. GitHub CLI's `gh stack push` uses `--force-with-lease`; the GitHub website's stack rebase also rewrites the stack branches. GitHub also documents that auto-merge is not supported for stacked pull requests.

`RPi5_main` currently forbids force-push/history rewrite. Therefore:

- do not create native stacked PRs under the current policy;
- do not weaken the no-force/no-history-rewrite rule merely to gain stack throughput;
- do not simulate stacks with a long chain of serial dependent PRs, because that recreates the fragmentation this contract is intended to remove;
- stacked PRs may be reconsidered only through a separate explicit repository-policy change.

If a future policy deliberately enables stacks, the stack must still preserve the same main-branch rules, exact-head review discipline, and owner merge authority.

## CI and ruleset

Speed improvements must come from larger coherent outcome batches and less human/PR serialization, **not** from weakening `main`.

Keep the active repository ruleset semantics:

- pull request required;
- squash-only merge;
- linear `main` history;
- required review-thread resolution;
- strict required status checks;
- no bypass/force merge.

Strict required status checks can cause a new build if `main` moves. That tradeoff is intentionally retained. With one Outcome PR rather than many serial PRs, the amount of self-inflicted base drift should fall.

Existing PR workflow concurrency may continue cancelling superseded PR runs. Do not remove required checks to save CI time.

## FAST exact-head conditional MERGE

FAST still requires a **separate explicit owner MERGE decision**.

Once the final intended diff is frozen and the exact PR head is known, the owner may authorize merge even if required checks are still running:

```text
MERGE RPi5_main #<pr> HEAD=<exact-head-sha>
```

That records `MERGE_AUTHORIZED_PENDING_CHECKS`; it does **not** merge immediately and it grants no LIVE authority.

Before executing the merge, automation must freshly verify:

1. current `main` and PR state;
2. PR head is still the exact authorized SHA;
3. the final diff still matches the authorized outcome/scope;
4. every required ruleset status check is passing;
5. unresolved review threads are zero;
6. mergeability is currently acceptable;
7. squash merge remains the allowed method.

Execution must use an expected-head SHA guard (or an equivalent fail-closed GitHub primitive). GitHub's pull-request merge REST API supports a head `sha` precondition and rejects a mismatched head.

If the PR head changes for **any** reason, including a corrective commit or base synchronization that produces a new head, the prior FAST merge authorization is void. A new explicit `MERGE ... HEAD=<new-sha>` is required.

Do **not** arm GitHub auto-merge early for a SHA-bound FAST authorization. The FAST authorization is bound to one exact head, while early PR-level auto-merge can outlive that exact head. The expected-head guarded merge path is the fail-closed default for FAST.

## AUTO-RUN FULL relationship

A valid `AUTO-RUN FULL RPi5_main #<issue>` activation is already the issue-scoped owner merge decision defined by that separate contract, so it does not add a second FAST merge gate.

AUTO-RUN FULL should still use the same default packaging:

```text
one frozen implementation issue -> one Outcome PR
```

Its GitHub native auto-merge behavior remains conservative: enable auto-merge only after final exact-head diff/scope review, required CI, review convergence and mergeability are already fresh. If the head changes, readiness must be re-established.

Native stacked PRs remain disabled under the current no-history-rewrite policy.

## Composite LIVE

Outcome batching does not combine unrelated risk classes.

After source merge and exact-main verification, at most one bounded Composite LIVE may cover the tightly coupled runtime steps for that outcome **only** when the separate LIVE authorization binds the exact SHA, target, mutation classes, limits, exclusions and expected baseline.

Merge never authorizes LIVE. The first authorized runtime mutation consumes that LIVE authorization. Any later error or ambiguity follows only predeclared recovery semantics; otherwise STOP with no retry, rollback, cleanup or alternate mutation path.

## Continuity

Current continuation should stay short and decision-oriented:

```text
GOAL
DONE
REMAINING
EXACT NEXT GATE
```

Historical evidence may remain append-only, but it must not obscure the current lane or force every continuation to reconstruct the project from a long supersession chain.

## External guidance reviewed

Reviewed 2026-09-06:

- GitHub Docs — About/Reference/Managing/Merging stacked pull requests
- GitHub Docs — Optimizing CI for stacked pull requests
- GitHub Docs — Automatically merging a pull request
- GitHub Docs — Rulesets / strict required status checks
- GitHub REST API — Merge a pull request with exact head `sha`
- DORA — Working in small batches

These sources inform the packaging/merge mechanics only. Repository-local safety rules remain authoritative where stricter.
