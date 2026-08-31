# P9 freshness handoff repair — 2026-08-31

Status: SOURCE REPAIR / PRE-MERGE
Roadmap: `RPi5_main#236`
Canonical handoff: `RPi5_main#191`
Related incident decision: `docs/P9_INCIDENT_EXIT_GATE_RECONCILIATION_2026-08-31.md`

## Decision

The fixed P9 baseline freshness limit remains **300 seconds** and the LIVE-AUTH TTL remains **600 seconds**. This repair does not widen either security window.

A successful Control baseline CLI result must now expose the exact trusted-server-time handoff window and must not publish/return `PASS` unless at least **180 seconds** of the existing 300-second baseline lifetime remain after all expensive collection work has finished.

`P9_EXIT_GATE=NOT_MET`

`CLEAN_P9_REPEAT_REQUIRED=true`

`P10_BLOCKED=true`

## 2026-08-31 LIVE-AUTH #6 incident

The owner-authorized clean-repeat attempt produced the following public-safe sequence:

1. one fresh Control baseline command returned `P9_CONTROL_BASELINE=PASS`, source `f04601dfd47e5691c875c0935b36ff101680f4dd`, evidence SHA-256 `ecbd519b2359f7ddaefe6a280dcbf3a6efad6c29169f33523b7ddc515bbee2da`, `p9_executed=false`, `state_store_touched=false`, and `production_mutation_started=false`;
2. owner-authored `deploy-authorizations#6` was created with `performed_via_github_app=null`, exact owner identity, exact queue/source/operation/baseline binding, and the existing 600-second LIVE-AUTH TTL contract;
3. exactly one genuine P9 CLI invocation used the correctly formed integer argument `--issue-number 6`;
4. the invocation failed closed with `P9EvidenceError: Control baseline evidence is stale or from the future`;
5. no retry, cleanup, rollback, alternate execution, P10, or production mutation followed.

Source inspection proves the stale-baseline exception occurs in P9 `_preflight()` before `LazyP9StateStore` is constructed. The failed invocation therefore did not enter the P9 StateStore lifecycle and did not enable mutation dispatch or result writing. LIVE-AUTH #6 is nevertheless a consumed historical authorization envelope and is not reusable.

## Root cause

The evidence freshness validator correctly compares the baseline `observed_at` to trusted GitHub REST response time and rejects an age outside `0..300` seconds. The RPi5 local wall clock is not the authority for this check.

The operational defect was that the baseline CLI's visible `PASS` did not reveal when the 300-second evidence window actually began. `observed_at` is captured from the GitHub server `Date` associated with the pinned canary-run observation. After that timestamp the collector still performs further GitHub work, two fixed D1 `SELECT` reads, validation, and publication. Manual LIVE-AUTH creation and post-creation provenance checking then consumed additional time.

The result was a truthful baseline at collection time but an operator workflow that could unknowingly hand a nearly expired baseline to P9.

## Source repair

The Control baseline CLI now:

- preserves `MAX_EVIDENCE_AGE_SECONDS=300` unchanged;
- reuses the already narrowed/cached Control source read client and performs one final authoritative Control repository GET after collection work completes;
- derives the handoff age only from timezone-aware GitHub server time;
- rejects future or already-stale baseline evidence before publication;
- requires at least `180` seconds of remaining freshness before replacing the trusted baseline or emitting `PASS`;
- exposes `observed_at`, `expires_at`, `remaining_freshness_seconds`, and `minimum_handoff_freshness_seconds` in the public-safe `PASS` JSON;
- leaves the persisted baseline evidence schema unchanged;
- leaves the LIVE-AUTH 600-second TTL unchanged.

The 180-second handoff requirement is not a new evidence TTL. It is a stricter publication/operability floor inside the existing 300-second security window so a displayed `PASS` means there is a bounded, visible opportunity to complete the owner handoff.

## Required operator order for a future clean P9

All non-live work must be completed before producing the freshness-bounded baseline:

1. fresh-read `RPi5_main` rules/current main/exact-main CI and canonical #191/#236 continuity;
2. fresh-read `ops-workflows#27`, exact Control source/current main/CI, operation registry/interface bindings, authorization-repository posture, and prepare the exact owner-authored LIVE-AUTH body/request id;
3. only then enter a new separately explicit STRICT LIVE envelope and execute exactly one fresh baseline command;
4. accept baseline `PASS` only when the reported `remaining_freshness_seconds` is at least the reported minimum (currently 180 seconds);
5. immediately create one new owner-authored LIVE-AUTH through the owner's GitHub session;
6. perform exactly the bounded read-only provenance/TTL/body/queue/source validation required for that issue;
7. execute exactly one correctly formed P9 one-shot with the integer issue number;
8. any error after the first authorized protected/live operation => STOP with no retry/cleanup/rollback/alternate path unless a future owner envelope explicitly authorizes it.

No chat estimate of baseline age may substitute for the CLI's trusted-server-time fields or the P9 preflight's independent freshness validation.

## Safety boundary

This source repair performs and authorizes no host/runtime mutation, baseline collection, D1 request, credential or permission change, queue/LIVE-AUTH mutation, P9 execution, P10, deployment, rollback, cleanup, or production mutation. A future source merge would still not install this code on the RPi5 and would not authorize a clean P9 retry.
