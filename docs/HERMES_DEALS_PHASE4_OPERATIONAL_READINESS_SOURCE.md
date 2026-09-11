# Hermes Deals Phase 4 operational readiness source bundle

Issue: `RPi5_main#470`

This source gate advances the Hermes Deals persistent-runner migration from the #467 source-readiness model toward one capability-specific operational sequence. It does not prove or change current RPi5 runtime state.

## Fresh source anchors

- RPi5_main activation source: `7f0016b9c68f128141815652bf1c76e764cf88b4`
- predecessor #467 terminal receipt: `5637924032`
- predecessor merge: `7f0016b9c68f128141815652bf1c76e764cf88b4`
- Hermes Deals source snapshot: `8015d6175b2b3c260fdb26546021bb17dcc5f4fb`
- Phase 4 lane: `HERMES_POSTCANARY_INCREMENTAL_CAPABILITY_MIGRATION_SOURCE`

The Hermes Deals delta after the #467 snapshot is ALDI weekly-shadow work and does not change the four residual capability identities frozen by this bundle.

## Ten source outcomes

1. predecessor terminal state ingested — `DONE`;
2. residual capability identities refreshed — `DONE`;
3. next lowest-risk audit target selected — `DONE`;
4. selected audit host-wiring source contract — `SOURCE_READY_LIVE_LATER`;
5. read-only preflight/post-install evaluator — `DONE`;
6. genuine-canary authorization/evidence package — `SOURCE_READY_LIVE_LATER`;
7. source-sync operational-readiness contract — `SOURCE_READY_LIVE_LATER`;
8. production-release Auto-Live A5 source descriptor — `SOURCE_READY_LIVE_LATER`;
9. runtime-evidence ledger and retirement validator — `DONE`;
10. deterministic operational handoff — `DONE`.

## Selected next audit capability

The selected capability remains the `runner-smoke` subset of `approved_audit_command` because it is read-only and can be represented by a narrow identity-only future operation.

The existing Hermes Deals implementation is deliberately **not** treated as the replacement runtime. The legacy path is still coupled to the persistent `github-runner` and root sudo dispatcher. #470 records that fact and forbids reusing that runner-coupled path as evidence that the new capability is installed or LIVE-ready.

The future source contract instead requires:

- operation ID `hermes-deals.runner-smoke-audit.v1`;
- target alias `hermes-deals-runner-smoke-audit`;
- a dedicated `hermes-deals-audit-canary` non-login, non-root, no-Docker execution identity;
- no supplementary groups;
- only `authorization_issue_number` across the privileged boundary;
- fixed helper and registration identities;
- root-owned reviewed install metadata with no-overwrite and no-follow semantics;
- no caller-selected command, path, argv, environment, uid/gid or generic shell authority.

No account, file, permission, helper, dispatcher, service or runner is installed or changed by this source gate.

## Read-only preflight

`ops/lib/deploy_executor/hermes_deals_phase4_operational_readiness.py` evaluates a sanitized metadata record only. It verifies exact source/CI and fixed helper, registration, execution-identity, ownership/mode and inert-state evidence. It does not read protected credentials, invoke the helper, perform host writes or consume a LIVE authorization.

A missing or mismatching field produces `BLOCKED`.

## Genuine canary package

The future canary package inherits the canonical `RPi5_main#236` authorization protocol. It requires owner server identity, exact source SHA and CI, canonical body hashing and immediate body re-fetch, TTL validation, durable one-shot replay protection and consume-before-helper semantics.

The source package creates neither READY nor LIVE-AUTH. It fabricates no request ID or canary evidence. A future genuine canary must use new current-state records and may not reuse historical authorizations.

## Source-sync

`hermes-deals.source-sync.v1` remains separately LIVE-gated. The only allowed future mutation is a fast-forward to one exact merged/reachable SHA after exact-SHA CI. Generic checkout path and Git subcommand authority remain forbidden. #470 does not fetch, merge or change a checkout.

## Auto-Live A5

`ops/deploy/hermes-deals-auto-live-a5-source-bridge.json` is an inactive source descriptor, not an activated manifest or executor operation.

It requires the complete production-baseline-to-target range to be evaluated by the reviewed Hermes Deals deploy-impact classifier. Only `AUTO_DEPLOY_SAFE` may become a future automatic candidate. Manual, DB/host-sensitive and unknown states remain owner-required or blocked.

The descriptor is intentionally not inserted into the global executor operation registry or Auto-Live manifest index in this gate. `automatic_mutation_enabled=false` and all mutation flags remain false. A later reviewed source integration must still preserve a separate first activation/LIVE gate.

## Runner retirement

The machine contract defines evidence slots for source replacement, host wiring, installed identity verification, genuine canary/e2e proof, fallback dependency removal and a fresh final runner inventory.

Missing or unknown evidence is `NOT_ELIGIBLE`. Historical success for the origin-path canary is retained only as historical evidence; it does not assert current host wiring or current installed identity. #470 never deregisters a runner or changes repository settings.

## Ordered future owner gates

After this source bundle is merged and exact-main source checks pass, the intended sequence is:

1. a separate exact LIVE authorization for the selected audit capability host install/wiring;
2. read-only post-install identity verification;
3. a new genuine READY record plus a new owner-authored LIVE-AUTH for one runner-smoke canary;
4. incremental source/LIVE gates for the remaining capabilities;
5. only after all replacement evidence and a fresh runner inventory, a separate exact runner-retirement/settings authorization.

Merge of #470 is never LIVE authority. Phase 4 remains `NOT_CLOSED_LIVE_EVIDENCE_REQUIRED` until real current runtime evidence satisfies the merged contract.
