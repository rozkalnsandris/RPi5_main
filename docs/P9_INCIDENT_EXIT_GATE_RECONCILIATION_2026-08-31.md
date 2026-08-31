# P9 incident exit-gate reconciliation — 2026-08-31

Status: SOURCE DECISION / PRE-MERGE
Roadmap: `RPi5_main#236`
Canonical incident evidence: `RPi5_main#191` comment `5483166469`
Source branch: `docs/236-p9-incident-clean-repeat-reconcile`

## Decision

`P9_EXIT_GATE=NOT_MET`

`CLEAN_P9_REPEAT_REQUIRED=true`

`P10_BLOCKED=true`

The technically successful `DRY_RUN_READY` result from the second P9 invocation is retained as diagnostic/control-plane evidence, but it is **not** accepted as the P9 exit-gate PASS.

## Basis

The P9 roadmap exit gate requires an end-to-end control-plane PASS with `PRODUCTION_MUTATION_STARTED=false`. The same repository operating contract requires authorization to be consumed at the first authorized mutation and requires evidence + STOP after any later error, ambiguity, or drift, with no automatic retry, cleanup, rollback, or alternate mutation path unless that behavior was explicitly pre-authorized.

The owner-authorized sequence produced the following public-safe evidence:

1. installed reviewed P9 source preflight PASS;
2. fresh Control baseline publication PASS for source `f04601dfd47e5691c875c0935b36ff101680f4dd` with `production_mutation_started=false`;
3. the first entered P9 command used `--issue-number #5`; POSIX shell comment parsing removed `#5`, so `argparse` failed with `argument --issue-number: expected one argument` before `run_p9_host_one_shot(...)` and before the genuine P9 StateStore/runtime path;
4. a subsequent invocation using `--issue-number 5` entered genuine P9 and returned `DRY_RUN_READY`, `mutation_dispatch_enabled=false`, `result_writer_enabled=false`, and `production_mutation_started=false`;
5. because the fresh baseline had already consumed the STRICT LIVE envelope, the corrected second invocation occurred after an error inside the consumed authorization envelope and therefore constituted a prohibited retry/procedural deviation under the frozen contract.

No evidence indicates production deployment, Worker deployment, Cloudflare configuration mutation, GitHub merge/decision mutation, or production mutation during this incident. The deviation is procedural/authorization-envelope non-compliance, not an observed production mutation.

## Exit-gate classification

The following evidence is accepted:

- fresh baseline: PASS;
- owner LIVE-AUTH provenance/binding: PASS at the genuine P9 execution time;
- malformed first P9 invocation: CLI parse failure before P9 runtime/StateStore;
- later genuine P9 technical result: `DRY_RUN_READY`;
- mutation dispatch/result writer: disabled;
- `PRODUCTION_MUTATION_STARTED=false`.

The following conclusion is **not** accepted:

- clean end-to-end P9 exit-gate PASS.

The no-retry/fail-closed property is part of the control plane being proven. A later successful runtime result cannot retroactively make an authorization-envelope retry compliant.

## Required continuation before P10

Before P10 may be considered, execute one **new clean genuine P9 canary** under a new, separately explicit STRICT LIVE owner authorization. That future envelope must be freshly bound to then-current GitHub/source state and must contain only the reviewed P9 sequence, including:

- one fresh trusted baseline satisfying the fixed freshness contract;
- one fresh owner-authored LIVE-AUTH satisfying the active TTL, identity, queue/source/operation/baseline and immutable-body checks;
- exactly one correctly formed P9 one-shot invocation;
- terminal success only if it returns `DRY_RUN_READY` with `mutation_dispatch_enabled=false`, `result_writer_enabled=false`, and `PRODUCTION_MUTATION_STARTED=false`;
- any error after the first authorized mutation => STOP, with no retry/cleanup/rollback/alternate mutation path unless explicitly pre-authorized in a future envelope.

The consumed/historical LIVE-AUTH and baseline involved in the incident are not reusable.

## P10 boundary

P10 remains blocked until all of the following are true:

1. this source decision is merged through the normal source review flow;
2. exact-main CI is fresh/green after merge;
3. one new protocol-compliant clean P9 canary satisfies the P9 exit gate;
4. the clean P9 PASS is reconciled into canonical GitHub/source continuity;
5. a separate explicit P10 owner authorization is issued.

This document grants **no** merge authority and **no** host/runtime, queue, LIVE-AUTH, P9 execution, P10, deployment, credential, permission, database, Cloudflare, systemd, Docker, network, rollback, cleanup, or production-mutation authority.

## Safety relationship to the existing Master Plan

The current `docs/AUTOMATION_MASTER_PLAN.md` already keeps P9 incomplete and P10 separately gated. This reconciliation narrows the current continuation further by resolving the incident question: the existing technical `DRY_RUN_READY` evidence does not complete P9; a clean repeat is mandatory before P10. Until this decision is merged and later integrated into any broader master-plan refresh, the stricter rule in this document and the latest `#236/#191` continuity governs the P9 incident continuation.
