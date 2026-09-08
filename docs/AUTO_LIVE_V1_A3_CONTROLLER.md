# Auto-Live v1 A3 — read-only controller

**Status:** A3 SOURCE ONLY / MUTATION DISABLED
**Roadmap:** `RPi5_main#421`
**Machine contract:** `ops/deploy/auto-live-controller-v1.json`
**Shared policy:** `rozkalnsandris/ops-workflows@f2aeb5152371a876268bb116bb98806cddbc8e15`

## Purpose

A3 adds the deterministic read-only Auto-Live decision layer to the existing trusted
RPi5 deploy-executor control plane. It does not install or activate a new runtime.

The controller consumes an explicitly trusted production baseline SHA, reads the
current GitHub source state, verifies the exact target SHA and required CI, classifies
the complete production-baseline-to-target path range, and returns one of:

- `NO_DEPLOY`
- `AUTO_DEPLOY_SAFE`
- `OWNER_REQUIRED`
- `BLOCKED`

Every A3 result remains non-mutating, including `AUTO_DEPLOY_SAFE`.

## Inputs and authority

GitHub remains canonical for repository identity, current `main`, source reachability,
changed source paths and Actions evidence.

The production baseline is not inferred from GitHub `main`, chat history, or a previous
Auto-Live decision. A caller must supply a freshly trusted production baseline from the
reviewed target-specific resolver bound by the A2 manifest and static operation.

A3 verifies that the A2 manifest, immutable shared-policy SHA, target alias, static
operation ID and baseline resolver still agree before any GitHub reconciliation read.

## Full-range classification

Classification is always over the production baseline -> exact target SHA range.
Latest-commit-only classification is forbidden.

Each compare-file entry must carry one of GitHub's documented statuses: `added`,
`removed`, `modified`, or `renamed`. Added, removed, and modified entries classify the
reported `filename`. A renamed entry classifies both `previous_filename` and `filename`
so moving a file out of a sensitive path cannot lower the range classification. Missing
rename provenance, an unknown status, or an unmatched path is `BLOCKED`. Mixed ranges
use the manifest precedence.

The GitHub compare file list is treated as bounded evidence. If the response is absent,
not `ahead`, empty, malformed, or reaches the configured 300-file hard limit, A3 returns
`BLOCKED` instead of assuming that the visible subset is complete.

## Exact target and CI

The exact target SHA must be current `main` or an ancestor reachable from current
`main`. A3 queries workflow runs with GitHub's documented server-side `branch=main`,
`event=push`, exact `head_sha`, and `status=completed` filters, then requires the
manifest's exact workflow path/name and a successful required gate job for that same
target SHA. Client-side identity checks remain in place as defense in depth.

Missing, truncated, malformed or unsuccessful CI evidence is `BLOCKED`.

## Decision mapping

`NO_DEPLOY` remains reconciliation-only.

`MANUAL_ROLLOUT_REQUIRED` and `DB_HOST_APPLY_REQUIRED` map to `OWNER_REQUIRED`.

A manifest-classified `AUTO_DEPLOY_SAFE` range is reported as `AUTO_DEPLOY_SAFE` only
when its static operation is also the reviewed ordinary Auto-Live-eligible operation.
This is a decision receipt only in A3; it is not live authority.

Unknown, ambiguous, incomplete or contract-mismatched evidence maps to `BLOCKED`.

## Mutation boundary

A3 validates the complete declared mutation-key set and keeps all of the following
false; a missing, extra, or true mutation flag is a contract failure:

- `execution_enabled`
- `automatic_mutation_allowed`
- `mutation_dispatch_enabled`
- `production_mutation_started`
- adapter/apply invocation
- systemd or timer mutation
- credential or permission mutation
- production deployment

The A2 manifests remain `INACTIVE_SOURCE_ONLY`. The global executor registry remains
execution-disabled. No adapter `apply`, dispatch bridge, systemd wiring, credential
change, host mutation or production action is introduced by A3.

Remote Desktop Commander remains bootstrap/recovery/owner-maintenance transport only
and is not part of the steady-state decision authority.

## A3 source gate

A3 source completion means the controller source, machine contract, regression tests,
documentation and GitHub CI have converged to a Ready PR.

It does **not** authorize:

- installing or enabling the controller on RPi5;
- changing `rozkalns-deploy-executor.service` or `.timer`;
- enabling `ops/deploy/executor-operations.json`;
- activating an A2 repository manifest;
- invoking a production adapter;
- deploying Dashboard, Weather, or any other target;
- changing GitHub App permissions, credentials, secrets or repository settings.

Those remain later A4/LIVE or separately scoped owner gates.
