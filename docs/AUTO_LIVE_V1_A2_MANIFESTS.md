# Auto-Live v1 — A2 repository manifests

Status: **A2 SOURCE ONLY / INACTIVE**

Canonical roadmap: `RPi5_main#421`  
Shared policy: `rozkalnsandris/ops-workflows@f2aeb5152371a876268bb116bb98806cddbc8e15` → `policy/auto-live-v1.json`

## Purpose

A2 binds production-bearing repositories to explicit machine-readable Auto-Live manifests. A manifest is eligibility policy, not execution authority. This stage does not enable the deploy executor, install or change host services, mutate credentials or permissions, or deploy production.

Canonical A2 index:

- `ops/deploy/auto-live-manifests.json`

Current manifests:

- `ops/deploy/auto-live-manifests/dashboard-rpi5.json`
- `ops/deploy/auto-live-manifests/rozkalns-weather.json`

No manifest means no automatic live mutation.

## Required binding

Each manifest binds:

1. exact source repository and production target alias;
2. one existing static operation from `ops/deploy/executor-operations.json`;
3. full production-baseline → target range classification;
4. exact-target-SHA required CI evidence;
5. explicit Auto-Live eligibility classes;
6. baseline resolver identity;
7. deterministic health/postconditions;
8. rollback/retry/failure semantics;
9. sensitive exclusions.

Unknown or unmatched paths are `BLOCKED`, never silently `NO_DEPLOY` or `AUTO_DEPLOY_SAFE`.

## Dashboard boundary

`dashboard-rpi5.production-release.v1` is the only current static production-release operation already declared `AUTO_DEPLOY_SAFE`.

A2 deliberately narrows its automatic path eligibility to `apps/web/` changes. Server, agent, terminal and contract changes require manual rollout; workflow, `ops/`, and `tools/` changes are host/control-plane class. Mixed ranges take the highest-risk matching class. Any unmatched path is `BLOCKED`.

The manifest is still `INACTIVE_SOURCE_ONLY` with `automatic_mutation_enabled=false`. A later activation/canary remains a separate owner LIVE gate.

## Weather boundary

`rozkalns-weather.public-runtime-release.v1` remains a `STRICT` operation. A2 therefore declares no automatic-eligible class for this target.

Documentation/tests reconcile as `NO_DEPLOY`; application source remains `MANUAL_ROLLOUT_REQUIRED`; deployment/workflow/Docker/environment surfaces are `DB_HOST_APPLY_REQUIRED`; unmatched paths are `BLOCKED`.

The manifest does not authorize Docker, systemd, credentials, private coordinates, SQLite/backfill, Cloudflare/network, or production mutation.

## Failure and concurrency invariants

All A2 manifests inherit the shared Auto-Live v1 rules:

- classify the complete production baseline → target range;
- require exact target SHA CI success;
- serialize one mutation-capable deploy per target;
- preserve evidence and STOP on post-mutation error, drift or ambiguity;
- no automatic retry, cleanup, rollback or alternate mutation path after mutation starts;
- merge remains a reconciliation trigger, not blanket LIVE authority.

## A2 exit

A2 source work may reach Draft PR / CI / Ready only.

A2 does **not** authorize:

- merge;
- executor enablement;
- systemd/timer or other host mutation;
- credential/App permission changes;
- production deployment;
- database, Cloudflare or network mutation;
- A3 controller activation;
- A4 canary.
