# Hermes Deals Phase 4 canary readiness + runner-retirement closure source bundle

Tracking: `RPi5_main#467`  
Predecessor: `RPi5_main#466` / PR `#468`

## Scope

This bundle is source-only. It converts the terminal #466 residuals into deterministic canary/preflight/retirement-closure contracts without asserting host state or creating READY, LIVE-AUTH, canary, runner-retirement, or production evidence.

Fresh source anchors used by the contract:

- `RPi5_main` activation/predecessor merge: `9ce80d2dddec084a5c52f3de7f52bc990e1de0f8`
- `hermes-deals/main`: `87eeb9a6dcfbd802158e42bc8501b5ad8629431f`
- Phase 4 work item: `HERMES_POSTCANARY_INCREMENTAL_CAPABILITY_MIGRATION_SOURCE`

## Source-path drift resolution

The old `tools/install-hermes-deals-audit-runner.sh` path is not provenance authority for current Hermes Deals source. The current reviewed source uses capability-specific paths under `tools/runner/`.

The source contract binds the exact current helper/installer blobs for origin-path audit, approved audit command, source sync, and production release. The stale path may still appear as a workflow path-watch entry. That does not make it a current helper or provenance anchor.

## Job results

| Job | Result | Source outcome |
| --- | --- | --- |
| 1 | `DONE` | #466 terminal outcome is frozen as the successor input. |
| 2 | `DONE` | Residual capability/workflow/helper identities are exact-SHA/blob bound. |
| 3 | `SOURCE_READY_LIVE_LATER` | Lowest-risk `runner-smoke` canary package is defined; no canary or authority is created. |
| 4 | `SOURCE_READY_LIVE_LATER` | Source-sync readiness is fixed to exact merged/reachable SHA fast-forward semantics with generic Git/path authority forbidden. |
| 5 | `SOURCE_READY_LIVE_LATER` | Production-release readiness preserves full baseline-to-target classification; only future `AUTO_DEPLOY_SAFE` application paths can qualify. |
| 6 | `NO_OP_ALREADY_RECONCILED` | #425 remains authoritative over stale #424: dedicated non-login/non-root/no-Docker identity, empty supplementary groups. |
| 7 | `SOURCE_READY_LIVE_LATER` | One metadata-only read-only preflight operator is defined per residual capability; helper execution/credential reads/host writes remain disabled. |
| 8 | `DONE` | Machine-readable runner-retirement graph and fail-closed evaluator deny unknown/missing evidence. |
| 9 | `SOURCE_READY_LIVE_LATER` | Auto-Live A5 source reconciliation binds exact SHA/CI, full-range classification, stable per-target concurrency and helper identity while mutation stays disabled. |
| 10 | `DONE` | Phase 4 source closure schema is defined; source evidence alone cannot close Phase 4. |

## Canary boundary

The selected lowest-risk residual audit is `hermes-deals.runner-smoke-audit.v1`.

A later genuine canary must still prove a runner-independent capability-specific helper and registration identity before LIVE. Its normalized authority surface remains identity-only; caller-selected command, path, argv or environment authority is forbidden. Expected evidence is bounded/sanitized and explicitly carries `production_mutation_started=false`.

No READY/LIVE-AUTH record or genuine canary is created by this bundle.

## Runtime preflight boundary

Preflight operators are source models only. They can evaluate fixed reviewed metadata: exact Hermes source SHA, exact-SHA CI result, fixed helper path/blob identity, fixed registration identity, and fixed execution identity.

They cannot invoke helpers, read protected credentials, or write host state.

## Runner-retirement boundary

`hermes-deals-audit` remains dependent on origin-path audit, approved audit command, and source sync. `hermes-deals-release` remains dependent on production release.

Each capability requires all of:

1. replacement source ready;
2. runtime wiring proven;
3. genuine canary/e2e evidence where required;
4. legacy fallback dependency removed;
5. fresh final runner inventory.

Missing or unknown evidence returns `NOT_ELIGIBLE`. Even complete evidence only opens a separate owner retirement gate; it does not authorize deregistration.

## Auto-Live A5 boundary

Only `AUTO_DEPLOY_SAFE` production-release ranges can become future automatic candidates. `source_sync` is owner-required, and read-only audits are `NO_DEPLOY`.

This bundle does not index a new production manifest, register a new production operation, enable executor mutation, or grant LIVE authority. `AUTO-RUN FULL`/merge authority remains distinct from LIVE authority.

## Phase 4 closure

Phase 4 remains `NOT_CLOSED_LIVE_EVIDENCE_REQUIRED`.

A final owner closure decision requires a fresh final capability inventory and either `RUNNER_COUNT_TARGET=0` or a narrowly justified residual runner explicitly accepted by the owner.

Runner deregistration/settings mutation, host runner service retirement, runtime wiring and genuine canaries remain separate future owner/LIVE gates.
