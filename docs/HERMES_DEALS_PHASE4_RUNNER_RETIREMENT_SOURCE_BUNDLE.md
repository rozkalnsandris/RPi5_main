# Hermes Deals Phase 4 — residual runner retirement source bundle (#466)

Status: **SOURCE ONLY / LIVE DISABLED / RUNNER RETIREMENT NOT AUTHORIZED**

This document is the human-readable companion to
`ops/contracts/hermes-deals-phase4-runner-retirement-v1.json`.

## Purpose

Issue #466 freezes ten source-only jobs that move Phase 4 from the first proven
`origin-path-audit` replacement toward a complete capability-by-capability runner-retirement
decision. The bundle does not inspect or mutate RPi5 runtime state and does not infer current
runner registration from repository source.

The activation base is `RPi5_main@2672451d1f3ddc6cffcc70a3627c6b758db8abe0`.
The Hermes Deals activation dependency was
`c9ef2460d9361664f3afcf6fe95277a4a7f0df98`. During fresh execution reads Hermes Deals
advanced to `87eeb9a6dcfbd802158e42bc8501b5ad8629431f` by one direct docs-only project-progress
commit; the four executable workflow blobs below were re-read from that exact current main and
are bound by blob identity in the machine contract.

## Fresh residual paths

| Capability | Workflow | Runner label | Source result |
| --- | --- | --- | --- |
| origin path read-only audit | `.github/workflows/origin-path-rpi5-audit.yml` | `hermes-deals-audit` | existing proven `hermes-deals.origin-path-audit.v1` source contract |
| approved audit command | `.github/workflows/rpi5-audit-command.yml` | `hermes-deals-audit` | source contract for fixed operation IDs; LIVE later |
| source checkout sync | `.github/workflows/rpi-source-sync.yml` | `hermes-deals-audit` | source contract for exact merged/reachable SHA fast-forward; LIVE later |
| production release | `.github/workflows/deploy-main.yml` | `hermes-deals-release` | deploy-impact/Auto-Live source reconciliation; LIVE later |

No public/fork/comment/dispatch input is granted direct RPi5 command authority. Replacement
interfaces use immutable capability/operation IDs and preserve owner numeric identity,
merged/reachable SHA and exact-CI requirements.

## Ten job outcomes

1. **DONE** — exact residual runner-path inventory is frozen.
2. **DONE** — capability classes and mutation classes are frozen.
3. **NO_OP_ALREADY_RECONCILED** — origin-path audit already uses the reviewed static operation,
   adapter, helper provenance and privileged request boundary.
4. **SOURCE_READY_LIVE_LATER** — `runner-smoke` and `b15m2-v08` become distinct fixed source
   operation identities; no arbitrary audit command selector is introduced.
5. **SOURCE_READY_LIVE_LATER** — source-sync is modeled as one exact-SHA trusted checkout
   fast-forward capability, not generic Git/path authority.
6. **SOURCE_READY_LIVE_LATER** — production release is reconciled to full
   production-baseline-to-target deploy classification; only `AUTO_DEPLOY_SAFE` can be a future
   automatic candidate.
7. **NO_OP_ALREADY_RECONCILED** — issue #425 / PR #431 is authoritative for Netto. The stale
   #424 UID/GID-1000 model must not replace its dedicated `hermes-netto-audit` identity.
8. **DONE** — deterministic adversarial regressions cover untrusted events, wrong owner/SHA/CI,
   unknown or cross-capability operations and generic command/path/argv/env authority.
9. **SOURCE_READY_LIVE_LATER** — runner retirement is fail-closed behind replacement source,
   runtime wiring, genuine canary where required, fallback removal and a fresh final inventory.
10. **DONE** — AUTO-RUN FULL merge authority remains distinct from Auto-Live/LIVE authority;
    sensitive classes remain owner-required and post-mutation automatic retry/cleanup/rollback
    stays disabled.

## Netto supersession rule

`RPi5_main#425` / PR #431 is the authoritative source contract. It requires a dedicated non-login,
non-root, no-Docker `hermes-netto-audit` identity, empty supplementary groups, fixed process
surface and disabled execution/host/canary flags. Open historical #424 / PR #426 is superseded for
identity semantics and must not regress the dedicated-identity boundary.

## Runner-retirement rule

A runner label is never retirement-eligible merely because a source replacement exists.
Eligibility requires **all** capabilities that depend on the label to have:

- replacement source ready;
- required runtime wiring proven by separately authorized host evidence;
- genuine canary/e2e proof where required;
- no remaining legacy fallback dependency;
- a fresh final runner/capability inventory.

Unknown or missing evidence evaluates to `NOT_ELIGIBLE`. The validator can compute source
eligibility but never authorizes deregistration or settings mutation.

## Auto-Live / AUTO-RUN FULL boundary

The bundle defines a source candidate policy for Hermes Deals production release but deliberately
does not index an active Auto-Live manifest and does not register a new live operation.

Future automatic eligibility requires the complete production baseline -> target range to classify
`AUTO_DEPLOY_SAFE`, exact target-SHA CI to pass, a reviewed static operation to be registered, a
repository manifest to be separately activated, stable target serialization, and the exact
project-specific helper/baseline contract to be proven.

`MANUAL_ROLLOUT_REQUIRED`, `DB_HOST_APPLY_REQUIRED`, unknown paths and ambiguous evidence remain
owner-required or blocked. `AUTO-RUN FULL` merge authority is not runtime/LIVE authority.

## Explicit non-authority

This bundle does **not** authorize or perform:

- runner registration/deregistration or repository settings writes;
- systemd/service/socket, user/group/ACL/sudoers or credential/App changes;
- Docker/container/network/Cloudflare mutation;
- source-sync execution;
- helper/audit invocation;
- production deployment;
- DB/Review/publication/application-data writes;
- synthetic READY/LIVE-AUTH/canary/production evidence;
- runtime-state inference from source.

After #466 reaches a terminal merged-source receipt, successor bundle #467 may be activated only
from freshly re-read current state. Any LIVE or runner-retirement step remains a separate exact
owner gate.
