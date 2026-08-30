# Hermes Deals origin-path pull canary — historical source contract

Status: **HISTORICAL DORMANT OPERATION / NO LONGER PRODUCTION-REGISTRY SELECTED / NOT HOST-EXECUTABLE**

Tracking:

- Hermes Deals migration: `rozkalnsandris/hermes-deals#384`
- merged inventory/architecture gate: `hermes-deals#787`
- shared executor roadmap: `RPi5_main#236`
- historical production-registry consumption gate: `RPi5_main#275`
- historical genuine-canary waiting gate: `RPi5_main#276`

## Current routing notice

On 2026-08-30 the owner redirected the first P9 genuine read-only canary target from Hermes Deals to the Rozkalns Control post-canary read-only reconciliation path. The production executor registry therefore no longer selects `hermes-deals.origin-path-audit.v1` as the active P9 operation. The reviewed Hermes adapter and fixtures remain source-controlled as historical regression evidence only.

This change does not activate either operation. Global `execution_enabled=false` remains authoritative, no real READY or LIVE-AUTH is created by source reconciliation, and P9 remains incapable of calling adapter `apply()`, a dispatcher, a workflow trigger or a production mutation surface.

The current selected P9 source contract is documented in `docs/CONTROL_CENTER_POSTCANARY_P9_SOURCE.md`.

## Historical purpose

This source contract originally defined the first read-only Hermes Deals migration canary for the existing owner-authorized pull executor architecture. It did not create a second request protocol and did not replace the current Hermes Deals self-hosted audit path.

The canary operation is `hermes-deals.origin-path-audit.v1`. It was introduced as a dormant reviewed fixture by `RPi5_main#247` and was consumed into the production registry by `RPi5_main#275` while the global gate remained `execution_enabled=false`. After the 2026-08-30 owner routing decision, the production registry moved to the Control Center operation while this Hermes contract remained dormant historical evidence.

## Frozen cross-repository source identities

Hermes Deals reviewed baseline for this historical source contract:

- repository: `rozkalnsandris/hermes-deals`
- stable repository ID: `1317143994`
- reviewed main after `#787`: `2fbde52cc5b6661343dca3fd967d8112cb2bffbe`
- dispatcher source blob: `f9bfd02c6d36bb54d5380e1f0c99a0195e2ff4bc`
- installer source blob: `41f004420a0f5aed314aaefd796a54e14dbd17ea`
- probe source blob: `2362e8eb578a7279c38fe4ed2a7d1edd05df891a`

These identities remain evidence for the historical review, not permanent execution authority. Any future proposal to restore Hermes as a live candidate must independently resolve current source identity, exact authorized SHA, merged/reachable status, exact-SHA CI and a new owner routing decision.

## Historical static operation contract

The reviewed historical fixture remains deliberately fail-closed:

- authorization class: `STRICT`
- ordinary LIVE-ALL eligibility: `false`
- target alias: `hermes-deals-origin-path-audit`
- location class: `trusted-home-host`
- reviewed source selector: `tools/runner/origin-path-rpi5-audit-dispatcher.sh`
- rollback policy: `NONE`
- invocation budget: one `hermes-deals.read-only-audit-invocation`
- production DB, deploy/cutover, restart/configuration, parser/collector, runner and credential/permission changes are excluded.

Queue prose is not operation, command, path, argument or budget authority. The historical fixture can be normalized only against its historical reviewed registry fixture; it is no longer accepted by the current production executor registry.

## Privilege boundary

The proposed executor poller remains the P5/P6 dedicated unprivileged service identity with `NoNewPrivileges=true`, no capabilities and no privileged command bridge.

The only payload allowed across the future unprivileged-to-privileged interface remains `rozkalns.deploy-dispatch-request.v1`: authorization repository identity, authorization issue identity and request UUID. It does not carry source SHA, operation ID, target, executable path, arguments or mutation budget.

This historical contract therefore grants no access to the Hermes Deals privileged dispatcher. A future privileged broker would still require independent re-fetch and revalidation of LIVE-AUTH, queue/source/CI/baseline state and a currently selected static operation.

## Legacy canary path compatibility

The Hermes Deals `origin-path-rpi5-audit` workflow remains outside this source-only routing change. Its self-hosted audit job and root-owned dispatcher are not modified by switching the P9 source contract to Control Center.

The dispatcher remains bound to its existing runner-owned evidence directory contract. This document does not weaken that allowlist, add a caller, alter its installer or add a privilege rule.

## Adapter behavior

`HermesDealsOriginAuditAdapter` remains validation-only historical evidence:

- preflight verifies exact operation/source/target/rollback/budget/exclusion/dependency contracts;
- `execution_enabled` must remain false;
- `apply()` always fails closed;
- postconditions only describe the sanitized evidence contract and required false production-mutation flags;
- the adapter contains no command launcher or generic execution surface.

## Historical regression evidence

The retained regression contract now proves that:

1. the historical Hermes registry fixture remains globally execution-disabled and `STRICT`;
2. the current production registry does **not** select the Hermes operation;
3. the exact historical READY fixture still normalizes only against the historical reviewed fixture without enabling execution;
4. free-form queue prose cannot expand the static invocation budget;
5. an unreviewed entrypoint fails with `UNKNOWN_OPERATION`;
6. adapter preflight remains read-only/disabled and `apply()` remains fail-closed;
7. the privileged dispatch request rejects SHA/operation/command/path/argv fields;
8. the expected Hermes Deals dispatcher/installer/probe source identities remain bound as historical dependencies;
9. source evidence does not claim host readiness.

## Current P9 gate

This Hermes document no longer selects the next P9 attempt. The current P9 operation and exact waiting conditions are defined by `docs/CONTROL_CENTER_POSTCANARY_P9_SOURCE.md` plus the current production registry and canonical roadmap.

Do not create or promote a dummy/placeholder READY item or LIVE-AUTH merely to exercise either operation. P9 success remains local `DRY_RUN_READY` with `PRODUCTION_MUTATION_STARTED=false`; P10 remains a separate mutation gate.

## Explicitly not authorized

This historical source contract itself does not authorize or perform:

- READY or LIVE-AUTH creation/promotion;
- any GitHub App, authorization-surface, credential or permission change;
- executor or privileged-broker installation/activation change;
- systemd, privilege-rule, package or host mutation;
- Hermes Deals runner registration/deregistration;
- production deploy/cutover;
- DB/Review/publication writes;
- parser/collector changes;
- Cloudflare mutation;
- modification of the existing Hermes Deals origin audit dispatcher/installer/workflow.

Nothing in this document carries historical authorization forward.
