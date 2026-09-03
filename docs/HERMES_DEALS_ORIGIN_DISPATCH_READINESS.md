# Hermes Deals origin audit — identity-only dispatch readiness boundary

Status: **SOURCE ONLY / DISPATCH NOT IMPLEMENTED / DISPATCH NOT ENABLED / RUNNER RETIREMENT NOT ELIGIBLE**

Tracking:

- current work item: `RPi5_main#354`
- completed registry reconciliation: `RPi5_main#352` / PR #353
- Hermes runner migration: `rozkalnsandris/hermes-deals#384`
- shared executor roadmap: `RPi5_main#236`

## Why this gate exists

PR #353 re-admitted `hermes-deals.origin-path-audit.v1` to the source-controlled operation registry while global `execution_enabled=false` remains authoritative. The operation is `STRICT`, not ordinary LIVE-ALL eligible, has rollback policy `NONE`, and permits at most one future `hermes-deals.read-only-audit-invocation`.

That source registration does **not** replace the existing `hermes-deals-audit` self-hosted execution path. Current `p9_runtime.py` intentionally has no dispatcher, result writer or production apply surface, and `HermesDealsOriginAuditAdapter.apply()` intentionally fails closed. Therefore current source can prove a canonical request is `DRY_RUN_READY`; it cannot execute the audit.

## Current reviewed Hermes source provenance

At this gate the reviewed cross-repository source baseline is:

- `rozkalnsandris/hermes-deals/main`: `fbe3cfa143788607446d0095ae1f887354d10eb3`
- workflow `.github/workflows/origin-path-rpi5-audit.yml`: blob `99a18c5f669e7880a8a8288c3f964285df87ae22`
- dispatcher `tools/runner/origin-path-rpi5-audit-dispatcher.sh`: blob `f9bfd02c6d36bb54d5380e1f0c99a0195e2ff4bc`
- installer `tools/runner/install-origin-path-rpi5-audit.sh`: blob `41f004420a0f5aed314aaefd796a54e14dbd17ea`
- probe `tools/hermes_deals_origin_probe.py`: blob `2362e8eb578a7279c38fe4ed2a7d1edd05df891a`

These are source-review anchors only. They do not prove current installed files, root ownership, sudoers, runner registration, credentials, runtime configuration or production health.

## Identity-only request

The future privileged boundary may receive only the canonical authorization issue identity:

```json
{
  "schema": "rozkalns.hermes-deals.origin-dispatch-request.v1",
  "authorization_issue_number": 17
}
```

The validator rejects every extra field. In particular, the request cannot carry:

- command or shell text;
- executable/dispatcher/probe paths;
- argv or environment;
- sudo authority;
- source SHA;
- `as_of` date;
- artifact/export path;
- repository entrypoint.

Those values must never be accepted from free-form GitHub prose or from the unprivileged caller.

## Independent privileged-side revalidation

Before any future read-only audit invocation, a separately reviewed privileged consumer must independently derive and verify all authority from canonical state. At minimum it must:

1. re-fetch the owner-authored LIVE-AUTH from the isolated authorization repository;
2. revalidate owner identity, TTL, body hash, replay state and queue binding;
3. re-fetch the READY queue and require the exact Hermes operation/source envelope;
4. prove the exact Hermes source SHA is merged/reachable and exact-SHA CI is successful;
5. revalidate the globally disabled static registry entry, invocation budget and exclusions;
6. revalidate the reviewed workflow/dispatcher/installer/probe provenance;
7. revalidate the root-owned origin registration and installed helper identities through a separately reviewed sanitized host-evidence contract;
8. derive any future dispatcher inputs from reviewed source and canonical state, never from request prose.

No source in #354 implements that privileged consumer or grants it runtime authority.

## Gate separation

The sequencing is deliberately split:

1. **#352 complete** — Hermes operation source-registered while globally disabled.
2. **#354 current** — freeze identity-only privileged-boundary source contract and prove the current implementation remains inert.
3. **Future source gate** — implement and review a capability-specific privileged broker/consumer with independent canonical revalidation; still no live activation merely from merge.
4. **Future LIVE host gate** — separately authorize installation/activation of that exact reviewed broker and any required host wiring.
5. **Future STRICT canary gate** — separately authorize exactly one genuine read-only Hermes origin audit and require sanitized postconditions with no production mutation.
6. **Runner retirement gate** — only after the replacement path has one accepted end-to-end canary and current capability coverage is proven; runner deregistration remains a separate LIVE authorization.

The separate `hermes-deals-release` production runner is outside #354 and is not made retirement-eligible by an origin-audit canary.

## Current classification

`CURRENT_WORK_ITEM=RPi5_main#354`

`CURRENT_PHASE=4`

`GLOBAL_EXECUTION_ENABLED=false`

`P9_DRY_RUN_SOURCE_READY=true`

`PRIVILEGED_DISPATCH_IMPLEMENTED=false`

`PRIVILEGED_DISPATCH_ENABLED=false`

`HOST_WIRING_ENABLED=false`

`GENUINE_HERMES_AUDIT_AUTHORIZED=false`

`HERMES_AUDIT_RUNNER_RETIREMENT_ELIGIBLE=false`

`HERMES_RELEASE_RUNNER_IN_SCOPE=false`

`PRODUCTION_MUTATION_STARTED=false`

Merge of this source gate never changes any of these live/runtime flags by itself.
