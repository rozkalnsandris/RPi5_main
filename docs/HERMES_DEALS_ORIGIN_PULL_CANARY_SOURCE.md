# Hermes Deals origin-path pull canary — source contract

Status: **SOURCE CONTRACT / DORMANT OPERATION / GLOBALLY DISABLED / NOT HOST-EXECUTABLE**

Tracking:

- Hermes Deals migration: `rozkalnsandris/hermes-deals#384`
- merged inventory/architecture gate: `hermes-deals#787`
- shared executor roadmap: `RPi5_main#236`
- production-registry consumption gate: `RPi5_main#275`
- current genuine-canary waiting gate: `RPi5_main#276`

## Purpose

This source contract defines the first read-only Hermes Deals migration canary for the existing owner-authorized pull executor architecture. It does not create a second request protocol and it does not replace the current Hermes Deals self-hosted audit path.

The canary operation is `hermes-deals.origin-path-audit.v1`. It was introduced as a dormant reviewed fixture by `RPi5_main#247`. As of merged `RPi5_main#275`, the production executor registry now contains exactly that reviewed operation while the global gate remains `execution_enabled=false`.

This registry consumption is source-only. P8 deliberately validates only the top-level disabled registry gate and does not parse, normalize, select, dispatch, preflight or apply registry operation entries. The presence of the reviewed operation therefore does not make the canary host-executable or authorize a live run.

## Frozen cross-repository source identities

Hermes Deals reviewed baseline for this source contract:

- repository: `rozkalnsandris/hermes-deals`
- stable repository ID: `1317143994`
- reviewed main after `#787`: `2fbde52cc5b6661343dca3fd967d8112cb2bffbe`
- dispatcher source blob: `f9bfd02c6d36bb54d5380e1f0c99a0195e2ff4bc`
- installer source blob: `41f004420a0f5aed314aaefd796a54e14dbd17ea`
- probe source blob: `2362e8eb578a7279c38fe4ed2a7d1edd05df891a`

The reviewed main SHA is evidence for this audit, not permanent execution authority. A future live attempt must independently resolve the current source repository identity, exact authorized SHA, merged/reachable status and exact-SHA CI at execution time.

## Static operation contract

The reviewed production-registry entry remains deliberately fail-closed:

- authorization class: `STRICT`
- ordinary LIVE-ALL eligibility: `false`
- target alias: `hermes-deals-origin-path-audit`
- location class: `trusted-home-host`
- reviewed source selector: `tools/runner/origin-path-rpi5-audit-dispatcher.sh`
- rollback policy: `NONE`
- invocation budget: one `hermes-deals.read-only-audit-invocation`
- production DB, deploy/cutover, restart/configuration, parser/collector, runner and credential/permission changes are excluded.

Queue prose is not operation, command, path, argument or budget authority. The operation is selected only by exact registry selectors and the full queue contract remains cryptographically bound by the existing P4 normalizer.

Global `execution_enabled=false` remains authoritative. Merely matching this static operation entry cannot enable execution.

## Privilege boundary

The proposed executor poller remains the P5/P6 dedicated unprivileged service identity with `NoNewPrivileges=true`, no capabilities and no privileged command bridge.

The only payload allowed across the future unprivileged-to-privileged interface remains `rozkalns.deploy-dispatch-request.v1`: authorization repository identity, authorization issue identity and request UUID. It does not carry source SHA, operation ID, target, executable path, arguments or mutation budget.

Therefore this source contract does **not** grant the poller access to the existing Hermes Deals privileged dispatcher. A future privileged broker must independently re-fetch and revalidate LIVE-AUTH, queue/source/CI/baseline state and the static operation registry before it may invoke any project-specific boundary.

## Legacy canary path compatibility

The current Hermes Deals `origin-path-rpi5-audit` workflow remains unchanged. Its existing self-hosted audit job and root-owned dispatcher stay available until the replacement path has separate live activation and end-to-end evidence.

The current dispatcher is intentionally bound to its existing runner-owned evidence directory contract. This source contract does not weaken that allowlist, add a new caller, alter its installer, or add a new privilege rule. Host compatibility is therefore **not yet proven** for the pull executor and must be addressed only at the later live/broker gate.

## Adapter behavior

`HermesDealsOriginAuditAdapter` is validation-only:

- preflight verifies exact operation/source/target/rollback/budget/exclusion/dependency contracts;
- `execution_enabled` must remain false;
- `apply()` always fails closed;
- postconditions only describe the sanitized evidence contract and required false production-mutation flags;
- the adapter contains no command launcher or generic execution surface.

## Source acceptance evidence

The post-`RPi5_main#275` regression contract proves that:

1. the production registry matches the reviewed Hermes canary registry, contains exactly one `hermes-deals.origin-path-audit.v1` operation and remains globally execution-disabled;
2. the operation is `STRICT` and not ordinary-LIVE-ALL eligible;
3. the exact READY fixture can normalize from the production registry without enabling execution;
4. free-form queue prose cannot expand the static invocation budget;
5. an unreviewed entrypoint fails with `UNKNOWN_OPERATION`;
6. adapter preflight remains read-only/disabled and `apply()` remains fail-closed;
7. the privileged dispatch request rejects SHA/operation/command/path/argv fields;
8. P8 accepts the globally disabled registry without parsing or consuming its operation entries and remains mutation/result-writer disabled;
9. the expected Hermes Deals dispatcher/installer/probe source identities remain bound as dependencies;
10. source readiness is not reported as host readiness.

## Current P9 waiting gate

`RPi5_main#276` advances the canonical control-plane lane to **P9 GENUINE READ-ONLY CANARY — WAITING FOR REAL READY + OWNER DECISION**.

A genuine P9 attempt requires all of the following at execution time:

- a real open `[DEPLOY-QUEUE][READY]` item matching this exact static operation contract;
- a separate explicit owner decision;
- fresh queue and LIVE-AUTH validation;
- fresh source repository identity, merged/reachable SHA and exact-SHA CI evidence;
- fresh registration/baseline and privileged-boundary evidence.

Do not create or promote a dummy/placeholder READY item or LIVE-AUTH merely to exercise the executor. P9 success remains local `DRY_RUN_READY` with `PRODUCTION_MUTATION_STARTED=false`; P10 remains a separate mutation gate.

## Explicitly not authorized

This source contract itself does not authorize or perform:

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

Later roadmap phases may separately complete some infrastructure prerequisites under their own evidence and authorization gates. Nothing in this document carries that authority forward. A merge of this reconciliation changes documentation only and does not authorize a genuine P9 canary or any live mutation.
