# Hermes Deals origin-path pull canary — source contract

Status: **SOURCE ONLY / DORMANT / NOT HOST-EXECUTABLE**

Tracking:

- Hermes Deals migration: `rozkalnsandris/hermes-deals#384`
- merged inventory/architecture gate: `hermes-deals#787`
- shared executor roadmap: `RPi5_main#236`

## Purpose

This source slice prepares the first read-only Hermes Deals migration canary for the existing owner-authorized pull executor architecture. It does not create a second request protocol and it does not replace the current Hermes Deals self-hosted audit path.

The canary operation is `hermes-deals.origin-path-audit.v1`. It is present only in a test/audit registry fixture. The production executor registry remains exactly:

```json
{
  "schema_version": 1,
  "execution_enabled": false,
  "operations": []
}
```

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

The dormant fixture is deliberately fail-closed:

- authorization class: `STRICT`
- ordinary LIVE-ALL eligibility: `false`
- target alias: `hermes-deals-origin-path-audit`
- location class: `trusted-home-host`
- reviewed source selector: `tools/runner/origin-path-rpi5-audit-dispatcher.sh`
- rollback policy: `NONE`
- invocation budget: one `hermes-deals.read-only-audit-invocation`
- production DB, deploy/cutover, restart/configuration, parser/collector, runner and credential/permission changes are excluded.

Queue prose is not operation, command, path, argument or budget authority. The operation is selected only by exact registry selectors and the full queue contract remains cryptographically bound by the existing P4 normalizer.

## Privilege boundary

The proposed executor poller remains the P5/P6 dedicated unprivileged service identity with `NoNewPrivileges=true`, no capabilities and no privileged command bridge.

The only payload allowed across the future unprivileged-to-privileged interface remains `rozkalns.deploy-dispatch-request.v1`: authorization repository identity, authorization issue identity and request UUID. It does not carry source SHA, operation ID, target, executable path, arguments or mutation budget.

Therefore this source slice does **not** grant the poller access to the existing Hermes Deals privileged dispatcher. A future privileged broker must independently re-fetch and revalidate LIVE-AUTH, queue/source/CI/baseline state and the static operation registry before it may invoke any project-specific boundary.

## Legacy canary path compatibility

The current Hermes Deals `origin-path-rpi5-audit` workflow remains unchanged. Its existing self-hosted audit job and root-owned dispatcher stay available until the replacement path has separate live activation and end-to-end evidence.

The current dispatcher is intentionally bound to its existing runner-owned evidence directory contract. This source slice does not weaken that allowlist, add a new caller, alter its installer, or add a new privilege rule. Host compatibility is therefore **not yet proven** for the pull executor and must be addressed only at the later live/broker gate.

## Adapter behavior

`HermesDealsOriginAuditAdapter` is validation-only:

- preflight verifies exact operation/source/target/rollback/budget/exclusion/dependency contracts;
- `execution_enabled` must remain false;
- `apply()` always fails closed;
- postconditions only describe the sanitized evidence contract and required false production-mutation flags;
- the adapter contains no command launcher or generic execution surface.

## Source acceptance evidence

The regression suite proves that:

1. the production registry stays empty and disabled;
2. the fixture operation is `STRICT` and not ordinary-LIVE-ALL eligible;
3. the exact READY queue normalizes only to the reviewed operation;
4. free-form queue prose cannot expand the static invocation budget;
5. an unreviewed entrypoint fails with `UNKNOWN_OPERATION`;
6. the adapter cannot be marked executable;
7. the privileged dispatch request rejects SHA/operation/command/path/argv fields;
8. the poller remains unprivileged and the adapter exposes no generic execution bridge;
9. the expected Hermes Deals dispatcher/installer/probe source identities are bound as dependencies;
10. source readiness is not reported as host readiness.

## Explicitly not authorized

This source slice does not authorize or perform:

- LIVE-AUTH creation;
- P7 GitHub App/authorization-surface changes;
- credential placement;
- executor or privileged-broker installation/activation;
- systemd, privilege-rule, package or host mutation;
- Hermes Deals runner registration/deregistration;
- production deploy/cutover;
- DB/Review/publication writes;
- parser/collector changes;
- Cloudflare mutation;
- modification of the existing Hermes Deals origin audit dispatcher/installer/workflow.

A merge of this source slice only records a dormant reviewed canary contract. Live activation remains a separate explicit owner gate.
