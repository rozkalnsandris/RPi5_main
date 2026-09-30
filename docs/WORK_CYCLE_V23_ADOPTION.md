# FAST-LANE v2.3 adoption — RPi5_main

Status: source/governance consumer adapter for `ops-workflows#124`.

Canonical shared revision: `rozkalnsandris/ops-workflows@274d58f2d9d3cb86feded2751b8f9009a4501f6b`.

## Adopted capabilities

- `BOOTSTRAP_MANIFEST_V1` through `.github/agent-bootstrap.json`.
- START safe auto-continuation and compact terminal response semantics.
- `WRITE_PREFLIGHT_COMPACT_V1` through the existing GitHub API access adapter; no second local write-preflight framework.

Normal START selects one current lane and automatically performs immediately safe same-scope technical work. It stops only at a genuine owner gate, an external wait that cannot be advanced safely, fail-closed drift/error/ambiguity, or DONE. Repository-local owner gates remain authoritative.

## RPi5_main local stricter rules

`RPi5_main` is the runtime-owner repository. Its production-safety, protected-data, GitHub-first/RDC, explicit FAST merge, and exact LIVE authorization rules in `AGENTS.md` remain stricter and authoritative.

The bootstrap deployment profile is therefore `custom`. It is descriptive routing metadata only and grants no deployment or runtime authority.

## AUTO-RUN FULL normalized-state compatibility

The shared Slice D contract `AUTO_RUN_FULL_SINGLE_ISSUE_STATE_V2` is a singleton controller model with `maximum_active_runs=1`.

`RPi5_main` already has an accepted multi-lane FULL model:

- issue-local lane state is authoritative;
- up to four runnable source lanes may exist concurrently;
- controller issue `#295` is an aggregate reconciliation view;
- conflict keys serialize shared resources;
- LIVE remains globally exclusive.

For this rollout the normalized singleton state is therefore `BLOCKED_LOCAL_MULTI_LANE`, not silently forced into the repository. Existing/historical state is not rewritten and no second controller framework is introduced. A future shared multi-lane adapter contract is required before changing this state model.

## Authority

This adoption does not widen source, merge, LIVE, runtime, protected-data, permissions, credentials, retry, rollback, cleanup, Queue or deployment authority. Merge never implies LIVE.
