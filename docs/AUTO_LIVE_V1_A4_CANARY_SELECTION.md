# Auto-Live v1 A4 — deterministic first-canary discovery

**Status:** `A4_DISCOVERY_READY_NO_CANARY_SELECTED` / LIVE DISABLED
**Roadmap:** `RPi5_main#421`
**Implementation:** `RPi5_main#459`
**State contract:** `ops/deploy/auto-live-a4-canary-selection.json`
**Discovery contract:** `ops/deploy/auto-live-a4-candidate-discovery.json`

## Purpose

A4 now has a deterministic source-side discovery engine for finding a real first Auto-Live canary candidate from already-declared A2 manifests. Discovery does not activate a manifest, invoke an adapter, mutate production, or create LIVE authority.

A0-A3 remain source-complete and mutation-disabled. The global executor registry remains `execution_enabled=false`.

## Durable state, not volatile SHA

The canonical A4 durable state is `A4_DISCOVERY_READY_NO_CANARY_SELECTED`.

No candidate repository SHA is stored as the canonical A4 current state. Candidate repository `main` SHAs and exact-SHA CI are fresh point-in-time evaluation evidence only. A normal Dashboard or Weather merge therefore does not require an `RPi5_main` continuity PR by itself.

Continuity changes only when durable A4 policy/state changes: candidate eligibility policy, discovery contract, selected canary, activation state, or equivalent reviewed control-plane semantics.

## Candidate set

The discovery engine accepts candidates only from `ops/deploy/auto-live-manifests.json`. It does not accept caller-supplied repositories, targets, manifest paths, operation IDs, commands, argv, environment, or mutation classes.

Each indexed manifest must still pass the existing A3 source-contract validation against:

- its exact source repository and target alias;
- its static operation in `ops/deploy/executor-operations.json`;
- `ORDERED_PATH_RULES_V1` full-range classification;
- exact-target CI requirements;
- deterministic health/postconditions;
- sensitive exclusions and fail-closed failure policy.

Dashboard is currently the only manifest that declares `AUTO_DEPLOY_SAFE` eligibility. Weather declares no automatic-eligible class and is therefore deterministically `NO_ELIGIBLE_CANARY` without requiring source or LIVE reads for candidate qualification.

## Source-first rejection

For an automatic-eligible candidate, discovery freshly reads repository `main` and exact-target CI, then classifies the current tip commit before asking for any production baseline.

If the current tip itself contains `MANUAL_ROLLOUT_REQUIRED` or `DB_HOST_APPLY_REQUIRED`, the target is `OWNER_REQUIRED` without a LIVE baseline read. That is safe because a production baseline equal to target would make the candidate a no-op, while any ancestor baseline-to-target range necessarily contains that higher-risk tip.

Unknown paths, incomplete compare evidence, missing exact-target CI, manifest drift, or static-operation drift return `BLOCKED`.

## Fresh production baseline boundary

A source-safe tip does **not** prove that the complete production-baseline-to-target range is safe. Discovery therefore returns `NEEDS_FRESH_LIVE_PREFLIGHT` until a separately obtained trusted read-only baseline evidence object is supplied.

Accepted baseline evidence is narrowly bound by schema `rozkalns.auto-live-production-baseline-evidence.v1` to:

- `TRUSTED_RPI5_READ_ONLY_PREFLIGHT` as evidence source;
- exact source repository and target alias;
- exact baseline resolver ID;
- the exact freshly evaluated target SHA;
- one exact production baseline SHA;
- explicit `trusted=true` and `fresh=true` producer assertions.

Repository source, historical evidence, chat history, or a candidate `main` SHA never infer current production state. Missing evidence yields `NEEDS_FRESH_LIVE_PREFLIGHT`; stale, untrusted, malformed, or target-mismatched evidence yields `BLOCKED`.

## Full-range qualification

With valid fresh baseline evidence, the existing A3 classifier evaluates the complete production-baseline-to-target range:

- `AUTO_DEPLOY_SAFE` -> `ELIGIBLE_CANARY`;
- `NO_DEPLOY` or already-current -> `NO_ELIGIBLE_CANARY`;
- `MANUAL_ROLLOUT_REQUIRED` / `DB_HOST_APPLY_REQUIRED` -> `OWNER_REQUIRED`;
- unknown/incomplete evidence -> `BLOCKED`.

If multiple candidates are fully eligible, selection uses stable `target_alias` then `manifest_path` ordering. The tie-break chooses only among already-proven `ELIGIBLE_CANARY` candidates and never widens eligibility.

## Current discovery decisions

The durable decision vocabulary is:

`ELIGIBLE_CANARY`, `NO_ELIGIBLE_CANARY`, `NEEDS_FRESH_LIVE_PREFLIGHT`, `OWNER_REQUIRED`, `BLOCKED`.

These are recomputed from fresh evidence on every evaluation. The repository does not persist a volatile candidate SHA as current continuity state.

## Historical evidence

The earlier 2026-09-09/10 Dashboard source and production SHAs remain preserved under `historical_evidence` in the state contract. They prove prior fail-closed decisions only. They are neither current source/runtime truth nor reusable LIVE authority.

## Mutation boundary

All activation and mutation surfaces remain disabled:

- executor execution disabled;
- manifest activation disabled;
- automatic mutation disabled;
- mutation dispatch disabled;
- adapter apply invocation disabled;
- systemd/timer mutation disabled;
- credential/permission mutation disabled;
- production deployment disabled;
- `production_mutation_started=false`.

A future `ELIGIBLE_CANARY` decision is still selection evidence only. First activation/canary remains a separate bounded owner LIVE gate with fresh host provenance and exact target binding. LIVE authorization alone cannot override source classification.
